import requests
import logging
import json

_logger = logging.getLogger(__name__)

from odoo import models, fields, api
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if
from datetime import date, datetime, timedelta
from ..backend.salesforce_rest_utils import SalesforceRestUtils

class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def create_lines_to_sf_by_cron(self):
        _logger.error("cron: %s", self)
        related_model = self.env['res.partner']
        fields = related_model._fields.keys()
        customer_category = self.env['res.partner.category'].search([('name', '=', 'Cliente')], limit=1)
        if not customer_category:
            _logger.error("Customer category not found")
            return self
        
        lines_create = related_model.search([
            '|',
            ('sf_id', '=', False),
            ('sf_id', '=', ''), 
            ('category_id', 'in', customer_category.ids),
            ('is_company', '=', True),
            ('company_id', '!=', False)
        ], limit=201)
        
        _logger.error("product_lines_create: %s", lines_create)
        
        if not lines_create:
            return self

        # Limit the number of product lines to process to a maximum of 200
        lines_to_process = lines_create[:min(len(lines_create), 200)]

        self._event('on_res_partner_create').notify(lines_to_process, fields)

        # If there are more than 200 product lines, schedule the next batch
        if len(lines_create) > 200:
            cron_job = self.env.ref('salesforce_trigger_event.ir_cron_create_res_partner_to_sf')
            next_call_time = (datetime.now() + timedelta(minutes=2)).strftime('%Y-%m-%d %H:%M:%S')
            cron_job.write({'nextcall': next_call_time})

    @api.model
    def create_contact_lines_to_sf(self, lines):
        _logger.error("cron: %s", self)
        related_model = self.env['res.partner']
        fields = related_model._fields.keys()
        customer_category = self.env['res.partner.category'].search([('name', '=', 'Cliente')], limit=1)
        if not customer_category:
            _logger.error("Customer category not found")
            return self
        
        lines_create = related_model.search([
            '|',
            ('sf_id', '=', False),
            ('sf_id', '=', ''), 
            ('parent_id.sf_id', '!=', False),
            ('parent_id.category_id', 'in', customer_category.ids),
            ('is_company', '=', False),
        ], limit=201)
        _logger.error("contact_lines_to_create: %s", lines_create)

        if not lines_create:
            return self

        # Limit the number of product lines to process to a maximum of 200
        lines_to_process = lines_create[:min(len(lines_create), 200)]

        self._event('on_res_partner_contact_create').notify(lines_to_process, fields)

        # If there are more than 200 product lines, schedule the next batch
        if len(lines_create) > 200:
            cron_job = self.env.ref('salesforce_trigger_event.ir_cron_create_contact_res_partner_to_sf')
            next_call_time = (datetime.now() + timedelta(minutes=2)).strftime('%Y-%m-%d %H:%M:%S')
            cron_job.write({'nextcall': next_call_time})


    def create(self, vals):
        if len(self) > 1:
            return super(ResPartner, self).create(vals)

        if self.env.context.get('skip_sync'):
            return super(ResPartner, self).create(vals)
        
        if self.sf_id not in [False, None, '']:
            _logger.error("sf_id is empty, skipping create")
            return super(ResPartner, self).create(vals)

        partner = super(ResPartner, self).create(vals)
        self._event('on_res_partner_create').notify(partner, fields=vals.keys())
        return partner
    
    def write(self, vals):
        _logger.error(f"Update: {vals}")
        if len(self) > 1:
            return super(ResPartner, self).write(vals)
        
        if self.env.context.get('skip_sync'):
            return super(ResPartner, self).write(vals)
        
        if self.sf_id in [False, None, '']:
            _logger.error("sf_id is empty, skipping write")
            return super(ResPartner, self).write(vals)
    
        changed_fields = []
        for field, value in vals.items():
            if self._fields[field].type in ['one2many', 'many2many']:
                continue
            elif isinstance(self[field], models.BaseModel):
                if self[field].id != value:
                    changed_fields.append(field)
            elif self[field] != value:
                changed_fields.append(field)

        if len(changed_fields) > 0:
            set_changed_fields = set(changed_fields)
            self._event('on_res_partner_update').notify(self, set_changed_fields)
        
        context_with_skip_sync = dict(self.env.context, skip_sync=True)
        return super(ResPartner, self.with_context(context_with_skip_sync)).write(vals)

    def unlink(self):
        _logger.error("→ Intentando eliminar res.partner con contexto skip_sync: %s", self.env.context.get('skip_sync'))
        # Buscar los sf_ids de los registros que se quieren eliminar
        partners = self.env['res.partner'].browse(self.ids)
        sf_ids = [sf_id for sf_id in partners.mapped('sf_id') if sf_id]  # Solo valores no vacíos

        _logger.error("→ sf_ids encontrados: %s", sf_ids)
        if len(sf_ids) == 0:
            _logger.error("→ No se encontraron sf_ids, se eliminará normalmente.")
            return super(ResPartner, self).unlink()
        else:
            _logger.error("→ Se encontraron sf_ids, notificando evento antes de eliminar.")
            self._event('on_res_partner_delete').notify(sf_ids)
            return super(ResPartner, self).unlink()


