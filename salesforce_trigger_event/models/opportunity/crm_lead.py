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
            ('sf_id', 'in', [False, None, '']),
            ('partner_id.sf_id', 'not in', [False, None, ''])
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
    
    @api.model
    def create(self, vals):
        if self.env.context.get('skip_sync'):
            return super(CrmLead, self).create(vals)
        
        lead = super(CrmLead, self).create(vals)
        self._event('on_crm_lead_create').notify(lead,fields=vals.keys())
        return lead


    @api.model
    def write(self, vals):
        if self.env.context.get('skip_sync'):
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
        if len(changed_fields) > 0:
            self._event('on_crm_lead_update').notify(self, changed_fields)

        self._process_lines(vals)
        return self
    

    @api.model
    def unlink(self):
        if self.env.context.get('skip_sync'):
            return super(CrmLead, self).unlink()
        
        sf_ids = self.env['crm.lead'].search([('id', 'in', self.ids)]).mapped('sf_id')
        self._event('on_sale_order_delete').notify(sf_ids)
        crmlead = super(CrmLead, self).unlink()
        return crmlead
    

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