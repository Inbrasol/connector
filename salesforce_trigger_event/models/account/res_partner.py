import requests
import logging
import json

_logger = logging.getLogger(__name__)

from odoo import models, fields, api
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if
from datetime import date

class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def create(self, vals):
        partner = super(ResPartner, self).create(vals)
        self._event('on_res_partner_create').notify(partner, fields=vals.keys())
        return partner
    
    @api.model
    def write(self, vals):
        changed_fields = []
        for field, value in vals.items():
            if self[field] != value:
                    changed_fields.append(field)
        print("Res Partner Update")
        print(changed_fields)
        result = super(ResPartner, self).write(vals)
        if len(changed_fields) > 0:
            self._event('on_res_partner_update').notify(self, changed_fields)
        return result
    
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
        rest_request = self.env['salesforce.rest.config'].build_rest_request_create(record,fields,'res_partner_create')
        if rest_request:
            rest_response = self.env['salesforce.rest.config'].post(rest_request['url'],rest_request['headers'],rest_request['fields'])
            print("Response")
            print(rest_response)
            if rest_response.status_code != 201:
                _logger.error(f"Failed to update Salesforce record: {rest_response.content}")
            else:
                record.write({'sf_id':rest_response.json()['id']})

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_res_partner_update(self, record, fields):
        print("Fields")
        print(fields)
        if record.sf_id not in [False, None, '']:
            rest_request = self.env['salesforce.rest.config'].build_rest_request_update(record,fields,'res_partner_update')
            if rest_request:
                rest_response = self.env['salesforce.rest.config'].patch(rest_request['url'],rest_request['headers'],rest_request['fields'])
                print("Response")
                print(rest_response)
                if rest_response.status_code != 204:
                    _logger.error(f"Failed to update Salesforce record: {rest_response.content}")

    @skip_if(lambda self: not self)
    def on_res_partner_delete(self,record,record_id):
        print("record_id")
        print(record_id)
        if record.sf_id not in [False, None, '']:
            rest_request = self.env['salesforce.rest.config'].build_rest_request_delete(record_id,'res_partner_delete')
            if rest_request:
                rest_response = self.env['salesforce.rest.config'].delete(rest_request['url'],rest_request['headers'])
                print("Response")
                print(rest_response)
                if rest_response.status_code != 204:
                    _logger.error(f"Failed to update Salesforce record: {rest_response.content}")