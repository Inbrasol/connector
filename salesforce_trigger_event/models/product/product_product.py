import requests
import logging

_logger = logging.getLogger(__name__)

from odoo import models, api
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if

class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def create(self, vals):
        product = super(ProductProduct, self).create(vals)
        self._event('on_product_create').notify(product)
        return product

    def write(self, vals):
        res = super(ProductProduct, self).write(vals)
        self._event('on_product_write').notify(self)
        return res

    def unlink(self):
        products = self.ids
        res = super(ProductProduct, self).unlink()
        self._event('on_product_unlink').notify(products)
        return res

class ProductProductListener(Component):
    _name = 'product.product.listener'
    _inherit = 'base.connector.listener'
    _apply_on = ['product.product']

    @skip_if(lambda self, fields:  not fields)
    def on_product_create(self, record, fields):
        authenticate = self.env["salesforce.backend"].authenticate()
        if authenticate['access_token']:
            # Your custom logic for update event
            salesforce_config = self.env['salesforce.rest.config'].search([('name', '=', 'sale_order_create')], limit=1)
            if not salesforce_config:
                return

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
                'amount': 'Amount'
            }

            field_salesforce_relationship = {
                'partner_id': 'AccountId',
                'user_id': 'OwnerId',
                'stage_id': 'StageName'
            }

            fields_to_update = []
            for field, value in fields.items():
                if field in field_salesforce_mapping:
                    fields_to_update[field_salesforce_mapping[field]] = value
                elif field in field_salesforce_relationship:
                    fields_to_update[field_salesforce_relationship[field]] = value.sf_id


            response = requests.patch(url, headers=headers, json=fields_to_update)
            if response.status_code != 204:
                _logger.error(f"Failed to update Salesforce record: {response.content}")
            
            self.env["salesforce.rest.log"].create_log(salesforce_config, url, 'PATCH', fields, response)

    @skip_if(lambda self, fields: not fields)
    def on_product_write(self, record, fields):
        # Your custom logic here
        authenticate = self.env["salesforce.backend"].authenticate()
        if authenticate['access_token']:
            # Your custom logic for update event
            salesforce_config = self.env['salesforce.rest.config'].search([('name', '=', 'sale_order_create')], limit=1)
            if not salesforce_config:
                return

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
                'amount': 'Amount'
            }

            field_salesforce_relationship = {
                'partner_id': 'AccountId',
                'user_id': 'OwnerId',
                'stage_id': 'StageName'
            }

            fields_to_update = []
            for field, value in fields.items():
                if field in field_salesforce_mapping:
                    fields_to_update[field_salesforce_mapping[field]] = value
                elif field in field_salesforce_relationship:
                    fields_to_update[field_salesforce_relationship[field]] = value.sf_id


            response = requests.patch(url, headers=headers, json=fields_to_update)
            if response.status_code != 204:
                _logger.error(f"Failed to update Salesforce record: {response.content}")
            
            self.env["salesforce.rest.log"].create_log(salesforce_config, url, 'PATCH', fields, response)

    @skip_if(lambda self: not self)
    def on_product_unlink(self):
        authenticate = self.env["salesforce.backend"].authenticate()
        if authenticate['access_token']:
            salesforce_config = self.env['salesforce.rest.config'].search([('name', '=', 'sale_order_delete')], limit=1)
            if not salesforce_config:
                return
            endpoint = salesforce_config.endpoint
            version = salesforce_config.version
            sobject_api_name = salesforce_config.sobject_api_name
            url = f"{endpoint}/services/data/v{version}/sobjects/{sobject_api_name}/{self.sf_id}"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {authenticate['access_token']}"
            }
            response = requests.delete(url, headers=headers)
            if response.status_code != 204:
                _logger.error(f"Failed to delete Salesforce record: {response.content}")
            self.env["salesforce.rest.log"].create_log(salesforce_config, url, 'DELETE', None, response)