import requests
import logging

_logger = logging.getLogger(__name__)

from odoo import models, api, fields
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    #skip_sync = fields.Boolean(string='Skip Sync', default=False, copy=False)

    @api.model
    def create(self, vals):
        product = super(ProductTemplate, self).create(vals)
        self._event('on_product_template_create').notify(product,fields=vals.keys())
        return product
    
    @api.model
    def write(self, vals):
        if self.env.context.get('skip_sync'):
            super(ProductTemplate, self).write(vals)
            return self
        
        # Set skip_sync in context to avoid recursion
        context_with_skip_sync = dict(self.env.context, skip_sync=True)
        changed_fields = []
        for field, value in vals.items():
            if self[field] != value:
                changed_fields.append(field)
        super(ProductTemplate, self.with_context(context_with_skip_sync)).write(vals)
        if len(changed_fields) > 0:
            self._event('on_product_template_update').notify(self, changed_fields)

        print("Product Template Update")
        print(self)
        return self

    @api.model
    def unlink(self):
        product = super(ProductTemplate, self).unlink()
        self._event('on_product_template_delete').notify(product,product.id)
        return product

class ProductProductListener(Component):
    _name = 'product.product.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['product.template']

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_product_template_create(self, record, fields):
        print("Fields")
        print(fields)
        #CALL API PRODUCT
        if record.sf_id in [False, None, '']:
            rest_request = self.env['salesforce.rest.config'].build_rest_request_create(record, fields, 'product_template_create')
            if rest_request:
                rest_response = self.env['salesforce.rest.config'].post(rest_request['url'],rest_request['headers'],rest_request['fields'])
                print("Response")
                print(rest_response)
                if rest_response.status_code == 201:
                    sf_id = rest_response.json()['id']
                    query = f"SELECT+Id,Pricebook2Id,Product2Id,UnitPrice,IsActive+FROM+PriceBookEntry+WHERE+Product2Id='{sf_id}'"
                    request_pricebook_entry = self.env['salesforce.rest.config'].build_rest_request_query(query, 'product_template_pricebook_entry_query')
                    if request_pricebook_entry:
                        rest_response_pricebook_entry = self.env['salesforce.rest.config'].get(request_pricebook_entry['url'],request_pricebook_entry['headers'])
                        print("Response Price Book")
                        print(rest_response_pricebook_entry)
                        if rest_response_pricebook_entry.status_code == 200:
                            response_data = rest_response_pricebook_entry.json()
                            for record_data in response_data['records']:
                                pricebook_entry_vals = {
                                    'sf_id': sf_id,
                                    'sf_pricebook_entry_id': record_data['Id'],
                                    'sf_pricebook_id': record_data['Pricebook2Id']
                                }
                                record.write(pricebook_entry_vals)
                        else:
                            record.write({'sf_id':sf_id})
                    else:
                        record.write({'sf_id':sf_id})
                else:
                    _logger.error(f"Failed to update Salesforce record: {rest_response.content}")

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_product_template_update(self, record, fields):
        print("Fields")
        print(fields)
        if record.sf_id not in [False, None, '']:
            rest_request = self.env['salesforce.rest.config'].build_rest_request_update(record, fields, 'product_template_update')
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
    def on_product_template_delete(self,record,record_id):
        print("record_id")
        print(record_id)
        if record.sf_id not in [False, None, '']:
            rest_request = self.env['salesforce.rest.config'].build_rest_request_delete(record_id,'product_template_delete')
            if rest_request:
                rest_response = self.env['salesforce.rest.config'].delete(rest_request['url'],rest_request['headers'])
                print("Response")
                print(rest_response)
                if rest_response.status_code != 204:
                    _logger.error(f"Failed to update Salesforce record: {rest_response.content}")