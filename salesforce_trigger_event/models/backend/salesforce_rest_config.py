import requests
import json
import logging
from datetime import date, timedelta
from odoo import models, fields, api
from .salesforce_rest_utils import SalesforceRestUtils

_logger = logging.getLogger(__name__)

class SalesforceRestConfig(models.Model):
    _name = 'salesforce.rest.config'
    _description = 'Salesforce REST Configuration'

    salesforce_backend_id = fields.Many2one('salesforce.backend', 'Salesforce Backend', required=True)
    name = fields.Char('Name', required=True)
    endpoint = fields.Char('Endpoint', related='salesforce_backend_id.url', readonly=True)
    sobject_api_name = fields.Char('SObject API Name', required=True)
    method = fields.Selection([
        ('GET', 'GET'),
        ('POST', 'POST'),
        ('PUT', 'PUT'),
        ('PATCH', 'PATCH'),
        ('DELETE', 'DELETE'),
    ], required=True, default='GET')
    version = fields.Char('Version', required=True)
    odoo_model_id = fields.Many2one('ir.model', 'Odoo Model', required=True, ondelete='cascade')
    rest_fields = fields.One2many('salesforce.rest.fields', 'salesforce_rest_config_id', 'Fields')
    record_types = fields.One2many('salesforce.record.type', 'salesforce_rest_config_id', 'Record Types')
    active = fields.Boolean('Active', default=True)
    type = fields.Selection([('single', 'Single'),('composite','Composite'),('composite_tree','Composite Tree'),
                            ('composite_collection','Composite Collection'),('composite_batch','Composite Batch'),
                            ('bulk','Bulk')], 'Type', required=True, default='single')
    line_rest_config_id = fields.Many2one('salesforce.rest.config', 'Line Setting')
    child_field_name = fields.Many2one('ir.model.fields', 'Odoo Line Field', ondelete='cascade' , domain="[('model_id', '=', odoo_model_id)]")
    child_rel_name = fields.Char('Relation Model')
    child_rel_filter = fields.Char('Relation Filter')

    def copy(self, default=None):
        self.ensure_one()
        default = dict(default or {})
        default.update({
            'name': f"{self.name} (copy)",
            'rest_fields': [],
            'record_types': [],
        })
        new_record = super(SalesforceRestConfig, self).copy(default)
        for child in self.rest_fields:
            child.copy({'salesforce_rest_config_id': new_record.id})
        for child in self.record_types:
            child.copy({'salesforce_rest_config_id': new_record.id})
        return new_record

    def authenticate(self):
        backend = self.env["salesforce.backend"].search([('id', '=', self.salesforce_backend_id.id)], limit=1)
        return backend.authenticate()

    def build_request(self, record, fields, operation, config_name):
        config = self.env['salesforce.rest.config'].search([('name', '=', config_name), ('active', '=', True)], limit=1)
        if not config:
            _logger.error(f"No active Salesforce REST configuration found with name: {config_name}")
            return None
        factory = RequestFactory()
        try:
            request_builder = factory.get_request_builder(config.type)
        except ValueError as e:
            _logger.error(f"Error getting request builder: {e}")
            return None
        
        return request_builder.build_request(config, record, fields, operation)


class RequestFactory:
    def get_request_builder(self, request_type):
        builders = {
            'single': RestRequestBuilder,
            'composite': CompositeRequestBuilder,
            'composite_tree': CompositeTreeRequestBuilder,
            'composite_collection': CompositesCollectionRequestBuilder,
            'composite_batch': CompositeBatchRequestBuilder,
            'bulk': BulkRequestBuilder
        }
        builder_class = builders.get(request_type)
        if not builder_class:
            raise ValueError(f"Unknown request type: {request_type}")
        return builder_class()

class RequestBuilder:

    def build_request(self, config, record, fields, operation):
        raise NotImplementedError("Subclasses must implement this method")
    
    def get_headers(self, config):
        authenticate = config.authenticate()
        if not authenticate.get('access_token'):
            _logger.error("Authentication failed.")
            return None
        return {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {authenticate['access_token']}"
        }

