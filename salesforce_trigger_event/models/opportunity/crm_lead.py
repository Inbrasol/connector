import requests
import logging
import json
import threading

_logger = logging.getLogger(__name__)

from odoo import models, fields, api , _
from datetime import date,datetime
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if
from ..backend.salesforce_rest_utils import SalesforceRestUtils

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    
    @api.model
    def create(self, vals):
        lead = super(CrmLead, self).create(vals)
        self._event('on_crm_lead_create').notify(lead,fields=vals.keys())
        return lead


    @api.model
    def write(self, vals):
        _logger.error("on_sale_order initi: %s", vals)
        _logger.error("on_sale_order initi: %s", self.env.context.get('skip_sync'))
        if self.env.context.get('skip_sync'):
            super(CrmLead, self).write(vals)
            return self
        print("Vals")
        print(vals)
        # Set skip_sync in context to avoid recursion
        context_with_skip_sync = dict(self.env.context, skip_sync=True)
        changed_fields = []
        for field, value in vals.items():
            print("Field")
            print(field)
            print("Value")
            print(value)
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

        print("CRM Lead Update")
        print(self)
        self._process_lines(vals)
        return self
    

    @api.model
    def unlink(self, vals):
        lead = super(CrmLead, self).unlink()
        self._event('on_crm_lead_unlink').notify(lead,lead.id)
        return lead

    @api.model
    def create_lines_to_sf(self):
        related_model = self.env['crm.lead.product']
        fields_dict = related_model._fields
        product_lines_create = self.env['crm.lead.product'].search([
            ('lead_id', 'in', self.ids),
            ('sf_id', 'in', [False, None, '']),
            ('product_id.sf_id', 'not in', [False, None, ''])
        ])
        if product_lines_create:
            self._event('on_crm_lead_product_create').notify(product_lines_create, fields_dict)
    

    def _process_lines(self, vals):
        product_lines_update_ids = []
        product_lines_create_size = 0
        related_model = self.env['crm.lead.product']
        fields_dict = related_model._fields
        if 'lead_product_ids' in vals:
            for product_line in vals['lead_product_ids']:
                operation, line_id = product_line[0], product_line[1]
                if operation == 0:
                    product_lines_create_size += 1
                if operation == 1:
                    product_lines_update_ids.append(line_id)
        if product_lines_create_size > 0:
            threading.Timer(60.0, self.create_lines_to_sf).start()
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
            SalesforceRestUtils.update_sf_integration_status(record, rest_response, context_with_skip_sync)
    

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_crm_lead_update(self, record, fields=None):
        if record.sf_id not in [False, None, '']:
            rest_request =  self.env['salesforce.rest.config'].build_request(record, fields, 'update', 'crm_lead_update')
            if rest_request:
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                rest_response = SalesforceRestUtils.patch(rest_request['url'],rest_request['headers'],rest_request['body'])
                SalesforceRestUtils.update_sf_integration_status(record, rest_response, context_with_skip_sync)


    @skip_if(lambda self: not self)
    def on_crm_lead_unlink(self,record,record_id):
        if record.sf_id not in [False, None, '']:
            rest_request =  self.env['salesforce.rest.config'].build_request(record, None,'delete','crm_lead_delete')
            if rest_request:
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                rest_response = SalesforceRestUtils.delete(rest_request['url'],rest_request['headers'])
                SalesforceRestUtils.update_sf_integration_status(record, rest_response, context_with_skip_sync)