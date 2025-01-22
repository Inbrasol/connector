import requests
import logging
import json

_logger = logging.getLogger(__name__)

from odoo import models, fields, api
from datetime import date

from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if


class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    #skip_sync = fields.Boolean(string='Skip Sync', default=False, copy=False)

    @api.model
    def create(self, vals):
        sale_order = super(SaleOrder, self).create(vals)
        print("Sale Order Create")
        self._event('on_sale_order_create').notify(sale_order, fields=vals.keys())
        return sale_order
    
    @api.model
    def write(self, vals):
        if self.env.context.get('skip_sync'):
            super(SaleOrder, self).write(vals)
            return self
        
        # Set skip_sync in context to avoid recursion
        context_with_skip_sync = dict(self.env.context, skip_sync=True)
        changed_fields = []
        for field, value in vals.items():
            if isinstance(self[field], models.BaseModel):
                if self[field].id != value:
                    changed_fields.append(field)
            elif self[field] != value:
                changed_fields.append(field)
        super(SaleOrder, self.with_context(context_with_skip_sync)).write(vals)
        if len(changed_fields) > 0:
            self._event('on_sale_order_update').notify(self, changed_fields)

        print("Sale Order Update")
        print(self)
        return self
    
    @api.model
    def unlink(self):
        self._event('on_sale_order_delete').notify(self,self.id)
        order = super(SaleOrder, self).unlink()
        return order
    

class SaleOrderListener(Component):
    _name = 'sale.order.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['sale.order']
    
    
    @skip_if(lambda self, record, fields: not record or not fields)
    def on_sale_order_create(self, record, fields):
        print("Fields")
        print(fields)
        rest_request = self.env['salesforce.rest.config'].build_rest_request_create(record, fields, 'sale_order_create')
        if rest_request:
            rest_response = self.env['salesforce.rest.config'].post(rest_request['url'],rest_request['headers'],rest_request['fields'])
            print("Response")
            print(rest_response)
            if rest_request['type'] == 'composite':
                if rest_response.status_code in [200, 201]:
                    for record_response in rest_response.json()['compositeResponse']:
                        if record_response['httpStatusCode'] in [200, 201] and record_response['referenceId'] in  rest_request['map_ref_fields'].keys():
                            map_field = rest_request['map_ref_fields'][record_response['referenceId']]
                            record_to_update = self.env[map_field['model']].browse(map_field['id'])
                            record_to_update.write({'sf_id': record_response['body']['id']})
                else:
                    _logger.error(f"Failed to update Salesforce record: {rest_response.content}")
            
            elif rest_request['type'] == 'single':
                if rest_response.status_code in [200, 201]:
                    record.write({'sf_id': rest_response.json()['id']})
                else:
                    _logger.error(f"Failed to update Salesforce record: {rest_response.content}")

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_sale_order_update(self, record, fields):
        print("Fields")
        print(fields)
        print("Record")
        print(record)
        if record.sf_id not in [False, None, '']:
            rest_request = self.env['salesforce.rest.config'].build_rest_request_update(record, fields, 'sale_order_update')
            if rest_request:
                rest_response = None
                match rest_request['method']:
                    case 'PATCH':
                        rest_response = self.env['salesforce.rest.config'].patch(rest_request['url'],rest_request['headers'],rest_request['fields'])
                    case 'PUT':
                        rest_response = self.env['salesforce.rest.config'].put(rest_request['url'],rest_request['headers'],rest_request['fields'])  
                print("Response")
                print(rest_response)
                if rest_response and rest_response.status_code != 204:
                    _logger.error(f"Failed to update Salesforce record: {rest_response.content}")
                
    @skip_if(lambda self: not self)
    def on_sale_order_delete(self,record, record_id):
        print("record_id")
        print(record_id)
        sale_order = self.env['sale.order'].browse(record.id)
        if sale_order.sf_id not in [False,None, '']:
            rest_request = self.env['salesforce.rest.config'].build_rest_request_delete(record.sf_id,'crm_lead_delete')
            if rest_request:
                rest_response = self.env['salesforce.rest.config'].delete(rest_request['url'],rest_request['headers'])
                print("Response")
                print(rest_response)
                if rest_response.status_code != 204:
                    _logger.error(f"Failed to update Salesforce record: {rest_response.content}")