class RestRequestBuilder(RequestBuilder):

    def build_query_request(self, config, query):
        url = f"{config.endpoint}/services/data/v{config.version}/query?q={query}"
        headers = self.get_headers(config)
        return {
            "url": url,
            "headers": headers,
            'method': config.method,
            'type': 'rest'
        }
    
    def build_create_request(self, config, record, fields):
        url = f"{config.endpoint}/services/data/v{config.version}/sobjects/{config.sobject_api_name}"
        headers = self.get_headers(config)
        body_request = SalesforceRestUtils.build_rest_fields(config, record, fields)
        return {
            "url": url,
            "headers": headers,
            'body': json.dumps(body_request, default=SalesforceRestUtils.json_serial),
            'method': config.method,
            'type': 'rest'
        }
    
    def build_update_request(self, config, record, fields):
        url = f"{config.endpoint}/services/data/v{config.version}/sobjects/{config.sobject_api_name}/{record.sf_id}"
        headers = self.get_headers(config)
        body_request = SalesforceRestUtils.build_rest_fields(config, record, fields)
        return {
            "url": url,
            "headers": headers,
            'body': json.dumps(body_request, default=SalesforceRestUtils.json_serial),
            'method': config.method,
            'type': 'rest'
        }
    
    def build_delete_request(self, config, record):
        url = f"{config.endpoint}/services/data/v{config.version}/sobjects/{config.sobject_api_name}/{record.sf_id}"
        headers = self.get_headers(config)
        return {
            "url": url,
            "headers": headers,
            'method': config.method,
            'type': 'rest'
        }
    
    def build_request(self, config, record, fields, operation):
        match operation:
            case 'query':
                return self.build_query_request(config, record)
            case 'create':
                return self.build_create_request(config, record, fields)
            case 'update':
                return self.build_update_request(config, record, fields)
            case 'delete':
                return self.build_delete_request(config, record)
            case _:
                _logger.error(f"Unsupported operation: {operation}")
                return None
            
class CompositeRequestBuilder(RequestBuilder):
    def build_create_request(self, config, record, fields):
        url = f"{config.endpoint}/services/data/v{config.version}/composite"
        headers = self.get_headers(config)
        body_request = None

        if not config.line_rest_config_id and isinstance(record, list):
            body_request = SalesforceRestUtils.build_rest_composite_fields(config, record, fields)
        elif config.line_rest_config_id and not isinstance(record, list):
            body_request = SalesforceRestUtils.build_rest_composite_nested_fields(config, record, fields)
        
        return {
            "url": url,
            "headers": headers,
            'body': json.dumps(body_request['body'], default=SalesforceRestUtils.json_serial),
            'map_ref_fields': body_request['map_ref_fields'],
            'method': config.method,
            'type': 'composite'
        }
    
    def build_update_request(self, config, record, fields):
        url = f"{config.endpoint}/services/data/v{config.version}/composite"
        headers = self.get_headers(config)
        body_request = None

        if not config.line_rest_config_id and isinstance(record, list):
            body_request = SalesforceRestUtils.build_rest_composite_fields(config, record, fields)
        elif config.line_rest_config_id and not isinstance(record, list):
            body_request = SalesforceRestUtils.build_rest_composite_nested_fields(config, record, fields)
        
        return {
            "url": url,
            "headers": headers,
            'body': json.dumps(body_request['body'], default=SalesforceRestUtils.json_serial),
            'map_ref_fields': body_request['map_ref_fields'],
            'method': config.method,
            'type': 'composite'
        }
    
    #Metodo por mejorar o retirar
    def build_delete_request(self, config, record):
        url = f"{config.endpoint}/services/data/v{config.version}/composite"
        headers = self.get_headers(config)
        body_request = None

        if not config.line_rest_config_id and isinstance(record, list):
            body_request = SalesforceRestUtils.build_rest_composite_fields(config, record, fields)
        elif config.line_rest_config_id and not isinstance(record, list):
            body_request = SalesforceRestUtils.build_rest_composite_nested_fields(config, record, fields)
        
        return {
            "url": url,
            "headers": headers,
            'body': json.dumps(body_request['body'], default=SalesforceRestUtils.json_serial),
            'map_ref_fields': body_request['map_ref_fields'],
            'method': config.method,
            'type': 'composite'
        }
    
    def build_request(self, config, record, fields, operation):
        match operation:
            case 'create':
                return self.build_create_request(config, record, fields)
            case 'update':
                return self.build_update_request(config, record, fields)
            case 'delete':
                return self.build_delete_request(config, record)
            case _:
                _logger.error(f"Unsupported operation: {operation}")
                return None

class CompositeTreeRequestBuilder(RequestBuilder):
    def build_request(self, config, record, fields, operation):
        url = f"{config.endpoint}/services/data/v{config.version}/composite/tree/{config.sobject_api_name}"
        headers = self.get_headers(config)
        body_request = None

        if not config.line_rest_config_id:
            body_request = SalesforceRestUtils.build_rest_composite_tree_fields(config, record, fields)
        elif config.line_rest_config_id:
            body_request = SalesforceRestUtils.build_rest_composite_tree_nested_fields(config, record, fields)
        
        return {
            "url": url,
            "headers": headers,
            'body': json.dumps(body_request['body'], default=SalesforceRestUtils.json_serial),
            'map_ref_fields': body_request['map_ref_fields'],
            'method': config.method,
            'type': 'composite_tree'
        }

