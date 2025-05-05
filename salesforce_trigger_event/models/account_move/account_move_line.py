import requests
import logging

_logger = logging.getLogger(__name__)

from odoo import models, api, fields
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if
from datetime import date, datetime, timedelta
from ..backend.salesforce_rest_utils import SalesforceRestUtils


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.model
    def create_lines_to_sf_by_cron(self):
        _logger.error("cron: %s", self)
        related_model = self.env['account.move.line']
        fields = related_model._fields.keys()
        lines_create = related_model.search([
            '|',
            ('sf_id', '=', False),
            ('sf_id', '=', ''), 
            ('move_id.sf_id', '!=', False),
            ('parent_state', '=', 'posted'),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
        ], limit=201)
        
        _logger.error("product_lines_create: %s", lines_create)
        
        if not lines_create:
            return self

        # Limit the number of product lines to process to a maximum of 200
        lines_to_process = lines_create[:min(len(lines_create), 200)]

        self._event('on_account_move_line_create').notify(lines_to_process, fields)

        # If there are more than 200 product lines, schedule the next batch
        if len(lines_create) > 200:
            cron_job = self.env.ref('salesforce_trigger_event.ir_cron_create_account_move_line_to_sf')
            next_call_time = (datetime.now() + timedelta(minutes=2)).strftime('%Y-%m-%d %H:%M:%S')
            cron_job.write({'nextcall': next_call_time})

        return self
    
    """
    def create(self, vals):
        if self.env.context.get('skip_sync'):
            return super(AccountMoveLine, self).create(vals)
        
        account_move_line = super(AccountMoveLine, self).create(vals)
        fields = self._fields.keys()
        self._event('on_account_move_line_create').notify(account_move_line,fields=fields)
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
    """

    def unlink(self):
        _logger.error("→ Intentando eliminar account.move.line con contexto skip_sync: %s", self.env.context.get('skip_sync'))
        # Buscar los sf_ids de las líneas que se quieren eliminar
        account_move_lines = self.env['account.move.line'].browse(self.ids)
        sf_ids = [sf_id for sf_id in account_move_lines.mapped('sf_id') if sf_id]  # Solo valores no vacíos

        _logger.error("→ sf_ids encontrados: %s", sf_ids)
        if len(sf_ids) == 0:
            _logger.error("→ No se encontraron sf_ids, se eliminará normalmente.")
            return super(AccountMoveLine, self).unlink()
        else:
            _logger.error("→ Se encontraron sf_ids, notificando evento antes de eliminar.")
            self._event('on_account_move_line_delete').notify(sf_ids)
            return super(AccountMoveLine, self).unlink()


class AccountMoveLineListener(Component):
    _name = 'account.move.line.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['account.move.line']


    @skip_if(lambda self, record, fields: not record or not fields)
    def on_account_move_line_create(self, record, fields):
        rest_request = self.env['salesforce.rest.config'].build_request(record, fields, 'create', 'account_move_line_create')
        if rest_request:
            rest_response = SalesforceRestUtils.post(rest_request['url'],rest_request['headers'],rest_request['body'])
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            if rest_response and rest_response.status_code in [200, 201]:
                SalesforceRestUtils._handle_successful_response(self, rest_request, rest_response, context_with_skip_sync)
            else:
                SalesforceRestUtils._handle_failed_response(record, rest_response, context_with_skip_sync)

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_account_move_line_update(self, record, fields):
        rest_request = self.env['salesforce.rest.config'].build_request(record, fields, 'update', 'account_move_line_update')
        if rest_request:
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            rest_response = None
            match rest_request['method']:
                case 'PATCH':
                    rest_response = SalesforceRestUtils.patch(rest_request['url'], rest_request['headers'], rest_request['body'])
                case 'PUT':
                    rest_response = SalesforceRestUtils.put(rest_request['url'], rest_request['headers'], rest_request['body'])
            
            if rest_response and rest_response.status_code in [200, 201]:
                SalesforceRestUtils._handle_successful_response(self, rest_request, rest_response, context_with_skip_sync)
            else:
                SalesforceRestUtils._handle_failed_response(record, rest_response, context_with_skip_sync)

    @skip_if(lambda self, records: not records)
    def on_account_move_line_delete(self,records):
        rest_request = self.env['salesforce.rest.config'].build_request(records, None, 'delete', 'account_move_line_delete')
        if rest_request:
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            rest_response = SalesforceRestUtils.delete(rest_request['url'], rest_request['headers'])
            
            if rest_response and rest_response.status_code in [200, 201]:
                SalesforceRestUtils._handle_successful_response(self, rest_request, rest_response, context_with_skip_sync)
            else:
                SalesforceRestUtils._handle_failed_response(records, rest_response, context_with_skip_sync)