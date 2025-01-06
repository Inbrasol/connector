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
    
    @api.multi
    def write(self, vals):
        partner = super(ResPartner, self).write(vals)
        changed_fields = []
        for field, value in vals.items():
            if partner[field] != value:
                changed_fields.append(field)
        self._event('on_res_partner_update').notify(partner, changed_fields)
        return partner
    
    @api.multi
    def unlink(self):
        partner_ids = self.ids
        partner = super(ResPartner, self).unlink()
        for partner_id in partner_ids:
            self._event('on_res_partner_delete').notify(partner_id)
        return partner


class SalesforcePartnerListener(Component):
    _name = 'salesforce.partner.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['res.partner']

    
    """
    @skip_if(lambda self, fields:  not fields)
    def on_res_partner_create(self, record, fields):
        salesforce_config = self.env['salesforce.rest.config'].search([('name', '=', 'res_partner_create')], limit=1)
        if not salesforce_config:
            return
        backend = self.env["salesforce.backend"].search([('id', '=', salesforce_config.salesforce_backend_id.id)], limit=1)
        authenticate = backend.authenticate()
        if authenticate['access_token'] is not None:
            endpoint = salesforce_config.endpoint
            version = salesforce_config.version
            sobject_api_name = salesforce_config.sobject_api_name  # Assuming the SObject API name is Opportunity
            url = f"{endpoint}/services/data/v{version}/sobjects/{sobject_api_name}/{self.sf_id}"
            
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {authenticate['access_token']}"
            }

            field_salesforce_mapping = {
                'name': 'Name',
                'vat': 'IdentificationNumber__c',
                'phone': 'Phone',
                'mobile': 'MobilePhone',
                'email': 'Email__c',
                'website': 'Website',
            }

            field_salesforce_relationship = {
                'l10n_latam_identification_type_id': 'IdentificationType__c',
                'company_id': 'Territory',
            }

            fields_to_update = {}
            for field in fields:
                if field in field_salesforce_mapping:
                    print("Field")
                    print(field)
                    print("record[field]")
                    print(record[field])
                    print("field_salesforce_mapping[field]")
                    print(field_salesforce_mapping[field])
                    fields_to_update[field_salesforce_mapping[field]] = getattr(record,field)
                elif field in field_salesforce_relationship:
                    fields_to_update[field_salesforce_relationship[field]] =  getattr(record,field).sf_id

            print("fields_to_update")
            print(fields_to_update)
            fields_to_update_json = json.dumps(fields_to_update, default=self.json_serial)
            print("fields_to_update_json")
            print(fields_to_update_json)
            response = requests.patch(url, headers=headers, data=fields_to_update_json)
            if response.status_code != 204:
                _logger.error(f"Failed to update Salesforce record: {response.content}")
            print("Response")
            print(response)
    """


    @skip_if(lambda self, record, fields: not record or not fields)
    def on_res_partner_create(self, record, fields=None):
        print("Fields")
        print(fields)
        rest_request = self.env['salesforce.rest.config'].build_rest_request_create(record,fields,'res_partner_create')
        if rest_request:
            rest_response = self.env['salesforce.rest.config'].post(rest_request['url'],rest_request['headers'],rest_request['fields'])
            print("Response")
            print(rest_response)
            if rest_response.status_code != 204:
                _logger.error(f"Failed to update Salesforce record: {rest_response.content}")
            else:
                record.write({'sf_id':rest_response.json()['id']})


    @skip_if(lambda self, record, fields: not record or not fields)
    def on_res_partner_update(self, record, fields=None):
        print("Fields")
        print(fields)
        rest_request = self.env['salesforce.rest.config'].build_rest_request_update(record,fields,'res_partner_update')
        if rest_request:
            rest_response = self.env['salesforce.rest.config'].patch(rest_request['url'],rest_request['headers'],rest_request['fields'])
            print("Response")
            print(rest_response)
            if rest_response.status_code != 204:
                _logger.error(f"Failed to update Salesforce record: {rest_response.content}")


    @skip_if(lambda self: not self)
    def on_res_partner_delete(self,record_id):
        print("record_id")
        print(record_id)
        rest_request = self.env['salesforce.rest.config'].build_rest_request_delete(record_id,'res_partner_delete')
        if rest_request:
            rest_response = self.env['salesforce.rest.config'].delete(rest_request['url'],rest_request['headers'])
            print("Response")
            print(rest_response)
            if rest_response.status_code != 204:
                _logger.error(f"Failed to update Salesforce record: {rest_response.content}")