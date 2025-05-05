import requests
import logging

_logger = logging.getLogger(__name__)

from odoo import models, api, fields
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if
from datetime import date, datetime, timedelta
from ..backend.salesforce_rest_utils import SalesforceRestUtils

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def create_lines_to_sf_by_cron(self):
        _logger.error("cron: %s", self)
        related_model = self.env['product.template']
        fields = related_model._fields.keys()
        lines_create = related_model.search([
            ('sf_id', '=', False),
            ('sale_ok', '=', True),
            ('type', 'in', ('consu', 'product')),
            ('active', '=', True),
        ], limit=201)
        
        _logger.error("product_lines_create: %s", lines_create)
        
        if not lines_create:
            return self

        # Limit the number of product lines to process to a maximum of 200
        lines = lines_create[:200]
        lines_to_process = []
        # Ensure the product name does not exceed 255 characters
        for line in lines:
            line_data = line
            if len(line.name) > 255:
                line_data['name'] = line.name[:255]
            lines_to_process.append(line_data)

        self._event('on_product_template_create_bulk').notify(lines_to_process, fields)

        # If there are more than 200 product lines, schedule the next batch
        if len(lines_create) > 200:
            cron_job = self.env.ref('salesforce_trigger_event.ir_cron_create_product_template_to_sf')
            next_call_time = (datetime.now() + timedelta(minutes=2)).strftime('%Y-%m-%d %H:%M:%S')
            cron_job.write({'nextcall': next_call_time})

        return self
    
    @api.model
    def update_lines_to_sf_by_cron(self):
        context_with_skip_sync = dict(self.env.context, skip_sync=True)
        related_model = self.env['product.template']
        lines_update = related_model.search([
            ('sf_id', '!=', False),
            ('sf_pricebook_id', '=', False),
            ('sale_ok', '=', True),
            ('type', 'in', ('consu', 'product')),
            ('active', '=', True),
        ], limit=201)

        _logger.error("product_lines_update: %s", lines_update)
        
        if not lines_update:
            return self

        # Limit the number of product lines to process to a maximum of 200
        lines_to_process = lines_update[:min(len(lines_update), 200)]

        query = "SELECT+Id,Pricebook2Id,Product2Id,UnitPrice,IsActive+FROM+PriceBookEntry+WHERE+Product2Id+IN+('{}')".format("'+','".join(lines_to_process.mapped('sf_id')))
        
        request_pricebook_entry = self.env['salesforce.rest.config'].build_request(query, None, 'query', 'product_template_pricebook_entry_query')
        
        _logger.error(f"GET request url: {request_pricebook_entry}")
        response = requests.get(request_pricebook_entry['url'], headers=request_pricebook_entry['headers'])
        _logger.error(f"GET response: {response}")
        _logger.error(f"GET response: {response.text}")
        
        order_documents_to_update = []

        if response.status_code == 200:
            records = response.json().get('records', [])
            for record in records:
                order_documents_to_update.append({
                    'id': lines_to_process.filtered(lambda x: x.sf_id == record['Product2Id']).id,
                    'sf_pricebook_entry_id': record['Id'],
                    'sf_pricebook_id': record['Pricebook2Id'],
                    'sf_integration_status': 'success',
                    'sf_integration_datetime': datetime.now()
                })
            
        if order_documents_to_update:
            related_model.with_context(context_with_skip_sync).write(order_documents_to_update)
        
        # If there are more than 200 product lines, schedule the next batch
        if len(order_documents_to_update) > 200:
            cron_job = self.env.ref('salesforce_trigger_event.ir_cron_update_product_template_to_sf')
            next_call_time = (datetime.now() + timedelta(minutes=2)).strftime('%Y-%m-%d %H:%M:%S')
            cron_job.write({'nextcall': next_call_time})

        return self
    
    """
    def create(self, vals):
        if self.env.context.get('skip_sync'):
            return super(ProductTemplate, self).create(vals)
        
        if self.sf_id not in [False, None, '']:
            return super(ProductTemplate, self).create(vals)
        
        product = super(ProductTemplate, self).create(vals)
        fields = self._fields.keys()
        self._event('on_product_template_create').notify(product,fields=fields)
        return product
    """
    
    def write(self, vals):
        if len(self) > 1:
            return super(ProductTemplate, self).write(vals)
        
        if self.env.context.get('skip_sync'):
            return super(ProductTemplate, self).write(vals)
        
        if self.sf_id not in [False, None, '']:
            return super(ProductTemplate, self).write(vals)
        
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
    
    def unlink(self):
        _logger.error("→ Intentando eliminar product.template con contexto skip_sync: %s", self.env.context.get('skip_sync'))
        # Buscar los sf_ids de los productos que se quieren eliminar
        product_templates = self.env['product.template'].browse(self.ids)
        sf_ids = [sf_id for sf_id in product_templates.mapped('sf_id') if sf_id]  # Solo valores no vacíos

        _logger.error("→ sf_ids encontrados: %s", sf_ids)
        if len(sf_ids) == 0:
            _logger.error("→ No se encontraron sf_ids, se eliminará normalmente.")
            return super(ProductTemplate, self).unlink()
        else:
            _logger.error("→ Se encontraron sf_ids, notificando evento antes de eliminar.")
            self._event('on_product_template_delete').notify(sf_ids)
            return super(ProductTemplate, self).unlink()


