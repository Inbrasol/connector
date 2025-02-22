import requests
import logging
import json

_logger = logging.getLogger(__name__)

from odoo import models, fields, api
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if
from datetime import date
from ..backend.salesforce_rest_utils import SalesforceRestUtils

class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def create(self, vals):
        partner = super(ResPartner, self).create(vals)
        self._event('on_res_partner_create').notify(partner, fields=vals.keys())
        return partner
    
    @api.model
    def write(self, vals):
        if self.env.context.get('skip_sync'):
            super(ResPartner, self).write(vals)
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
        super(ResPartner, self.with_context(context_with_skip_sync)).write(vals)
        if len(changed_fields) > 0:
            self._event('on_res_partner_update').notify(self, changed_fields)

        print("Res Partner Update")
        print(self)
        return self
    
    @api.model
    def unlink(self):
        partner = super(ResPartner, self).unlink()
        self._event('on_res_partner_delete').notify(partner,partner.id)
        return partner


class SalesforcePartnerListener(Component):
    _name = 'salesforce.partner.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['res.partner']


    @skip_if(lambda self, record, fields: not record or not fields)
    def on_res_partner_create(self, record, fields):
        print("Fields")
        print(fields)
        context_with_skip_sync = dict(self.env.context, skip_sync=True)
        rest_request = self.env['salesforce.rest.config'].build_request(record,fields,'create','res_partner_create')
        if rest_request:
            rest_response = SalesforceRestUtils.post(rest_request['url'],rest_request['headers'],rest_request['body'])
            SalesforceRestUtils.update_sf_integration_status(record, rest_response.status_code, rest_response.json(), context_with_skip_sync)
            

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_res_partner_update(self, record, fields):
        print("Fields")
        print(fields)
        if record.sf_id not in [False, None, '']:
            rest_request = self.env['salesforce.rest.config'].build_request(record,fields,'update','res_partner_update')
            if rest_request:
                rest_response = SalesforceRestUtils.patch(rest_request['url'],rest_request['headers'],rest_request['body'])
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                SalesforceRestUtils.update_sf_integration_status(record, rest_response.status_code, rest_response.json(), context_with_skip_sync)


    @skip_if(lambda self: not self)
    def on_res_partner_delete(self,record,record_id):
        if record.sf_id not in [False, None, '']:
            rest_request = self.env['salesforce.rest.config'].build_request(record, None,'delete','res_partner_delete')
            if rest_request:
                rest_response = SalesforceRestUtils.delete(rest_request['url'],rest_request['headers'])
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                SalesforceRestUtils.update_sf_integration_status(record, rest_response.status_code, rest_response.json(), context_with_skip_sync)
