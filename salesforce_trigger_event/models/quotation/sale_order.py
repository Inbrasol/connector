import requests
import logging
import json

_logger = logging.getLogger(__name__)

from odoo import models, fields, api
from datetime import date, datetime
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if
from ..backend.salesforce_rest_utils import SalesforceRestUtils

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
        rest_request = SalesforceRestUtils.build_request(record, fields, 'create', 'sale_order_create')
        if not rest_request:
            return

        context_with_skip_sync = dict(self.env.context, skip_sync=True)
        rest_response = self._send_rest_request(rest_request)

        if rest_response and rest_response.status_code in [200, 201]:
            self._handle_successful_response(rest_request, rest_response, context_with_skip_sync)
        else:
            self._handle_failed_response(record, rest_response, context_with_skip_sync)

    def _send_rest_request(self, rest_request):
        if rest_request['type'] in ['composite', 'single']:
            return SalesforceRestUtils.post(rest_request['url'], rest_request['headers'], rest_request['body'])
        _logger.warning(f"Unsupported request type: {rest_request['type']}")
        return None

    def _handle_successful_response(self, rest_request, rest_response, context_with_skip_sync):
        if rest_request['type'] == 'composite':
            self._process_composite_response(rest_request, rest_response, context_with_skip_sync)
        elif rest_request['type'] == 'single':
            self._update_record_with_response(rest_request, rest_response, context_with_skip_sync)

    def _process_composite_response(self, rest_request, rest_response, context_with_skip_sync):
        response_data = rest_response.json()
        if rest_request['composite_type'] == 'single':
            self._update_records_from_composite_response(response_data['compositeResponse'], rest_request, context_with_skip_sync)
        elif rest_request['composite_type'] == 'tree':
            self._update_records_from_composite_response(response_data['results'], rest_request, context_with_skip_sync)

    def _update_records_from_composite_response(self, responses, rest_request, context_with_skip_sync):
        for record_response in responses:
            if record_response['referenceId'] in rest_request['map_ref_fields']:
                map_field = rest_request['map_ref_fields'][record_response['referenceId']]
                record_to_update = self.env[map_field['model']].browse(map_field['id'])
                record_to_update.with_context(context_with_skip_sync).write({
                    'sf_id': record_response.get('id', record_response['body'].get('id')),
                    'sf_integration_status': 'success',
                    'sf_integration_datetime': datetime.now()
                })

    def _update_record_with_response(self, rest_request, rest_response, context_with_skip_sync):
        record = self.env[rest_request['model']].browse(rest_request['id'])
        record.with_context(context_with_skip_sync).write({
            'sf_id': rest_response.json()['id'],
            'sf_integration_status': 'success',
            'sf_integration_datetime': datetime.now()
        })

    def _handle_failed_response(self, record, rest_response, context_with_skip_sync):
        _logger.error(f"Failed to update Salesforce record: {rest_response.content}")
        record.with_context(context_with_skip_sync).write({
            'sf_integration_status': 'failed',
            'sf_integration_datetime': datetime.now(),
            'sf_integration_error': rest_response.json()
        })


    @skip_if(lambda self, record, fields: not record or not fields)
    def on_sale_order_update(self, record, fields):
        if record.sf_id not in [False, None, '']:
            rest_request = SalesforceRestUtils.build_request(record, fields, 'update', 'sale_order_update')
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            if rest_request:
                rest_response = None
                match rest_request['method']:
                    case 'PATCH':
                        rest_response = SalesforceRestUtils.patch(rest_request['url'],rest_request['headers'],rest_request['body'])
                    case 'PUT':
                        rest_response = SalesforceRestUtils.put(rest_request['url'],rest_request['headers'],rest_request['body'])
                SalesforceRestUtils.update_sf_integration_status(record, rest_response.status_code, rest_response.json(), context_with_skip_sync)
    

    @skip_if(lambda self: not self)
    def on_sale_order_delete(self,record, record_id):
        sale_order = self.env['sale.order'].browse(record.id)
        if sale_order.sf_id not in [False,None, '']:
            rest_request = SalesforceRestUtils.build_request(sale_order, None, 'delete', 'sale_order_delete')
            if rest_request:
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                rest_response = SalesforceRestUtils.delete(rest_request['url'],rest_request['headers'])
                SalesforceRestUtils.update_sf_integration_status(sale_order, rest_response.status_code, rest_response.json(), context_with_skip_sync)