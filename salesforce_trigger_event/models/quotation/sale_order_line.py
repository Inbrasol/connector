import requests
import logging
import json

_logger = logging.getLogger(__name__)

from odoo import models, fields, api
from datetime import date

from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.model
    def create(self, vals):
        line = super(SaleOrderLine, self).create(vals)
        self._event('on_sale_order_line_create').notify(line, fields=vals.keys())
        return line
    
    @api.model
    def write(self, vals):
        line = super(SaleOrderLine, self).write(vals)
        changed_fields = []
        for field, value in vals.items():
            if self[field] != value:
                    changed_fields.append(field)
        self._event('on_sale_order_line_update').notify(line, changed_fields)
        return line
    

    @api.model
    def unlink(self):
        for line in self:
            self._event('on_sale_order_line_unlink').notify(line, fields=None)
        return super(SaleOrderLine, self).unlink()
    

class SaleOrderLineListener(Component):
    _name = 'sale.order.line.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['sale.order.line']
    
    
    @skip_if(lambda self, record, fields: not record or not fields)
    def on_sale_order_line_create(self, record, fields=None):
        print("Fields")
        print(fields)
        rest_request = self.env['salesforce.rest.config'].build_rest_request_create(record, fields, 'sale_order_line_create')
        if rest_request:
            rest_response = self.env['salesforce.rest.config'].post(rest_request['url'],rest_request['headers'],rest_request['fields'])
            print("Response")
            print(rest_response)
            if rest_response.status_code == 201:
                record.write({'sf_id':rest_response.json()['id']})
            else:
                _logger.error(f"Failed to update Salesforce record: {rest_response.content}")
    
    @skip_if(lambda self, record, fields: not record or not fields)
    def on_sale_order_line_update(self, record, fields):
        print("Fields")
        print(fields)
        rest_request = self.env['salesforce.rest.config'].build_rest_request_create(record, fields, 'sale_order_line_update')
        if rest_request:
            rest_response = None
            match rest_request['method']:
                case 'PATCH':
                    rest_response = self.env['salesforce.rest.config'].patch(rest_request['url'],rest_request['headers'],rest_request['fields'])
                case 'PUT':
                    rest_response = self.env['salesforce.rest.config'].put(rest_request['url'],rest_request['headers'],rest_request['fields'])  
        if rest_response:
            print("Response")
            print(rest_response)
            if rest_response.status_code == 204:
                record.write({'sf_id':rest_response.json()['id']})
            else:
                _logger.error(f"Failed to update Salesforce record: {rest_response.content}")
    
    @skip_if(lambda self, record, fields: not record or not fields)
    def on_sale_order_line_unlink(self, record, fields):
        print("Fields")
        print(fields)
        rest_request = self.env['salesforce.rest.config'].build_rest_request_create(record, fields, 'sale_order_line_unlink')
        if rest_request:
            rest_response = self.env['salesforce.rest.config'].delete(rest_request['url'],rest_request['headers'])
            print("Response")
            print(rest_response)