import requests
import logging

_logger = logging.getLogger(__name__)

from odoo import models, api, fields
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if
from datetime import date, datetime
from ..backend.salesforce_rest_utils import SalesforceRestUtils

class AccountMove(models.Model):
    _inherit = 'account.move'


    @api.model
    def create(self, vals):
        account_move = super(AccountMove, self).create(vals)
        self._event('on_account_move_create').notify(account_move,fields=vals.keys())
        return account_move
    
    @api.model
    def write(self, vals):
        if self.env.context.get('skip_sync'):
            super(AccountMove, self).write(vals)
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
        super(AccountMove, self.with_context(context_with_skip_sync)).write(vals)
        if len(changed_fields) > 0:
            self._event('on_account_move_update').notify(self, changed_fields)

        print("Account Move Update")
        print(self)
        return self
    
    @api.model
    def unlink(self):
        self._event('on_account_move_delete').notify(self, self.id)
        account_move = super(AccountMove, self).unlink()
        return  account_move
    
    def _process_lines(self, vals):
        account_move_lines_update_ids = []
        related_model = self.env['account.move.line']
        fields_dict = related_model._fields
        if 'line_ids' in vals:
            for product_line in vals['line_ids']:
                operation, line_id = product_line[0], product_line[1]
                if operation == 1:
                    account_move_lines_update_ids.append(line_id)

        if account_move_lines_update_ids:
            account_move_lines = related_model.browse(account_move_lines_update_ids)
            self.env['account.move.line']._event('on_account_move_line_update').notify(account_move_lines, fields_dict)
        
        return self

class AccountMoveListener(Component):
    _name = 'account.move.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['account.move']


    @skip_if(lambda self, record, fields: not record or not fields)
    def on_account_move_create(self, record, fields):
        rest_request = self.env['salesforce.rest.config'].build_request(record, fields, 'create', 'account_move_create')
        if not rest_request:
            return

        context_with_skip_sync = dict(self.env.context, skip_sync=True)
        rest_response = self._send_rest_request(rest_request)

        if rest_response and rest_response.status_code in [200, 201]:
            self._handle_successful_response(rest_request, rest_response, context_with_skip_sync)
        else:
            self._handle_failed_response(record, rest_response, context_with_skip_sync)

    def _send_rest_request(self, rest_request):
        if rest_request['type'] in ['rest', 'composite_tree', 'composite']:
            return SalesforceRestUtils.post(rest_request['url'], rest_request['headers'], rest_request['body'])
        _logger.warning(f"Unsupported request type: {rest_request['type']}")
        return None

    def _handle_successful_response(self, rest_request, rest_response, context_with_skip_sync):
        if rest_request['type'] in ['composite_tree', 'composite']:
            self._process_composite_response(rest_request, rest_response, context_with_skip_sync)
        elif rest_request['type'] == 'rest':
            self._update_record_with_response(rest_request, rest_response, context_with_skip_sync)

    def _process_composite_response(self, rest_request, rest_response, context_with_skip_sync):
        response_data = rest_response.json()
        if rest_request['type'] == 'composite':
            self._update_records_from_composite_response(response_data['compositeResponse'], rest_request, context_with_skip_sync)
        elif rest_request['type'] == 'composite_tree':
            self._update_records_from_composite_response(response_data['results'], rest_request, context_with_skip_sync)

    def _update_records_from_composite_response(self, responses, rest_request, context_with_skip_sync):
        for record_response in responses:
            if record_response['referenceId'] in rest_request['map_ref_fields']:
                map_field = rest_request['map_ref_fields'][record_response['referenceId']]
                record_to_update = self.env[map_field['model']].browse(map_field['id'])
                record_to_update.with_context(context_with_skip_sync).write({
                    'sf_id': record_response.get('id'),
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
    def on_account_move_update(self, record, fields):
        if record.sf_id not in [False, None, '']:
            rest_request = self.env['salesforce.rest.config'].build_request(record, fields, 'update', 'account_move_update')
            if rest_request:
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                rest_response = None
                match rest_request['method']:
                    case 'PATCH':
                        rest_response = SalesforceRestUtils.patch(rest_request['url'],rest_request['headers'],rest_request['body'])
                    case 'PUT':
                        rest_response = SalesforceRestUtils.put(rest_request['url'],rest_request['headers'],rest_request['body'])
                
                SalesforceRestUtils.update_sf_integration_status(record, rest_response, context_with_skip_sync)

    @skip_if(lambda self: not self)
    def on_account_move_delete(self,record, record_id):
        if record.sf_id not in [False, None, '']:
            rest_request = self.env['salesforce.rest.config'].build_request(record, None, 'delete', 'account_move_delete')
            if rest_request:
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                rest_response = SalesforceRestUtils.delete(rest_request['url'],rest_request['headers'])
                SalesforceRestUtils.update_sf_integration_status(record, rest_response, context_with_skip_sync)