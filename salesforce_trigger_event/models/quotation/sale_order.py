import requests
import logging
import json

_logger = logging.getLogger(__name__)

from odoo import models, fields, api
from datetime import date, datetime, timedelta
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if
from ..backend.salesforce_rest_utils import SalesforceRestUtils

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    @api.model
    def create_lines_to_sf_by_cron(self):
        _logger.error("cron: %s", self)
        related_model = self.env['sale.order']
        fields = related_model._fields.keys()
        lines_create = related_model.search([
            ('sf_id', 'in', [False, None, '']),
            ('partner_id.sf_id', 'not in', [False, None, '']),
            ('state', 'in', ['draft', 'sent', 'sale']),
        ], limit=201)
        
        _logger.error("sale_orders: %s", lines_create)
        
        if not lines_create:
            return self

        # Limit the number of product lines to process to a maximum of 200
        lines_to_process = lines_create[:min(len(lines_create), 200)]

        self._event('on_sale_order_create').notify(lines_to_process, fields)

        # If there are more than 200 product lines, schedule the next batch
        if len(lines_create) > 200:
            cron_job = self.env.ref('salesforce_trigger_event.ir_cron_create_sale_order_to_sf')
            next_call_time = (datetime.now() + timedelta(minutes=2)).strftime('%Y-%m-%d %H:%M:%S')
            cron_job.write({'nextcall': next_call_time})

        return self
    
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
            if self._fields[field].type in ['one2many', 'many2many']:
                continue
            elif isinstance(self[field], models.BaseModel):
                if self[field].id != value:
                    changed_fields.append(field)
            elif self[field] != value:
                changed_fields.append(field)
        super(SaleOrder, self.with_context(context_with_skip_sync)).write(vals)
        if len(changed_fields) > 0:
            self._event('on_sale_order_update').notify(self, changed_fields)

        print("Sale Order Update")
        print(self)
        self._process_lines(vals)
        return self
    
    @api.model
    def unlink(self):
        sf_ids = self.env['sale.order'].search([('id', 'in', self.ids)]).mapped('sf_id')
        self._event('on_sale_order_delete').notify(sf_ids)
        order = super(SaleOrder, self).unlink()
        return order
    
    def _process_lines(self, vals):
        sale_order_lines_update_ids = []
        related_model = self.env['sale.order.line']
        fields_dict = related_model._fields
        if 'order_line' in vals:
            for product_line in vals['order_line']:
                operation, line_id = product_line[0], product_line[1]
                if operation == 1:
                    sale_order_lines_update_ids.append(line_id)

        if sale_order_lines_update_ids:
            sale_order_lines = related_model.browse(sale_order_lines_update_ids)
            self.env['sale.order.line']._event('on_sale_order_line_update').notify(sale_order_lines, fields_dict)
        
        return self
    
class SaleOrderListener(Component):
    _name = 'sale.order.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['sale.order']
    

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_sale_order_create(self, record, fields):
        rest_request = self.env['salesforce.rest.config'].build_request(record, fields, 'create', 'sale_order_create')
        if not rest_request:
            return

        context_with_skip_sync = dict(self.env.context, skip_sync=True)
        rest_response = self._send_rest_request(rest_request)

        if rest_response and rest_response.status_code in [200, 201]:
            SalesforceRestUtils._handle_successful_response(self, rest_request, rest_response, context_with_skip_sync)
        else:
            SalesforceRestUtils._handle_failed_response(record, rest_response, context_with_skip_sync)

    def _send_rest_request(self, rest_request):
        if rest_request['type'] in ['rest','composite_tree', 'composite']:
            return SalesforceRestUtils.post(rest_request['url'], rest_request['headers'], rest_request['body'])
        _logger.warning(f"Unsupported request type: {rest_request['type']}")
        return None

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_sale_order_update(self, record, fields):
        if record.sf_id not in [False, None, '']:
            rest_request = self.env['salesforce.rest.config'].build_request(record, fields, 'update', 'sale_order_update')
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            if rest_request:
                rest_response = None
                match rest_request['method']:
                    case 'PATCH':
                        rest_response = SalesforceRestUtils.patch(rest_request['url'],rest_request['headers'],rest_request['body'])
                    case 'PUT':
                        rest_response = SalesforceRestUtils.put(rest_request['url'],rest_request['headers'],rest_request['body'])
                SalesforceRestUtils._update_sf_integration_status(record, rest_response, context_with_skip_sync)
    

    skip_if(lambda self, records: not records)
    def on_sale_order_delete(self, records):
        rest_request = self.env['salesforce.rest.config'].build_request(records, None, 'delete', 'sale_order_delete')
        if rest_request:
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            rest_response = SalesforceRestUtils.delete(rest_request['url'], rest_request['headers'])
            SalesforceRestUtils._handle_successful_response(self, rest_request, rest_response, context_with_skip_sync)