class ProductProductListener(Component):
    _name = 'product.product.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['product.template']

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_product_template_create(self, record, fields):
        if record.sf_id in [False, None, '']:
            rest_request =  self.env['salesforce.rest.config'].build_request(record, fields, 'create', 'product_template_create')
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
        request_pricebook_entry = self.env['salesforce.rest.config'].build_request(query, None, 'query', 'product_template_pricebook_entry_query')
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
    def on_product_template_create_bulk(self, record, fields):
        #Call Sync Product Template to Salesforce
        rest_request = self.env['salesforce.rest.config'].build_request(record, fields, 'create', 'product_template_create_bulk')
        if rest_request:
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            rest_response = SalesforceRestUtils.post(rest_request['url'], rest_request['headers'], rest_request['body'])
            if rest_response and rest_response.status_code in [200, 201]:
                sf_tmpl_ids = []
                # Process the response
                response_data = rest_response.json()
                for record_response in response_data['results']:
                    if record_response['referenceId'] in rest_request['map_ref_fields']:
                        map_field = rest_request['map_ref_fields'][record_response['referenceId']]
                        record_to_update = self.env[map_field['model']].browse(map_field['id'])
                        record_to_update.with_context(context_with_skip_sync).write({
                            'sf_id': record_response.get('id'),
                            'sf_integration_status': 'success',
                            'sf_integration_datetime': datetime.now()
                        })
                        sf_tmpl_ids.append(record_response.get('id'))

                # Ensure sf_tmpl_ids are properly formatted for the query
                sf_tmpl_ids_str = "','".join(sf_tmpl_ids)
                query = f"SELECT+Id,Pricebook2Id,Product2Id,Product2.Odoo_Id__c,UnitPrice,IsActive+FROM+PriceBookEntry+WHERE+Product2Id+IN+('{sf_tmpl_ids_str}')"
                request_pricebook_entry = self.env['salesforce.rest.config'].build_request(query, None, 'query', 'product_template_pricebook_entry_query')
                _logger.error("request_pricebook_entry:  %s", request_pricebook_entry)
                if request_pricebook_entry:
                    rest_response_pricebook_entry = SalesforceRestUtils.get(request_pricebook_entry['url'], request_pricebook_entry['headers'])
                    if rest_response_pricebook_entry and rest_response_pricebook_entry.status_code == 200:
                        rest_response_pricebook_entry_data = rest_response_pricebook_entry.json()
                        _logger.error("rest_response_pricebook_entry_data:  %s", rest_response_pricebook_entry_data)
                        for record_data in rest_response_pricebook_entry_data['records']:
                            pricebook_entry_vals = {
                                'sf_id': record_data['Product2Id'],
                                'sf_pricebook_entry_id': record_data['Id'],
                                'sf_pricebook_id': record_data['Pricebook2Id'],
                                'sf_integration_status': 'success',
                                'sf_integration_datetime': datetime.now()
                            }
                            record_id = int(record_data['Product2']['Odoo_Id__c'])
                            record_to_update = self.env['product.template'].browse(record_id)
                            record_to_update.with_context(context_with_skip_sync).write(pricebook_entry_vals)
                            
                        
    @skip_if(lambda self, record, fields: not record or not fields)
    def on_product_template_update(self, record, fields):
        if record.sf_id not in [False, None, '']:
            rest_request = self.env['salesforce.rest.config'].build_request(record, fields, 'update', 'product_template_update')
            if rest_request:
                rest_response = None
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                match rest_request['method']:
                    case 'PATCH':
                        rest_response = SalesforceRestUtils.patch(rest_request['url'],rest_request['headers'],rest_request['body'])
                    case 'PUT':
                        rest_response = SalesforceRestUtils.put(rest_request['url'],rest_request['headers'],rest_request['body'])

                SalesforceRestUtils._update_sf_integration_status(record, rest_response.status_code, rest_response.json(), context_with_skip_sync)

    @skip_if(lambda self, records: not records)
    def on_product_template_delete(self, records):
        rest_request = self.env['salesforce.rest.config'].build_request(records, None, 'delete', 'product_template_delete')
        if rest_request:
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            rest_response = SalesforceRestUtils.delete(rest_request['url'], rest_request['headers'])
            SalesforceRestUtils._handle_successful_response(self, rest_request, rest_response, context_with_skip_sync)