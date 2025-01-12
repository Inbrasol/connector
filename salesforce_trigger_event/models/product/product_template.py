import requests
import logging

_logger = logging.getLogger(__name__)

from odoo import models, api
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def create(self, vals):
        product = super(ProductTemplate, self).create(vals)
        self._event('on_product_create').notify(product)
        return product

    def write(self, vals):
        changed_fields = []
        for field, value in vals.items():
            if self[field] != value:
                changed_fields.append(field)
        res = super(ProductTemplate, self).write(vals)
        if len(changed_fields) > 0:
            self._event('on_product_write').notify(self,changed_fields)
        return res

    def unlink(self):
        products = self.ids
        res = super(ProductTemplate, self).unlink()
        for product in products:
            self._event('on_product_unlink').notify(product)
        return res

class ProductProductListener(Component):
    _name = 'product.product.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['product.template']

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_product_create(self, record, fields=None):
        print("Fields")
        print(fields)
        rest_request = self.env['salesforce.rest.config'].build_rest_request_create(record, fields, 'product_template_create')
        if rest_request:
            rest_response = self.env['salesforce.rest.config'].post(rest_request['url'],rest_request['headers'],rest_request['fields'])
            print("Response")
            print(rest_response)
            if rest_response.status_code == 201:
                record.write({'sf_id':rest_response.json()['id']})
            else:
                _logger.error(f"Failed to update Salesforce record: {rest_response.content}")

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_product_write(self, record, fields):
        print("Fields")
        print(fields)
        rest_request = self.env['salesforce.rest.config'].build_rest_request_create(record, fields, 'product_template_update')
        if rest_request:
            rest_response = None
            match rest_request['method']:
                case 'PATCH':
                    rest_response = self.env['salesforce.rest.config'].patch(rest_request['url'],rest_request['headers'],rest_request['fields'])
                case 'PUT':
                    rest_response = self.env['salesforce.rest.config'].put(rest_request['url'],rest_request['headers'],rest_request['fields'])  
            print("Response")
            print(rest_response)
            if rest_response.status_code != 204:
                _logger.error(f"Failed to update Salesforce record: {rest_response.content}")

    @skip_if(lambda self: not self)
    def on_product_unlink(self,record_id):
        print("record_id")
        print(record_id)
        rest_request = self.env['salesforce.rest.config'].build_rest_request_delete(record_id,'product_template_delete')
        if rest_request:
            rest_response = self.env['salesforce.rest.config'].delete(rest_request['url'],rest_request['headers'])
            print("Response")
            print(rest_response)
            if rest_response.status_code != 204:
                _logger.error(f"Failed to update Salesforce record: {rest_response.content}")