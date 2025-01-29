import requests
import logging

_logger = logging.getLogger(__name__)

from odoo import models, api, fields
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if
from datetime import date, datetime


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'


    @api.model
    def create(self, vals):
        account_move_line = super(AccountMoveLine, self).create(vals)
        self._event('on_account_move_line_create').notify(account_move_line,fields=vals.keys())
        return account_move_line
    
    @api.model
    def write(self, vals):
        if self.env.context.get('skip_sync'):
            super(AccountMoveLine, self).write(vals)
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
        super(AccountMoveLine, self.with_context(context_with_skip_sync)).write(vals)
        if len(changed_fields) > 0:
            self._event('on_account_move_line_update').notify(self, changed_fields)

        print("Account Move Line Update")
        print(self)
        return self
    
    @api.model
    def unlink(self):
        self._event('on_account_move_line_delete').notify(self, self.id)
        account_move_line = super(AccountMoveLine, self).unlink()
        return account_move_line
    


class AccountMoveLineListener(Component):
    _name = 'account.move.line.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['account.move.line']


    @skip_if(lambda self, record, fields: not record or not fields)
    def on_account_move_line_create(self, record, fields):
        print("Fields")
        print(fields)
        rest_request = self.env['salesforce.rest.config'].build_rest_request_create(record, fields, 'account_move_line_create')
        if rest_request:
            rest_response = self.env['salesforce.rest.config'].post(rest_request['url'],rest_request['headers'],rest_request['fields'])
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            print("Response")
            print(rest_response)
            if rest_response.status_code == 201:
                record.with_context(context_with_skip_sync).write({
                    'sf_id': rest_response.json()['id'],
                    'sf_integration_status': 'success',
                    'sf_integration_datetime': datetime.now()
                })
            else:
                _logger.error(f"Failed to update Salesforce record: {rest_response.content}")
                record.with_context(context_with_skip_sync).write({
                    'sf_integration_status': 'failed',
                    'sf_integration_datetime': datetime.now(),
                    'sf_integration_error': rest_response.json()
                })


    @skip_if(lambda self, record, fields: not record or not fields)
    def on_account_move_line_update(self, record, fields):
        print("Fields")
        print(fields)
        for line in record:
            if line.sf_id not in [False, None, '']:
                rest_request = self.env['salesforce.rest.config'].build_rest_request_update(line, fields, 'account_move_line_update')
                if rest_request:
                    context_with_skip_sync = dict(self.env.context, skip_sync=True)
                    rest_response = self.env['salesforce.rest.config'].post(rest_request['url'],rest_request['headers'],rest_request['fields'])
                    print("Response")
                    print(rest_response)
                    if rest_response.status_code == 204:
                        line.with_context(context_with_skip_sync).write({
                            'sf_integration_status': 'success',
                            'sf_integration_datetime': datetime.now()
                        })
                    else:
                        _logger.error(f"Failed to update Salesforce record: {rest_response.content}")
                        line.with_context(context_with_skip_sync).write({
                            'sf_integration_status': 'failed',
                            'sf_integration_datetime': datetime.now(),
                            'sf_integration_error': rest_response.json()
                        })

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_account_move_line_delete(self,record, record_id):
        print("record_id")
        print(record_id)
        if record.sf_id not in [False, None, '']:
            rest_request = self.env['salesforce.rest.config'].build_rest_request_delete(record.sf_id,'crm_lead_delete')
            if rest_request:
                rest_response = self.env['salesforce.rest.config'].delete(rest_request['url'],rest_request['headers'])
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                print("Response")
                print(rest_response)
                if rest_response.status_code != 204:
                    _logger.error(f"Failed to update Salesforce record: {rest_response.content}")
                    record.with_context(context_with_skip_sync).write({
                        'sf_integration_status': 'failed',
                        'sf_integration_datetime': datetime.now(),
                        'sf_integration_error': rest_response.json()
                    })