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

    @api.model
    def create(self, vals):
        sale_order = super(SaleOrder, self).create(vals)
        print("Sale Order Create")
        self._event('on_sale_order_create').notify(sale_order, fields=vals.keys())
        return sale_order
    
    @api.model
    def write(self, vals):
        sale_order = super(SaleOrder, self).write(vals)
        changed_fields = []
        for field, value in vals.items():
            if self[field] != value:
                    changed_fields.append(field)
        print("Sale Order Update")
        if len(changed_fields) > 0:
            self._event('on_sale_order_update').notify(sale_order, changed_fields)
        return sale_order
    
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
            if rest_response.status_code == 201:
                record.write({'sf_id':rest_response.json()['id']})
            else:
                _logger.error(f"Failed to update Salesforce record: {rest_response.content}")

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_sale_order_update(self, record, fields):
        print("Fields")
        print(fields)
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
                if rest_response.status_code != 204:
                    _logger.error(f"Failed to update Salesforce record: {rest_response.content}")
                
    @skip_if(lambda self: not self)
    def on_sale_order_delete(self,record, record_id):
        print("record_id")
        print(record_id)
        if record.sf_id not in [False,None, '']:
            rest_request = self.env['salesforce.rest.config'].build_rest_request_delete(record.sf_id,'crm_lead_delete')
            if rest_request:
                rest_response = self.env['salesforce.rest.config'].delete(rest_request['url'],rest_request['headers'])
                print("Response")
                print(rest_response)
                if rest_response.status_code != 204:
                    _logger.error(f"Failed to update Salesforce record: {rest_response.content}")