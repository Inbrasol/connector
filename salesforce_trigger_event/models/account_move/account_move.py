import requests
import logging

_logger = logging.getLogger(__name__)

from odoo import models, api, fields
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if
from datetime import date, datetime, timedelta
from ..backend.salesforce_rest_utils import SalesforceRestUtils

class AccountMove(models.Model):
    _inherit = 'account.move'


    @api.model
    def create_lines_to_sf_by_cron(self):
        _logger.error("cron: %s", self)
        related_model = self.env['account.move']
        fields = related_model._fields.keys()
        lines_create = related_model.search([
            ('sf_id', '=', False),
            ('sale_order_id.sf_id', '!=', False),
            ('partner_id.commercial_partner_id.sf_id', '!=', False),
            ('state', '=', 'posted'),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
        ], limit=201)
        
        _logger.error("product_lines_create: %s", lines_create)
        
        if not lines_create:
            return self

        # Limit the number of product lines to process to a maximum of 200
        lines_to_process = lines_create[:min(len(lines_create), 200)]

        self._event('on_account_move_create_bulk').notify(lines_to_process, fields)

        # If there are more than 200 product lines, schedule the next batch
        if len(lines_create) > 200:
            cron_job = self.env.ref('salesforce_trigger_event.ir_cron_create_account_move_to_sf')
            next_call_time = (datetime.now() + timedelta(minutes=2)).strftime('%Y-%m-%d %H:%M:%S')
            cron_job.write({'nextcall': next_call_time})

        return self
        
    def create_lines_to_sf(self):
        _logger.error("create_lines_to_sf: %s", self)
        if self.env.context.get('skip_sync') or  self.sf_id  in [False, None, '']:
            return self
        # Fetch lines that need to be created in Salesforce
        lines_create_ids = self.line_ids.filtered(lambda line: not line.sf_id).ids
        if not lines_create_ids:
            return self
        
        related_model = self.env['account.move.line']
        fields_dict = related_model._fields
        # Filter lines that are not already synced with Salesforce
        lines_create = related_model.search([
            ('id', 'in', lines_create_ids),
            ('sf_id', '=', False),
            ('move_id.sf_id', '!=', False),
            ('product_id.sf_id', '!=', False),
        ], limit=201)
        
        _logger.error("account_move_lines: %s", lines_create)
        
        if not lines_create:
            return self

        # Limit the number of product lines to process to a maximum of 200
        lines_to_process = lines_create[:min(len(lines_create), 200)]
        self.env['account.move.line']._event('on_account_move_line_create').notify(lines_to_process, fields_dict)
        return self
    
    def create(self, vals):
        if self.env.context.get('skip_sync'):
            return super(AccountMove, self).create(vals)
        
        if self.sf_id not in [False, None, '']:
            return super(AccountMove, self).create(vals)
        
        account_move = super(AccountMove, self).create(vals)
        fields = self._fields.keys()
        self._event('on_account_move_create').notify(account_move,fields=fields)
        return account_move
    
    def write(self, vals):
        if self.env.context.get('skip_sync'):
            return super(AccountMove, self).write(vals)
        
        if self.sf_id in [False, None, '']:
            return super(AccountMove, self).write(vals)
        
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

        return self
    
    def unlink(self):
        _logger.error("→ Intentando eliminar account.move con contexto skip_sync: %s", self.env.context.get('skip_sync'))
        # Buscar los sf_ids de los registros que se quieren eliminar
        account_moves = self.env['account.move'].browse(self.ids)
        sf_ids = [sf_id for sf_id in account_moves.mapped('sf_id') if sf_id]  # Solo valores no vacíos

        _logger.error("→ sf_ids encontrados: %s", sf_ids)
        if len(sf_ids) == 0:
            _logger.error("→ No se encontraron sf_ids, se eliminará normalmente.")
            return super(AccountMove, self).unlink()
        else:
            _logger.error("→ Se encontraron sf_ids, notificando evento antes de eliminar.")
            self._event('on_account_move_delete').notify(sf_ids)
            return super(AccountMove, self).unlink()
    
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
            SalesforceRestUtils._handle_successful_response(self, rest_request, rest_response, context_with_skip_sync)
        else:
            SalesforceRestUtils._handle_failed_response(record, rest_response, context_with_skip_sync)

    def _send_rest_request(self, rest_request):
        if rest_request['type'] in ['rest', 'composite_tree', 'composite']:
            return SalesforceRestUtils.post(rest_request['url'], rest_request['headers'], rest_request['body'])
        _logger.warning(f"Unsupported request type: {rest_request['type']}")
        return None
    
    @skip_if(lambda self, records, fields: not records or not fields)
    def on_account_move_create_bulk(self, records, fields):
        rest_request = self.env['salesforce.rest.config'].build_request(records, fields, 'create', 'account_move_create_bulk')
        if rest_request:
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            rest_response = SalesforceRestUtils.post(rest_request['url'], rest_request['headers'], rest_request['body'])
            if rest_response and rest_response.status_code in [200, 201]:
                SalesforceRestUtils._handle_successful_response(self, rest_request, rest_response, context_with_skip_sync)
            else:
                SalesforceRestUtils._handle_failed_response(records, rest_response, context_with_skip_sync)
    

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
                
                SalesforceRestUtils._update_sf_integration_status(record, rest_response, context_with_skip_sync)

    @skip_if(lambda self, records: not records)
    def on_account_move_delete(self, records):
        rest_request = self.env['salesforce.rest.config'].build_request(records, None, 'delete', 'account_move_delete')
        if rest_request:
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            rest_response = SalesforceRestUtils.delete(rest_request['url'], rest_request['headers'])
            SalesforceRestUtils._handle_successful_response(self, rest_request, rest_response, context_with_skip_sync)