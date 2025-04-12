import requests
import logging
import json
import threading

_logger = logging.getLogger(__name__)

from odoo import models, fields, api , _
from datetime import date,datetime, timedelta
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if
from ..backend.salesforce_rest_utils import SalesforceRestUtils

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    @api.model
    def create_lines_to_sf_by_cron(self):
        _logger.error("cron: %s", self)
        related_model = self.env['crm.lead']
        fields = related_model._fields.keys()
        lines_create = related_model.search([
            ('sf_id', '=', False),
            ('partner_id.commercial_partner_id.sf_id', '!=', False),
            ('stage_id.code', '!=', False),
        ], limit=201)
        
        _logger.error("product_lines_create: %s", lines_create)
        
        if not lines_create:
            return self

        # Limit the number of product lines to process to a maximum of 200
        lines_to_process = lines_create[:min(len(lines_create), 200)]

        self._event('on_crm_lead_create').notify(lines_to_process, fields)

        # If there are more than 200 product lines, schedule the next batch
        if len(lines_create) > 200:
            cron_job = self.env.ref('salesforce_trigger_event.ir_cron_create_crm_lead_to_sf')
            next_call_time = (datetime.now() + timedelta(minutes=2)).strftime('%Y-%m-%d %H:%M:%S')
            cron_job.write({'nextcall': next_call_time})

        return self
    
    def create_lines_to_sf(self):
        #Create Product Template to Salesforce
        _logger.error("create_lines_to_sf: %s", self)
        if self.env.context.get('skip_sync') or  self.sf_id  in [False, None, '']:
            return self
        
        # Fetch lines that need to be created in Salesforce
        context_with_skip_sync = dict(self.env.context, skip_sync=True)
        lines_product_template_ids = self.lead_product_ids.filtered(lambda line: not line.sf_id and not line.product_id.sf_id).mapped('product_id.product_tmpl_id').ids
        if lines_product_template_ids:
            _logger.error("lines_product_template_ids: %s", lines_product_template_ids)
            product_template_related_model = self.env['product.template']
            product_template_fields_dict = product_template_related_model._fields
            # Filter lines that are not already synced with Salesforce
            product_template_lines_create = product_template_related_model.search([
                ('id', 'in', lines_product_template_ids),
                ('active', '=', True)
            ], limit=201)

            _logger.error("product_template_lines_create: %s", product_template_lines_create)

            if not product_template_lines_create:
                return self

            # Limit the number of product lines to process to a maximum of 200
            product_template_lines_to_process = product_template_lines_create[:min(len(product_template_lines_create), 200)]
            self.env['product.template'].with_context(context_with_skip_sync)._event('on_product_template_create_bulk').notify(product_template_lines_to_process, product_template_fields_dict)


        #Create CRM Lead Product to Salesforce
        lines_create_ids = self.lead_product_ids.filtered(lambda line: not line.sf_id and line.product_id.sf_id).ids
        if not lines_create_ids:
            return self
        
        related_model = self.env['crm.lead.product']
        fields_dict = related_model._fields
        # Filter lines that are not already synced with Salesforce
        lines_create = related_model.search([
            ('id', 'in', lines_create_ids),
            ('sf_id', '=', False),
            ('lead_id.sf_id', '!=', False),
            ('product_id.sf_id', '!=', False),
        ], limit=201)
        
        _logger.error("crm_lead_product_lines_update: %s", lines_create)
        
        if not lines_create:
            return self

        # Limit the number of product lines to process to a maximum of 200
        lines_to_process = lines_create[:min(len(lines_create), 200)]
        self.env['crm.lead.product'].with_context(context_with_skip_sync)._event('on_crm_lead_product_create').notify(lines_to_process, fields_dict)

        return self
        
    
    
    def create(self, vals):
        if self.env.context.get('skip_sync'):
            return super(CrmLead, self).create(vals)
        
        if self.sf_id not in [False, None, '']:
            return super(CrmLead, self).create(vals)
        
        lead = super(CrmLead, self).create(vals)
        fields = self._fields.keys()
        self._event('on_crm_lead_create').notify(lead,fields=fields)
        return lead

    def write(self, vals):
        if self.env.context.get('skip_sync'):
            return super(CrmLead, self).write(vals)
        
        if self.sf_id in [False, None, '']:
            return super(CrmLead, self).write(vals)
        
        # Set skip_sync in context to avoid recursion
        context_with_skip_sync = dict(self.env.context, skip_sync=True)
        changed_fields = []
        for field, value in vals.items():
            if self._fields[field].type in ['one2many', 'many2many']:
                continue
            elif isinstance(self[field], models.BaseModel):
                if self[field].id != value:
                    changed_fields.append(field)
            elif self[field] != value:
                changed_fields.append(field)
        super(CrmLead, self.with_context(context_with_skip_sync)).write(vals)
        if len(changed_fields) > 0 and 'date_automation_last' not in changed_fields:
            self._event('on_crm_lead_update').notify(self, changed_fields)

        self._process_lines(vals)
        return self
    
    def unlink(self):
        _logger.error("→ Intentando eliminar crm.lead con contexto skip_sync: %s", self.env.context.get('skip_sync'))
        # Buscar los sf_ids de los registros que se quieren eliminar
        crm_leads = self.env['crm.lead'].browse(self.ids)
        sf_ids = [sf_id for sf_id in crm_leads.mapped('sf_id') if sf_id]  # Solo valores no vacíos

        _logger.error("→ sf_ids encontrados: %s", sf_ids)
        if len(sf_ids) == 0:
            _logger.error("→ No se encontraron sf_ids, se eliminará normalmente.")
            return super(CrmLead, self).unlink()
        else:
            _logger.error("→ Se encontraron sf_ids, notificando evento antes de eliminar.")
            self._event('on_crm_lead_unlink').notify(crm_leads)
            return super(CrmLead, self).unlink()
    
    def _process_lines(self, vals):
        product_lines_update_ids = []
        related_model = self.env['crm.lead.product']
        fields_dict = related_model._fields
        if 'lead_product_ids' in vals:
            for product_line in vals['lead_product_ids']:
                operation, line_id = product_line[0], product_line[1]
                if operation == 1:
                    product_lines_update_ids.append(line_id)
        if product_lines_update_ids:
            product_lines = related_model.browse(product_lines_update_ids)
            self.env['crm.lead.product']._event('on_crm_lead_product_update').notify(product_lines, fields_dict)
        
        return self


