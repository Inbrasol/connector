import requests
import logging
import json

_logger = logging.getLogger(__name__)

from odoo import models, fields, api
from datetime import date, datetime

from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if
from ..backend.salesforce_rest_utils import SalesforceRestUtils

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'


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
            if self._fields[field].type in ['one2many', 'many2many']:
                continue
            elif isinstance(self[field], models.BaseModel):
                if self[field].id != value:
                    changed_fields.append(field)
            elif self[field] != value:
                changed_fields.append(field)
        super(SaleOrderLine, self.with_context(context_with_skip_sync)).write(vals)
        if len(changed_fields) > 0:
            self._event('on_sale_order_line_update').notify(self, changed_fields)
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
        rest_request = SalesforceRestUtils.build_request(record, fields, 'create', 'sale_order_line_create')
        if rest_request:
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            rest_response = SalesforceRestUtils.post(rest_request['url'],rest_request['headers'],rest_request['body'])
            SalesforceRestUtils.update_sf_integration_status(record, rest_response.status_code, rest_response.json(), context_with_skip_sync)
    

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_sale_order_line_update(self, record, fields):
        if record.sf_id not in [False, None, '']:
            rest_request = SalesforceRestUtils.build_request(record, fields, 'update', 'sale_order_line_update')
            if rest_request:
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                rest_response = None
                match rest_request['method']:
                    case 'PATCH':
                        rest_response = SalesforceRestUtils.patch(rest_request['url'],rest_request['headers'],rest_request['body'])
                    case 'PUT':
                        rest_response = SalesforceRestUtils.put(rest_request['url'],rest_request['headers'],rest_request['body'])
                SalesforceRestUtils.update_sf_integration_status(record, rest_response.status_code, rest_response.json(), context_with_skip_sync)
    
    @skip_if(lambda self: not self)
    def on_sale_order_line_delete(self,record, record_id):
        if record.sf_id not in [False, None, '']:
            rest_request = SalesforceRestUtils.build_request(record, None, 'delete', 'sale_order_line_delete')
            if rest_request:
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                rest_response = SalesforceRestUtils.delete(rest_request['url'],rest_request['headers'])
                SalesforceRestUtils.update_sf_integration_status(record, rest_response.status_code, rest_response.json(), context_with_skip_sync)