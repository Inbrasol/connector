import requests
import logging
import json

_logger = logging.getLogger(__name__)

from odoo import models, fields, api , _
from datetime import date, datetime, timedelta
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if
from ..backend.salesforce_rest_utils import SalesforceRestUtils

class CrmLeadProduct(models.Model):
    _inherit = 'crm.lead.product'

    @api.model
    def create_lines_to_sf_by_cron(self):
        _logger.error("cron: %s", self)
        related_model = self.env['crm.lead.product']
        fields = related_model._fields.keys()
        product_lines_create = related_model.search([
            ('sf_id', '=', False),
            ('lead_id.sf_id', '!=', False),
            ('product_tmpl_id.sf_id', '!=', False),
        ], limit=201)
        _logger.error("product_lines_create: %s", product_lines_create)
        
        if not product_lines_create:
            return self

        _logger.error("product_lines_create: %s", product_lines_create)

        # Limit the number of product lines to process to a maximum of 200
        product_lines_to_process = product_lines_create[:min(len(product_lines_create), 200)]

        self._event('on_crm_lead_product_create').notify(product_lines_to_process, fields)

        # If there are more than 200 product lines, schedule the next batch
        if len(product_lines_create) > 200:
            cron_job = self.env.ref('salesforce_trigger_event.ir_cron_create_crm_lead_product_to_sf')
            next_call_time = (datetime.now() + timedelta(minutes=2)).strftime('%Y-%m-%d %H:%M:%S')
            cron_job.write({'nextcall': next_call_time})

        return self
        
    """
    @api.model
    def create(self, vals):
        lead_product = super(CrmLeadProduct, self).create(vals)
        if lead_product.product_tmpl_id.sf_id in [False, None, '']:
            self._event('on_crm_lead_product_create').notify(lead_product, fields=vals.keys())
            
        return lead_product

    """
    
    """
    @api.model
    def write(self, vals):
        # Call Sync Product Template to Salesforce
        _logger.error("crm.lead.product: %s", vals)
        _logger.error("crm.lead.product: %s", self.sf_id)
        _logger.error("crm.lead.product: %s", vals.get('product_id'))
        _logger.error("crm.lead.product: %s", self.product_tmpl_id.sf_id)
    
        if self.sf_id in [False, None, ''] and vals.get('product_id') and self.product_tmpl_id.sf_id not in [False, None, '']:
            self._event('on_crm_lead_product_create').notify(self, fields=vals.keys)
        if self.env.context.get('skip_sync'):
            super(CrmLeadProduct, self).write(vals)
            return self
        
        # Set skip_sync in context to avoid recursion
        context_with_skip_sync = dict(self.env.context, skip_sync=True)
        changed_fields = []
        for record in self:
            record_changed_fields = []
            for field, value in vals.items():
                if record._fields[field].type in ['one2many', 'many2many']:
                    continue
                elif isinstance(record[field], models.BaseModel):
                    if record[field].id != value:
                        record_changed_fields.append(field)
                elif record[field] != value:
                    record_changed_fields.append(field)
            if record_changed_fields:
                changed_fields.append((record, record_changed_fields))
        
        super(CrmLeadProduct, self.with_context(context_with_skip_sync)).write(vals)
        
        if changed_fields:
            records_to_notify = [record for record, fields in changed_fields]
            fields_to_notify = list(set(field for record, fields in changed_fields for field in fields))
            self._event('on_crm_lead_product_update').notify(records_to_notify, fields_to_notify)

        print("Crm Lead Product Update")
        print(self)
        return self
    """
    
    def unlink(self):
        if self.env.context.get('skip_sync'):
            return super(CrmLeadProduct, self).unlink()
        
        sf_ids = self.env['crm.lead.product'].search([('id', 'in', self.ids)]).mapped('sf_id')
        self._event('on_crm_lead_product_delete').notify(sf_ids)
        lead_product = super(CrmLeadProduct, self).unlink()
        return lead_product
    


class CrmLeadProductListener(Component):
    _name = 'crm.lead.product.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['crm.lead.product']
    
    @skip_if(lambda self, record, fields: not record or not fields)
    def on_crm_lead_product_create(self, record, fields):
        #Call Sync Product Template to Salesforce
        rest_request = self.env['salesforce.rest.config'].build_request(record, fields, 'create', 'crm_lead_product_create')
        if rest_request:
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            rest_response = SalesforceRestUtils.post(rest_request['url'], rest_request['headers'], rest_request['body'])
            if rest_response and rest_response.status_code in [200, 201]:
                SalesforceRestUtils._handle_successful_response(self, rest_request, rest_response, context_with_skip_sync)
            else:
                SalesforceRestUtils._handle_failed_response(record, rest_response, context_with_skip_sync)
        
    @skip_if(lambda self, records, fields: not records or not fields)
    def on_crm_lead_product_update(self, records, fields):
        rest_request = self.env['salesforce.rest.config'].build_request(records, fields, 'update', 'crm_lead_product_update')
        if rest_request:
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            rest_response = None
            match rest_request['method']:
                case 'PATCH':
                    rest_response = SalesforceRestUtils.patch(rest_request['url'], rest_request['headers'], rest_request['body'])
                case 'PUT':
                    rest_response = SalesforceRestUtils.put(rest_request['url'], rest_request['headers'], rest_request['body'])
            SalesforceRestUtils._update_sf_integration_status(records, rest_response, context_with_skip_sync)
    
    @skip_if(lambda self, records: not records)
    def on_crm_lead_product_delete(self, records):
        rest_request = self.env['salesforce.rest.config'].build_request(records, None, 'delete', 'crm_lead_product_delete')
        if rest_request:
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            rest_response = SalesforceRestUtils.delete(rest_request['url'], rest_request['headers'])
            SalesforceRestUtils._handle_successful_response(self, rest_request, rest_response, context_with_skip_sync)