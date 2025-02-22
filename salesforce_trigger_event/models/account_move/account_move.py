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

class AccountMoveListener(Component):
    _name = 'account.move.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['account.move']


    @skip_if(lambda self, record, fields: not record or not fields)
    def on_account_move_create(self, record, fields):
        _logger.info("Processing account move creation with fields: %s", fields)
        rest_request = SalesforceRestUtils.build_request(record, fields, 'create', 'account_move_create')
        if not rest_request:
            return

        context_with_skip_sync = dict(self.env.context, skip_sync=True)
        rest_response = SalesforceRestUtils.post(rest_request['url'], rest_request['headers'], rest_request['body'])
        _logger.info("Salesforce response: %s", rest_response.json())

        if rest_request['type'] == 'composite':
            self._handle_composite_response(record, rest_request, rest_response, context_with_skip_sync)
        elif rest_request['type'] == 'single':
            self._handle_single_response(record, rest_response, context_with_skip_sync)

    def _handle_composite_response(self, record, rest_request, rest_response, context):
        if rest_response.status_code in [200, 201]:
            for record_response in rest_response.json().get('compositeResponse', []):
                if record_response['httpStatusCode'] in [200, 201]:
                    self._update_record_with_response(record_response, rest_request, context)
        else:
            self._log_and_update_failure(record, rest_response, context)

    def _handle_single_response(self, record, rest_response, context):
        if rest_response.status_code in [200, 201]:
            record.with_context(context).write({
                'sf_id': rest_response.json().get('id'),
                'sf_integration_status': 'success',
                'sf_integration_datetime': datetime.now()
            })
        else:
            self._log_and_update_failure(record, rest_response, context)

    def _update_record_with_response(self, record_response, rest_request, context):
        reference_id = record_response.get('referenceId')
        if reference_id in rest_request['map_ref_fields']:
            map_field = rest_request['map_ref_fields'][reference_id]
            record_to_update = self.env[map_field['model']].browse(map_field['id'])
            record_to_update.with_context(context).write({
                'sf_id': record_response['body'].get('id'),
                'sf_integration_status': 'success',
                'sf_integration_datetime': datetime.now()
            })

    def _log_and_update_failure(self, record, rest_response, context):
        _logger.error("Failed to update Salesforce record: %s", rest_response.content)
        record.with_context(context).write({
            'sf_integration_status': 'failed',
            'sf_integration_datetime': datetime.now(),
            'sf_integration_error': rest_response.json()
        })

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_account_move_update(self, record, fields):
        if record.sf_id not in [False, None, '']:
            rest_request = SalesforceRestUtils.build_request(record, fields, 'update', 'account_move_update')
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
    def on_account_move_delete(self,record, record_id):
        if record.sf_id not in [False, None, '']:
            rest_request = SalesforceRestUtils.build_request(record, None, 'delete', 'account_move_delete')
            if rest_request:
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                rest_response = SalesforceRestUtils.delete(rest_request['url'],rest_request['headers'])
                SalesforceRestUtils.update_sf_integration_status(record, rest_response.status_code, rest_response.json(), context_with_skip_sync)