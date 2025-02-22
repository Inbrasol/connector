import requests
import logging

_logger = logging.getLogger(__name__)

from odoo import models, api, fields
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if
from datetime import date, datetime
from ..backend.salesforce_rest_utils import SalesforceRestUtils

class ProductTemplate(models.Model):
    _inherit = 'product.template'

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
            if self._fields[field].type in ['one2many', 'many2many']:
                continue
            elif isinstance(self[field], models.BaseModel):
                if self[field].id != value:
                    changed_fields.append(field)
            elif self[field] != value:
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
        if record.sf_id in [False, None, '']:
            rest_request = SalesforceRestUtils.build_request(record, fields, 'create', 'product_template_create')
            if rest_request:
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                rest_response = SalesforceRestUtils.post(rest_request['url'], rest_request['headers'], rest_request['body'])
                if rest_response.status_code == 201:
                    sf_id = rest_response.json().get('id')
                    self._handle_pricebook_entry(record, sf_id, context_with_skip_sync)
                else:
                    self._handle_failed_integration(record, rest_response, context_with_skip_sync)

    def _handle_pricebook_entry(self, record, sf_id, context_with_skip_sync):
        query = f"SELECT+Id,Pricebook2Id,Product2Id,UnitPrice,IsActive+FROM+PriceBookEntry+WHERE+Product2Id='{sf_id}'"
        request_pricebook_entry = self.env['salesforce.rest.config'].build_rest_request_query(query, 'product_template_pricebook_entry_query')
        if request_pricebook_entry:
            rest_response_pricebook_entry = SalesforceRestUtils.get(request_pricebook_entry['url'], request_pricebook_entry['headers'])
            if rest_response_pricebook_entry.status_code == 200:
                self._update_pricebook_entry(record, rest_response_pricebook_entry.json(), sf_id, context_with_skip_sync)
            else:
                self._update_record_with_failure(record, sf_id, context_with_skip_sync)
        else:
            self._update_record_with_failure(record, sf_id, context_with_skip_sync)

    def _update_pricebook_entry(self, record, response_data, sf_id, context_with_skip_sync):
        for record_data in response_data.get('records', []):
            pricebook_entry_vals = {
                'sf_id': sf_id,
                'sf_pricebook_entry_id': record_data['Id'],
                'sf_pricebook_id': record_data['Pricebook2Id'],
                'sf_integration_status': 'success',
                'sf_integration_datetime': datetime.now()
            }
            record.with_context(context_with_skip_sync).write(pricebook_entry_vals)

    def _update_record_with_failure(self, record, sf_id, context_with_skip_sync):
        record.with_context(context_with_skip_sync).write({
            'sf_id': sf_id,
            'sf_integration_status': 'failed',
            'sf_integration_datetime': datetime.now()
        })

    def _handle_failed_integration(self, record, rest_response, context_with_skip_sync):
        _logger.error(f"Failed to update Salesforce record: {rest_response.content}")
        record.with_context(context_with_skip_sync).write({
            'sf_integration_status': 'failed',
            'sf_integration_datetime': datetime.now(),
            'sf_integration_error': rest_response.json()
        })
                    

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_product_template_update(self, record, fields):
        if record.sf_id not in [False, None, '']:
            rest_request = SalesforceRestUtils.build_request(record, fields, 'update', 'product_template_update')
            if rest_request:
                rest_response = None
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                match rest_request['method']:
                    case 'PATCH':
                        rest_response = SalesforceRestUtils.patch(rest_request['url'],rest_request['headers'],rest_request['body'])
                    case 'PUT':
                        rest_response = SalesforceRestUtils.put(rest_request['url'],rest_request['headers'],rest_request['body'])

                SalesforceRestUtils.update_sf_integration_status(record, rest_response.status_code, rest_response.json(), context_with_skip_sync)

    @skip_if(lambda self: not self)
    def on_product_template_delete(self,record,record_id):
        if record.sf_id not in [False, None, '']:
            rest_request = SalesforceRestUtils.build_request(record, None,'delete','product_template_delete')
            if rest_request:
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                rest_response = SalesforceRestUtils.delete(rest_request['url'],rest_request['headers'])
                SalesforceRestUtils.update_sf_integration_status(record, rest_response.status_code, rest_response.json(), context_with_skip_sync)