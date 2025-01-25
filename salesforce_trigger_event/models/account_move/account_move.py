import requests
import logging

_logger = logging.getLogger(__name__)

from odoo import models, api, fields
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if



class AccountMove(models.Model):
    _inherit = 'account.move'

    #skip_sync = fields.Boolean(string='Skip Sync', default=False, copy=False)

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
        print("Fields")
        print(fields)
        rest_request = self.env['salesforce.rest.config'].build_rest_request_create(record, fields, 'account_move_create')
        if rest_request:
            rest_response = self.env['salesforce.rest.config'].post(rest_request['url'],rest_request['headers'],rest_request['fields'])
            print("Response")
            print(rest_response)
            print("Responde JSON")
            print(rest_response.json())
            if rest_request['type'] == 'composite':
                if rest_response.status_code in [200, 201]:
                    for record_response in rest_response.json()['compositeResponse']:
                        if record_response['httpStatusCode'] in [200, 201] and record_response['referenceId'] in  rest_request['map_ref_fields'].keys():
                            map_field = rest_request['map_ref_fields'][record_response['referenceId']]
                            record_to_update = self.env[map_field['model']].browse(map_field['id'])
                            record_to_update.write({'sf_id': record_response['body']['id']})
                else:
                    _logger.error(f"Failed to update Salesforce record: {rest_response.content}")
            
            elif rest_request['type'] == 'single':
                if rest_response.status_code in [200, 201]:
                    record.write({'sf_id': rest_response.json()['id']})
                else:
                    _logger.error(f"Failed to update Salesforce record: {rest_response.content}")

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_account_move_update(self, record, fields):
        print("Fields")
        print(fields)
        if record.sf_id not in [False, None, '']:
            rest_request = self.env['salesforce.rest.config'].build_rest_request_update(record, fields, 'account_move_update')
            if rest_request:
                rest_response = None
                match rest_request['method']:
                    case 'PATCH':
                        rest_response = self.env['salesforce.rest.config'].patch(rest_request['url'],rest_request['headers'],rest_request['fields'])
                    case 'PUT':
                        rest_response = self.env['salesforce.rest.config'].put(rest_request['url'],rest_request['headers'],rest_request['fields'])
                
                if rest_response and rest_response.status_code != 204:
                    _logger.error(f"Failed to update Salesforce record: {rest_response.content}")
                
    @skip_if(lambda self: not self)
    def on_account_move_delete(self,record, record_id):
        print("record_id")
        print(record_id)
        if record.sf_id not in [False, None, '']:
            rest_request = self.env['salesforce.rest.config'].build_rest_request_delete(record.sf_id,'account_move_delete')
            if rest_request:
                rest_response = self.env['salesforce.rest.config'].delete(rest_request['url'],rest_request['headers'])
                print("Response")
                print(rest_response)
                if rest_response.status_code != 204:
                    _logger.error(f"Failed to update Salesforce record: {rest_response.content}")