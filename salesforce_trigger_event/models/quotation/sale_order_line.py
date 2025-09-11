import requests
import logging
import json

_logger = logging.getLogger(__name__)

from odoo import models, fields, api
from datetime import date, datetime, timedelta

from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if
from ..backend.salesforce_rest_utils import SalesforceRestUtils

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.model
    def create_lines_to_sf_by_cron(self):
        _logger.error("cron: %s", self)
        related_model = self.env['sale.order.line']
        fields = related_model._fields.keys()
        lines_create = related_model.search([
            '|',
            ('sf_id', '=', False),
            ('sf_id', '=', ''), 
            ('order_id.sf_id', '!=', False),
            ('product_id.sf_id', '!=', False),
        ], limit=201)
        
        _logger.error("sale_order_lines: %s", lines_create)
        
        if not lines_create:
            return self

        # Limit the number of product lines to process to a maximum of 200
        lines_to_process = lines_create[:min(len(lines_create), 200)]

        self._event('on_sale_order_line_create').notify(lines_to_process, fields)

        # If there are more than 200 product lines, schedule the next batch
        if len(lines_create) > 200:
            cron_job = self.env.ref('salesforce_trigger_event.ir_cron_create_sale_order_line_to_sf')
            next_call_time = (datetime.now() + timedelta(minutes=2)).strftime('%Y-%m-%d %H:%M:%S')
            cron_job.write({'nextcall': next_call_time})

        return self
    
    @api.model
    def sync_lines_to_sf_by_cron(self):
        _logger.error("cron: %s", self)
        related_model = self.env['sale.order.line']
        # Buscar líneas que aún no tienen sf_id pero cumplen condiciones
        lines_to_sync = related_model.search([
            '|',
            ('sf_id', '=', False),
            ('sf_id', '=', ''), 
            ('order_id.sf_id', '!=', False)
        ], limit=201)
        
        _logger.error("quote lines to sync: %s", lines_to_sync)
        
        if not lines_to_sync:
            return self

        # Limitar a 200 registros por lote
        lines = lines_to_sync[:200]
        odoo_ids = [str(l.id) for l in lines]
        if not odoo_ids:
            return self

        # Consultar en Salesforce por Odoo_Id__c en QuoteLineItem
        query = (
            "SELECT+Id,Odoo_Id__c+"
            "FROM+QuoteLineItem+WHERE+Odoo_Id__c+IN+('{}')"
        ).format("','".join(odoo_ids))
        request_qli = self.env['salesforce.rest.config'].build_request(query, None, 'query', 'quote_line_item_query')
        
        _logger.error(f"GET request url: {request_qli}")
        response = requests.get(request_qli['url'], headers=request_qli['headers'])
        _logger.error(f"GET response: {response}")
        _logger.error(f"GET response: {response.text}")
        
        context_with_skip_sync = dict(self.env.context, skip_sync=True)
        updates = []

        if response.status_code == 200:
            records = response.json().get('records', [])
            for record in records:
                odoo_id = int(record['Odoo_Id__c'])
                updates.append((odoo_id, {
                    'sf_id': record['Id'],
                }))
        
        # Actualizar solo el campo sf_id en Odoo
        for odoo_id, vals in updates:
            related_model.browse(odoo_id).with_context(context_with_skip_sync).write(vals)

        # Si hay más de 200, reprogramar el cron
        if len(lines_to_sync) > 200:
            cron_job = self.env.ref('salesforce_trigger_event.ir_cron_sync_sale_order_line_to_sf')
            next_call_time = (datetime.now() + timedelta(minutes=2)).strftime('%Y-%m-%d %H:%M:%S')
            cron_job.write({'nextcall': next_call_time})

        return self 
    
    """
    def create(self, vals):
        if self.env.context.get('skip_sync'):
            return super(SaleOrderLine, self).create(vals)
        
        line = super(SaleOrderLine, self).create(vals)
        fields = self._fields.keys()
        self._event('on_sale_order_line_create').notify(line, fields=fields)
        return line
    
    @api.model
    def write(self, vals):
        _logger.error("on_sale_order_line_update initi: %s", vals)
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
        _logger.error("on_sale_order_line_update: %s", changed_fields) 
        if len(changed_fields) > 0:
            self._event('on_sale_order_line_update').notify(self, changed_fields)
        return self
    """
    

    def unlink(self):
        _logger.error("→ Intentando eliminar sale.order.line con contexto skip_sync: %s", self.env.context.get('skip_sync'))
        # Buscar los sf_ids de las líneas que se quieren eliminar
        sale_order_lines = self.env['sale.order.line'].browse(self.ids)
        sf_ids = [sf_id for sf_id in sale_order_lines.mapped('sf_id') if sf_id]  # Solo valores no vacíos

        _logger.error("→ sf_ids encontrados: %s", sf_ids)
        if len(sf_ids) == 0:
            _logger.error("→ No se encontraron sf_ids, se eliminará normalmente.")
            return super(SaleOrderLine, self).unlink()
        else:
            _logger.error("→ Se encontraron sf_ids, notificando evento antes de eliminar.")
            self._event('on_sale_order_line_delete').notify(sf_ids)
            return super(SaleOrderLine, self).unlink()
    

class SaleOrderLineListener(Component):
    _name = 'sale.order.line.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['sale.order.line']
    
    
    @skip_if(lambda self, record, fields: not record or not fields)
    def on_sale_order_line_create(self, record, fields):
        rest_request = self.env['salesforce.rest.config'].build_request(record, fields, 'create', 'sale_order_line_create')
        if rest_request:
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            rest_response = SalesforceRestUtils.post(rest_request['url'],rest_request['headers'],rest_request['body'])

            if rest_response and rest_response.status_code in [200, 201]:
                SalesforceRestUtils._handle_successful_response(self, rest_request, rest_response, context_with_skip_sync)
            else:
                SalesforceRestUtils._handle_failed_response(self, rest_request, rest_response, context_with_skip_sync)

    @skip_if(lambda self, records, fields: not records or not fields)
    def on_sale_order_line_update(self, records, fields):
        rest_request = self.env['salesforce.rest.config'].build_request(records, fields, 'update', 'sale_order_line_update')
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
                SalesforceRestUtils._handle_failed_response(self, rest_request, rest_response, context_with_skip_sync)


    @skip_if(lambda self, records: not records)
    def on_sale_order_line_delete(self, records):
        rest_request = self.env['salesforce.rest.config'].build_request(records, None, 'delete', 'sale_order_line_delete')
        if rest_request:
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            rest_response = SalesforceRestUtils.delete(rest_request['url'], rest_request['headers'])
            if rest_response and rest_response.status_code not in [200, 201]:
                SalesforceRestUtils._handle_failed_response(self, rest_request, rest_response, context_with_skip_sync)