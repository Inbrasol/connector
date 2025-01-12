import requests
import logging

_logger = logging.getLogger(__name__)

from odoo import models, api
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if



class AccountMoveiine(models.Model):
    _inherit = 'account.move.line'

    @api.model
    def create(self, vals):
        account_move_line = super(AccountMoveiine, self).create(vals)
        self._event('on_account_move_line_create').notify(account_move_line,fields=vals.keys())
        return account_move_line
    
    def write(self, vals):
        account_move_line = super(AccountMoveiine, self).write(vals)
        changed_fields = []
        for field, value in vals.items():
            if self[field] != value:
                    changed_fields.append(field)
        self._event('on_account_move_line_update').notify(account_move_line, changed_fields)
        return account_move_line
    
    def unlink(self):
        for account_move_line in self:
            self._event('on_account_move_line_delete').notify(account_move_line, fields=None)
        return super(AccountMoveiine, self).unlink()
    


class AccountMoveLineListener(Component):
    _name = 'account.move.line.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['account.move.line']


    @skip_if(lambda self, record, fields: not record or not fields)
    def on_account_move_line_create(self, record, fields=None):
        print("Fields")
        print(fields)
        rest_request = self.env['salesforce.rest.config'].build_rest_request_create(record, fields, 'account_move_line_create')
        if rest_request:
            rest_response = self.env['salesforce.rest.config'].post(rest_request['url'],rest_request['headers'],rest_request['fields'])
            print("Response")
            print(rest_response)
            if rest_response.status_code == 201:
                record.write({'sf_id':rest_response.json()['id']})
            else:
                _logger.error(f"Failed to update Salesforce record: {rest_response.content}")
    

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_account_move_line_update(self, record, fields):
        print("Fields")
        print(fields)
        rest_request = self.env['salesforce.rest.config'].build_rest_request_create(record, fields, 'account_move_line_update')
        if rest_request:
            rest_response = self.env['salesforce.rest.config'].post(rest_request['url'],rest_request['headers'],rest_request['fields'])
            print("Response")
            print(rest_response)
            if rest_response.status_code == 204:
                record.write({'sf_id':rest_response.json()['id']})
            else:
                _logger.error(f"Failed to update Salesforce record: {rest_response.content}")


    @skip_if(lambda self: not self)
    def on_account_move_line_delete(self,record_id):
        print("record_id")
        print(record_id)
        rest_request = self.env['salesforce.rest.config'].build_rest_request_delete(record_id,'crm_lead_delete')
        if rest_request:
            rest_response = self.env['salesforce.rest.config'].delete(rest_request['url'],rest_request['headers'])
            print("Response")
            print(rest_response)
            if rest_response.status_code != 204:
                _logger.error(f"Failed to update Salesforce record: {rest_response.content}")