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

    skip_sync = fields.Boolean(string='Skip Sync', default=False, copy=False)

    @api.model
    def create(self, vals):
        line = super(SaleOrderLine, self).create(vals)
        self._event('on_sale_order_line_create').notify(line, fields=vals.keys())
        return line
    
    @api.model
    def write(self, vals):
        if self.env.context.get('skip_sync'):
            super(SaleOrderLine, self).write(vals)
            return self
        
        # Set skip_sync in context to avoid recursion
        context_with_skip_sync = dict(self.env.context, skip_sync=True)
        changed_fields = []
        for field, value in vals.items():
            if self[field] != value:
                changed_fields.append(field)
        super(SaleOrderLine, self.with_context(context_with_skip_sync)).write(vals)
        if len(changed_fields) > 0:
            self._event('on_sale_order_line_update').notify(self, changed_fields)
        self.write({'skip_sync':False})
        return self
    

    @api.model
    def unlink(self):
        self._event('on_sale_order_line_delete').notify(self, self.id)
        sale_order_line = super(SaleOrderLine, self).unlink()
        return sale_order_line
    

class SaleOrderLineListener(Component):
    _name = 'sale.order.line.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['sale.order.line']
    
    
    @skip_if(lambda self, record, fields: not record or not fields)
    def on_sale_order_line_create(self, record, fields):
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
        if record.sf_id not in [False, None, '']:
            rest_request = self.env['salesforce.rest.config'].build_rest_request_update(record, fields, 'sale_order_line_update')
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
    
    @skip_if(lambda self: not self)
    def on_sale_order_line_delete(self,record, record_id):
        print("record_id")
        print(record_id)
        if record.sf_id not in [False, None, '']:
            rest_request = self.env['salesforce.rest.config'].build_rest_request_delete(record.sf_id,'sale_order_line_delete')
            if rest_request:
                rest_response = self.env['salesforce.rest.config'].delete(rest_request['url'],rest_request['headers'])
                print("Response")
                print(rest_response)