class SalesforcePartnerListener(Component):
    _name = 'salesforce.partner.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['res.partner']


    @skip_if(lambda self, record, fields: not record or not fields)
    def on_res_partner_create(self, record, fields):
        context_with_skip_sync = dict(self.env.context, skip_sync=True)
        rest_request = self.env['salesforce.rest.config'].build_request(record,fields,'create','res_partner_create')
        if rest_request:
            rest_response = SalesforceRestUtils.post(rest_request['url'],rest_request['headers'],rest_request['body'])
            if rest_response and rest_response.status_code in [200, 201]:
                SalesforceRestUtils._handle_successful_response(self, rest_request, rest_response, context_with_skip_sync)
            else:
                SalesforceRestUtils._handle_failed_response(record, rest_response, context_with_skip_sync)

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_res_partner_contact_create(self, record, fields):
        context_with_skip_sync = dict(self.env.context, skip_sync=True)
        rest_request = self.env['salesforce.rest.config'].build_request(record,fields,'create','res_partner__contact_create')
        if rest_request:
            rest_response = SalesforceRestUtils.post(rest_request['url'],rest_request['headers'],rest_request['body'])
            if rest_response and rest_response.status_code in [200, 201]:
                SalesforceRestUtils._handle_successful_response(self, rest_request, rest_response, context_with_skip_sync)
            else:
                SalesforceRestUtils._handle_failed_response(record, rest_response, context_with_skip_sync)


    @skip_if(lambda self, record, fields: not record or not fields)
    def on_res_partner_update(self, record, fields):
        print("Fields")
        print(fields)
        _logger.error(f"Fields Before: {fields}")
        if record.sf_id not in [False, None, '']:
            rest_request = self.env['salesforce.rest.config'].build_request(record,fields,'update','res_partner_update')
            if rest_request:
                rest_response = SalesforceRestUtils.patch(rest_request['url'],rest_request['headers'],rest_request['body'])
                _logger.error(f"Failed to update Salesforce record: {rest_response}")
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                SalesforceRestUtils._update_sf_integration_status(record, rest_response, context_with_skip_sync)


    @skip_if(lambda self, records: not records)
    def on_res_partner_delete(self, records):
        rest_request = self.env['salesforce.rest.config'].build_request(records, None, 'delete', 'res_partner_delete')
        if rest_request:
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            rest_response = SalesforceRestUtils.delete(rest_request['url'], rest_request['headers'])
            
            if rest_response and rest_response.status_code in [200, 201]:
                SalesforceRestUtils._update_sf_integration_status(records, rest_response, context_with_skip_sync)
            else:
                SalesforceRestUtils._handle_failed_response(records, rest_response, context_with_skip_sync)