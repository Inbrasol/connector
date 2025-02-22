import requests
import logging
import json

_logger = logging.getLogger(__name__)

from odoo import models, fields, api , _
from datetime import date, datetime
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if
from ..backend.salesforce_rest_utils import SalesforceRestUtils

class CrmLeadProduct(models.Model):
    _inherit = 'crm.lead.product'
    

    @api.model
    def create(self, vals):
        lead_product = super(CrmLeadProduct, self).create(vals)
        self._event('on_crm_lead_product_create').notify(lead_product, list(vals.keys()))
        return lead_product
    
    @api.model
    def write(self, vals):
        if self.env.context.get('skip_sync'):
            super(CrmLeadProduct, self).write(vals)
            return self
        
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
        super(CrmLeadProduct, self.with_context(context_with_skip_sync)).write(vals)
        if len(changed_fields) > 0:
            self._event('on_crm_lead_product_update').notify(self, changed_fields)

        print("Crm Lead Product Update")
        print(self)
        return self
    
    @api.model
    def unlink(self):
        for record in self:
                self._event('on_crm_lead_product_delete').notify(record, record.id)
        lead_product = super(CrmLeadProduct, self).unlink()
        return lead_product
    


class CrmLeadProductListener(Component):
    _name = 'crm.lead.product.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['crm.lead.product']
    
    @skip_if(lambda self, record, fields: not record or not fields)
    def on_crm_lead_product_create(self, record, fields):
        rest_request = SalesforceRestUtils.build_request(record, fields, 'create', 'crm_lead_product_create')
        if rest_request:
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            rest_response = SalesforceRestUtils.post(rest_request['url'],rest_request['headers'],rest_request['body'])
            SalesforceRestUtils.update_sf_integration_status(record, rest_response.status_code, rest_response.json(), context_with_skip_sync)
    
    @skip_if(lambda self, record, fields: not record or not fields)
    def on_crm_lead_product_update(self, record, fields):
        if record.sf_id not in [False, None, '']:
            rest_request = SalesforceRestUtils.build_request(record, fields, 'update', 'crm_lead_product_update')
            if rest_request:
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                rest_response = None
                match rest_request['method']:
                    case 'PATCH':
                        rest_response = SalesforceRestUtils.patch(rest_request['url'],rest_request['headers'],rest_request['body'])
                    case 'PUT':
                        rest_response = SalesforceRestUtils.put(rest_request['url'],rest_request['headers'],rest_request['body'])
                SalesforceRestUtils.update_sf_integration_status(record, rest_response.status_code, rest_response.json(), context_with_skip_sync)
    
    @skip_if(lambda self, record, fields: not record or not fields)
    def on_crm_lead_product_delete(self, record, record_id):
        if record.sf_id not in [False, None, '']:
            rest_request = SalesforceRestUtils.build_request(record, None, 'delete', 'crm_lead_product_delete')
            if rest_request:
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                rest_response = SalesforceRestUtils.delete(rest_request['url'],rest_request['headers'])
                SalesforceRestUtils.update_sf_integration_status(record, rest_response.status_code, rest_response.json(), context_with_skip_sync)