class CrmLeadEventListener(Component):
    _name = 'crm.lead.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['crm.lead']


    @skip_if(lambda self, record, fields: not record or not fields)
    def on_crm_lead_create(self, record, fields=None):
        rest_request =  self.env['salesforce.rest.config'].build_request(record, fields, 'create', 'crm_lead_create')
        if rest_request:
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            rest_response = SalesforceRestUtils.post(rest_request['url'],rest_request['headers'],rest_request['body'])
            if rest_response and rest_response.status_code in [200, 201]:
                SalesforceRestUtils._handle_successful_response(self, rest_request, rest_response, context_with_skip_sync)
            else:
                SalesforceRestUtils._handle_failed_response(record, rest_response, context_with_skip_sync)
    

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_crm_lead_update(self, record, fields=None):
        if record.sf_id not in [False, None, '']:
            rest_request =  self.env['salesforce.rest.config'].build_request(record, fields, 'update', 'crm_lead_update')
            if rest_request:
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                rest_response = SalesforceRestUtils.patch(rest_request['url'],rest_request['headers'],rest_request['body'])
                SalesforceRestUtils._update_sf_integration_status(record, rest_response, context_with_skip_sync)


    @skip_if(lambda self, records: not records)
    def on_crm_lead_unlink(self, records):
        rest_request = self.env['salesforce.rest.config'].build_request(records, None, 'delete', 'crm_lead_delete')
        if rest_request:
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            rest_response = SalesforceRestUtils.delete(rest_request['url'], rest_request['headers'])
            SalesforceRestUtils._handle_successful_response(self, rest_request, rest_response, context_with_skip_sync)