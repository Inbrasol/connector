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
    type = fields.Selection([('single', 'Single'),('composite','Composite'),('bulk','Bulk')], 'Type', required=True, default='single')
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
        
        request_type = SalesforceRestUtils.get_operation_type_by_size(config, record)
        factory = RequestFactory()
        
        try:
            request_builder = factory.get_request_builder(request_type)
        except ValueError as e:
            _logger.error(f"Error getting request builder: {e}")
            return None
        
        return request_builder.build_request(config, record, fields, operation)
    
    def build_rest_request_query(self, query, name):
        salesforce_config = self.env['salesforce.rest.config'].search([('name', '=', name), ('active', '=', True)], limit=1)
        if not salesforce_config:
            return
        backend = self.env["salesforce.backend"].search([('id', '=', salesforce_config.salesforce_backend_id.id)], limit=1)
        authenticate = backend.authenticate()
        if authenticate['access_token']:
            endpoint = salesforce_config.endpoint
            version = salesforce_config.version
            url = f"{endpoint}/services/data/v{version}/query?q=" + query
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {authenticate['access_token']}"
            }
            return {
                "url": url,
                "headers": headers,
                'method': salesforce_config.method,
                'type': salesforce_config.type
            }


class RequestFactory:
    def get_request_builder(self, request_type):
        if request_type == 'single':
            return SingleRequestBuilder()
        elif request_type == 'composite_single':
            return CompositeSingleRequestBuilder()
        elif request_type == 'composite_tree':
            return CompositeTreeRequestBuilder()
        elif request_type == 'composite_batch':
            return CompositeBatchRequestBuilder()
        elif request_type == 'bulk':
            return BulkRequestBuilder()
        else:
            raise ValueError(f"Unknown request type: {request_type}")

class RequestBuilder:
    def build_request(self, config, record, fields, operation):
        raise NotImplementedError("Subclasses must implement this method")

class SingleRequestBuilder(RequestBuilder):
    def build_request(self, config, record, fields, operation):
        authenticate = config.authenticate()
        if authenticate['access_token']:
            url = f"{config.endpoint}/services/data/v{config.version}/sobjects/{config.sobject_api_name}"
            if operation in ['update', 'delete']:
                url += f"/{record.sf_id}"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {authenticate['access_token']}"
            }
            body_request = SalesforceRestUtils.build_rest_fields(config, record, fields)
            return {
                "url": url,
                "headers": headers,
                'body': json.dumps(body_request, default=SalesforceRestUtils.json_serial),
                'method': config.method,
                'type': 'single'
            }

class CompositeSingleRequestBuilder(RequestBuilder):
    def build_request(self, config, record, fields, operation):
        authenticate = config.authenticate()
        if authenticate['access_token']:
            url = f"{config.endpoint}/services/data/v{config.version}/composite/sobjects/{config.sobject_api_name}"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {authenticate['access_token']}"
            }
            body_request = SalesforceRestUtils.build_rest_composite_fields(config,record, fields)
            return {
                "url": url,
                "headers": headers,
                'body': json.dumps(body_request['body'], default=SalesforceRestUtils.json_serial),
                'map_ref_fields': fields['map_ref_fields'],
                'method': config.method,
                'type': 'composite_single'
            }

class CompositeTreeRequestBuilder(RequestBuilder):
    def build_request(self, config, record, fields, operation):
        authenticate = config.authenticate()
        if authenticate['access_token']:
            url = f"{config.endpoint}/services/data/v{config.version}/composite/tree/{config.sobject_api_name}"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {authenticate['access_token']}"
            }
            body_request = SalesforceRestUtils.build_rest_composite_tree_fields(config,record, fields)
            return {
                "url": url,
                "headers": headers,
                'body': json.dumps(body_request['body'], default=SalesforceRestUtils.json_serial),
                'map_ref_fields': fields['map_ref_fields'],
                'method': config.method,
                'type': 'composite_tree'
            }

class CompositeBatchRequestBuilder(RequestBuilder):
    def build_request(self, config, record, fields, operation):
        authenticate = config.authenticate()
        if authenticate['access_token']:
            url = f"{config.endpoint}/services/data/v{config.version}/composite/batch"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {authenticate['access_token']}"
            }
            body_request = SalesforceRestUtils.build_rest_composite_batch_fields(config, record, fields)
            return {
                "url": url,
                "headers": headers,
                'body': json.dumps(body_request['batchRequest'], default=SalesforceRestUtils.json_serial),
                'map_ref_fields': fields['map_ref_fields'],
                'method': config.method,
                'type': 'composite_batch'
            }

class BulkRequestBuilder(RequestBuilder):
    def build_request(self, config, records, operation):
        authenticate = config.authenticate()
        if authenticate['access_token']:
            url = f"{config.endpoint}/services/data/v{config.version}/jobs/ingest"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {authenticate['access_token']}"
            }
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