class CompositesCollectionRequestBuilder(RequestBuilder):
    def create_built_request(self, config, records, fields, operation):
        url = f"{config.endpoint}/services/data/v{config.version}/composite/sobjects"
        headers = self.get_headers(config)
        body_request = SalesforceRestUtils.build_rest_composite_collection_fields(config, records, fields, operation)

        return {
            "url": url,
            "headers": headers,
            'body': json.dumps(body_request['body'], default=SalesforceRestUtils.json_serial),
            "map_ref_fields": None,
            "method": config.method,
            "type": "composite_collection"
        }
    
    def update_built_request(self, config, records, fields, operation):
        url = f"{config.endpoint}/services/data/v{config.version}/composite/sobjects"
        headers = self.get_headers(config)
        body_request = SalesforceRestUtils.build_rest_composite_collection_fields(config, records, fields, operation)

        return {
            "url": url,
            "headers": headers,
            "body": json.dumps(body_request['body'], default=SalesforceRestUtils.json_serial),
            "map_ref_fields": None,
            "method": config.method,
            "type": "composite_collection"
        }
    
    def delete_built_request(self, config, records, fields, operation):
        record_ids = ','.join(records)
        url = f"{config.endpoint}/services/data/v{config.version}/composite/sobjects?ids={record_ids}"
        
        headers = self.get_headers(config)
        return {
            "url": url,
            "headers": headers,
            "map_ref_fields": None,
            "method": config.method,
            "type": 'composite_collection'
        }
    
    def build_request(self, config, records, fields, operation):
        match operation:
            case 'create':
                return self.create_built_request(config, records, fields, operation)
            case 'update':
                return self.update_built_request(config, records, fields, operation)
            case 'delete':
                return self.delete_built_request(config, records, fields, operation)
            case _:
                _logger.error(f"Unsupported operation: {operation}")
                return None

class CompositeBatchRequestBuilder(RequestBuilder):
    def create_built_request(self, config, records, fields, operation):        
        url = f"{config.endpoint}/services/data/v{config.version}/composite/batch"
        headers = self.get_headers(config)
        body_request = SalesforceRestUtils.build_composite_batch_fields(config, records, fields)

        return {
            "url": url,
            "headers": headers,
            'body': json.dumps(body_request['batchRequest'], default=SalesforceRestUtils.json_serial),
            'map_ref_fields': body_request['map_ref_fields'],
            'method': config.method,
            'type': 'composite_batch'
        }
    
    def update_built_request(self, config, records, fields, operation):
        url = f"{config.endpoint}/services/data/v{config.version}/composite/batch"
        headers = self.get_headers(config)
        body_request = SalesforceRestUtils.build_composite_batch_fields(config, records, fields)

        return {
            "url": url,
            "headers": headers,
            'body': json.dumps(body_request['batchRequest'], default=SalesforceRestUtils.json_serial),
            'map_ref_fields': body_request['map_ref_fields'],
            'method': config.method,
            'type': 'composite_batch'
        }
    
    def delete_built_request(self, config, records, fields, operation):        
        url = f"{config.endpoint}/services/data/v{config.version}/composite/batch"
        headers = self.get_headers(config)
        body_request = SalesforceRestUtils.build_composite_batch_fields(config, records, fields)

        return {
            "url": url,
            "headers": headers,
            'map_ref_fields': body_request['map_ref_fields'],
            'method': config.method,
            'type': 'composite_batch'
        }
    
    def build_request(self, config, records, fields, operation):
        match operation:
            case 'create':
                return self.create_built_request(config, records, fields, operation)
            case 'update':
                return self.update_built_request(config, records, fields, operation)
            case 'delete':
                return self.delete_built_request(config, records, fields, operation)
            case _:
                _logger.error(f"Unsupported operation: {operation}")
                return None
            
class BulkRequestBuilder(RequestBuilder):
    def build_request(self, config, records, operation):
        authenticate = self.authenticate(config)
        if authenticate['access_token']:
            url = f"{config.endpoint}/services/data/v{config.version}/jobs/ingest"
            headers = self.get_headers(config)
            job_data = {
                "object": config.sobject_api_name,
                "contentType": "CSV",
                "operation": operation,
                "lineEnding": "LF"
            }
            job_response = requests.post(url, headers=headers, data=json.dumps(job_data))
            job_info = job_response.json()
            job_id = job_info.get('id')
            if job_id:
                upload_url = f"{config.endpoint}/services/data/v{config.version}/jobs/ingest/{job_id}/batches"
                upload_headers = headers.copy()
                upload_headers['Content-Type'] = 'text/csv'
                json_data = SalesforceRestUtils.build_bulk_request_fields(records)
                upload_response = requests.put(upload_url, headers=upload_headers, data=json_data)
                if upload_response.status_code == 201:
                    close_url = f"{config.endpoint}/services/data/v{config.version}/jobs/ingest/{job_id}"
                    close_data = {"state": "UploadComplete"}
                    close_response = requests.patch(close_url, headers=headers, data=json.dumps(close_data))
                    return close_response.json()
        return None