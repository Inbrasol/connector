import requests
import json
from datetime import date, timedelta
from odoo import models, fields, api

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

    
    #ORM Methods

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
    
    ##Utils Methods###
    def get(self, url, headers):
        response = requests.get(url, headers= headers)
        return response

    def post(self, url, headers, data):
        response = requests.post(url, headers=headers, data=data)
        return response

    def put(self, url, headers, data):
        response = requests.put(url, headers = headers, data=data)
        return response
    
    def patch(self, url, headers, data):
        response = requests.patch(url, headers = headers, data=data)
        return response

    def delete(self, url, headers):
        response = requests.delete(url, headers = headers)
        return response

    def json_serial(self,obj):
        #JSON serializer for objects not serializable by default json code
        if isinstance(obj, date):
            return obj.strftime('%Y-%m-%d')
        raise TypeError(f"Type {type(obj)} not serializable")

    def build_rest_fields(self, sf_config, record, fields):
        fields_to_rest = {}
        for field in sf_config.rest_fields.filtered(lambda f: f.active):
            if field.default_value not in [None, '', False]:
                match field.type:
                    case 'string' | 'integer' | 'float' | 'boolean' | 'related':
                        fields_to_rest.update({field.salesforce_field: field.default_value})
                    case 'date':
                        match field.default_value:
                            case 'YESTERDAY':
                                fields_to_rest.update({field.salesforce_field: date.today() - timedelta(days=1)})
                            case 'TODAY':
                                fields_to_rest.update({field.salesforce_field: date.today()})
                            case 'TOMORROW':
                                fields_to_rest.update({field.salesforce_field: date.today() + timedelta(days=1)})
                            case 'LAST_WEEK':
                                fields_to_rest.update({field.salesforce_field: date.today() - timedelta(days=date.today().weekday() + 7)})
                            case 'THIS_WEEK':
                                fields_to_rest.update({field.salesforce_field: date.today() - timedelta(days=date.today().weekday())})
                            case 'NEXT_WEEK':
                                fields_to_rest.update({field.salesforce_field: date.today() + timedelta(days=6 - date.today().weekday() + 7)})
                            case 'LAST_MONTH':
                                fields_to_rest.update({field.salesforce_field: date.today().replace(day=1) - timedelta(days=1)})
                            case 'THIS_MONTH':
                                fields_to_rest.update({field.salesforce_field: date.today().replace(day=1)})
                            case 'NEXT_MONTH':
                                fields_to_rest.update({field.salesforce_field: date.today().replace(day=28) + timedelta(days=4)})
                            case 'LAST_90_DAYS':
                                fields_to_rest.update({field.salesforce_field: date.today() - timedelta(days=90)})
                            case 'NEXT_90_DAYS':
                                fields_to_rest.update({field.salesforce_field: date.today() + timedelta(days=90)})
                            case 'LAST_N_DAYS:n':
                                fields_to_rest.update({field.salesforce_field: date.today() - timedelta(days=int(field.default_value.split(':')[1]))})
                            case 'NEXT_N_DAYS:n':
                                fields_to_rest.update({field.salesforce_field: date.today() + timedelta(days=int(field.default_value.split(':')[1]))})
                            case _:
                                fields_to_rest.update({field.salesforce_field: date.today()})
                    case 'datetime':
                        match field.default_value:
                            case 'YESTERDAY':
                                fields_to_rest.update({field.salesforce_field: date.now() - timedelta(days=1)})
                            case 'TODAY':
                                fields_to_rest.update({field.salesforce_field: date.now()})
                            case 'TOMORROW':
                                fields_to_rest.update({field.salesforce_field: date.now() + timedelta(days=1)})
                            case 'LAST_WEEK':
                                fields_to_rest.update({field.salesforce_field: date.now() - timedelta(days=date.now().weekday() + 7)})
                            case 'THIS_WEEK':
                                fields_to_rest.update({field.salesforce_field: date.now() - timedelta(days=date.now().weekday())})
                            case 'NEXT_WEEK':
                                fields_to_rest.update({field.salesforce_field: date.now() + timedelta(days=6 - date.now().weekday() + 7)})
                            case 'LAST_MONTH':
                                fields_to_rest.update({field.salesforce_field: date.now().replace(day=1) - timedelta(days=1)})
                            case 'THIS_MONTH':
                                fields_to_rest.update({field.salesforce_field: date.now().replace(day=1)})
                            case 'NEXT_MONTH':
                                fields_to_rest.update({field.salesforce_field: date.now().replace(day=28) + timedelta(days=4)})
                            case 'LAST_90_DAYS':
                                fields_to_rest.update({field.salesforce_field: date.now() - timedelta(days=90)})
                            case 'NEXT_90_DAYS':
                                fields_to_rest.update({field.salesforce_field: date.now() + timedelta(days=90)})
                            case 'LAST_N_DAYS:n':
                                fields_to_rest.update({field.salesforce_field: date.now() - timedelta(days=int(field.default_value.split(':')[1]))})
                            case 'NEXT_N_DAYS:n':
                                fields_to_rest.update({field.salesforce_field: date.now() + timedelta(days=int(field.default_value.split(':')[1]))})
                            case _:
                                fields_to_rest.update({field.salesforce_field: date.now()})
                
            elif field.odoo_field_id.name in fields:
                value = getattr(record, field.odoo_field_id.name)[field.odoo_related_field_id.name] if field.type == 'related' else getattr(record, field.odoo_field_id.name)
                if value not in [None, '', False] :
                    match field.type:
                        case 'string' | 'integer' | 'float' | 'boolean':
                            fields_to_rest.update({field.salesforce_field : value})
                        case 'date' | 'datetime':
                            fields_to_rest.update({field.salesforce_field: getattr(record,field.odoo_field_id.name)})
                        case 'related':
                            fields_to_rest.update({field.salesforce_field: getattr(record,field.odoo_field_id.name)[field.odoo_related_field_id.name]})
                        case _:
                            fields_to_rest.update({field.salesforce_field: getattr(record,field.odoo_field_id.name)})
                            
            elif field.type == 'related' and getattr(record, field.odoo_field_id.name) not in [None, '', False]:
                fields_to_rest.update({field.salesforce_field: getattr(record, field.odoo_field_id.name)[field.odoo_related_field_id.name]})


        for record_type in sf_config.record_types.filtered(lambda r: r.active):
            match record_type.type:
                case 'string':
                    if getattr(record, record_type.odoo_field_id.name) == record_type.odoo_field_value:
                        fields_to_rest.update({'RecordTypeId': record_type.record_type_id})
                case 'related':
                    if (getattr(record, record_type.odoo_field_id.name) not in [None, '', False]) and (getattr(record, record_type.odoo_field_id.name)[record_type.odoo_related_field_id.name] == record_type.odoo_field_value):
                        fields_to_rest.update({'RecordTypeId': record_type.record_type_id})

        print("Fields to Rest")
        print(fields_to_rest)
        return fields_to_rest

    #   REST RECORD
    def build_rest_single_request_create(self, salesforce_config, record, fields):
        backend = self.env["salesforce.backend"].search([('id', '=', salesforce_config.salesforce_backend_id.id)], limit=1)
        authenticate = backend.authenticate()
        print("Authenticate")
        print(authenticate)
        if authenticate['access_token'] is not None:
            # Your custom logic for update event
            endpoint = salesforce_config.endpoint
            version = salesforce_config.version
            sobject_api_name = salesforce_config.sobject_api_name  # Assuming the SObject API name is Opportunity
            url = f"{endpoint}/services/data/v{version}/sobjects/{sobject_api_name}"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {authenticate['access_token']}"
            }

            fields = self.build_rest_fields(salesforce_config,record,fields)
            print("Fields")
            print(fields)
            print("headers")
            print(headers)

            return {
                "url": url,
                "headers": headers,
                'fields': json.dumps(fields, default=self.json_serial),
                'method': salesforce_config.method,
                'type': salesforce_config.type
            }
        
    def build_rest_single_request_update(self, salesforce_config, record, fields):
        backend = self.env["salesforce.backend"].search([('id', '=', salesforce_config.salesforce_backend_id.id)], limit=1)
        authenticate = backend.authenticate()
        print("Authenticate")
        print(authenticate)
        if authenticate['access_token'] is not None:
            # Your custom logic for update event
            endpoint = salesforce_config.endpoint
            version = salesforce_config.version
            sobject_api_name = salesforce_config.sobject_api_name  # Assuming the SObject API name is Opportunity
            url = f"{endpoint}/services/data/v{version}/sobjects/{sobject_api_name}/{record.sf_id}"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {authenticate['access_token']}"
            }
            
            fields = self.build_rest_fields(salesforce_config,record, fields)
            print("Fields")
            print(fields)
            print("headers")
            print(headers)

            return {
                "url": url,
                "headers": headers,
                'fields': json.dumps(fields, default=self.json_serial),
                'method': salesforce_config.method,
                'type': salesforce_config.type
            }
        
    def build_rest_single_request_delete(self, salesforce_config, record_id):
        backend = self.env["salesforce.backend"].search([('id', '=', salesforce_config.salesforce_backend_id.id)], limit=1)
        authenticate = backend.authenticate()
        print("Authenticate")
        print(authenticate)
        if authenticate['access_token'] is not None:
            # Your custom logic for update event
            endpoint = salesforce_config.endpoint
            version = salesforce_config.version
            sobject_api_name = salesforce_config.sobject_api_name  # Assuming the SObject API name is Opportunity
            url = f"{endpoint}/services/data/v{version}/sobjects/{sobject_api_name}/{record_id}"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {authenticate['access_token']}"
            }
            print("headers")
            print(headers)

            return {
                "url": url,
                "headers": headers,
                'method': salesforce_config.method,
                'type': salesforce_config.type
            }
        
    #  COMPOSITE REST API
    def build_rest_composite_fields(self, salesforce_config, record , fields):
        request_fields = {"allOrNone" : True, 'compositeRequest': []}
        map_ref_fields = {}
        composite_request = []
        map_ref_fields.update({f"New{salesforce_config.sobject_api_name}": {'id': record.id, 'model':salesforce_config.odoo_model_id.model}})
        fields = self.build_rest_fields(salesforce_config,record,fields)
        composite_request.append({
            "method": salesforce_config.method,
            "url": f"/services/data/v{salesforce_config.version}/sobjects/{salesforce_config.sobject_api_name}",
            "referenceId": f"New{salesforce_config.sobject_api_name}",
            "body": fields
        })
        composite_request.append({
            "method": "GET",
            "referenceId": f"New{salesforce_config.sobject_api_name}Info",
            "url": f"/services/data/v{salesforce_config.version}/sobjects/{salesforce_config.sobject_api_name}/@{{New{salesforce_config.sobject_api_name}.id}}"
        })
        for line in record[salesforce_config['child_field_name']['name']].filtered_domain(eval(salesforce_config.child_rel_filter)):
            ref_key = f"New{salesforce_config.sobject_api_name}" + str(len(map_ref_fields) + 1)
            map_ref_fields.update({ref_key: {'id': line.id,'model':salesforce_config['line_rest_config_id']['odoo_model_id']['model']}})
            composite_request.append({
                "method": salesforce_config.line_rest_config_id.method,
                "url": f"/services/data/v{salesforce_config.line_rest_config_id.version}/sobjects/{salesforce_config.line_rest_config_id.sobject_api_name}",
                "referenceId": f"New{salesforce_config.line_rest_config_id.sobject_api_name}{len(map_ref_fields)}",
                "body": self.build_rest_fields(salesforce_config.line_rest_config_id, line, line._fields)
            })
        print("Composite Request")
        print(composite_request)
        request_fields['compositeRequest'] = composite_request
        return {
            'fields': request_fields,
            'map_ref_fields': map_ref_fields
        }

    def build_rest_composite_request_create(self, salesforce_config, record, fields):
        backend = self.env["salesforce.backend"].search([('id', '=', salesforce_config.salesforce_backend_id.id)], limit=1)
        authenticate = backend.authenticate()
        print("Authenticate")
        print(authenticate)
        if authenticate['access_token'] is not None:
            # Your custom logic for update event
            endpoint = salesforce_config.endpoint
            version = salesforce_config.version
            url = f"{endpoint}/services/data/v{version}/composite/"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {authenticate['access_token']}"
            }
            fields = self.build_rest_composite_fields(salesforce_config,record,fields)
            print("Fields Composite")
            print(fields)
            print("headers")
            print(headers)
            return {
                "url": url,
                "headers": headers,
                'fields': json.dumps(fields['fields'], default=self.json_serial),
                'map_ref_fields': fields['map_ref_fields'],
                'method': salesforce_config.method,
                'type': salesforce_config.type
            }

    def build_rest_composite_request_update(self, salesforce_config, record, fields):
        backend = self.env["salesforce.backend"].search([('id', '=', salesforce_config.salesforce_backend_id.id)], limit=1)
        authenticate = backend.authenticate()
        print("Authenticate")
        print(authenticate)
        if authenticate['access_token'] is not None:
            # Your custom logic for update event
            endpoint = salesforce_config.endpoint
            version = salesforce_config.version
            url = f"{endpoint}/services/data/v{version}/composite/"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {authenticate['access_token']}"
            }
            fields = self.build_rest_composite_fields(salesforce_config,record,fields)
            print("Fields Composite")
            print(fields)
            print("headers")
            print(headers)
            return {
                "url": url,
                "headers": headers,
                'fields': json.dumps(fields['fields'], default=self.json_serial),
                'map_ref_fields': fields['map_ref_fields'],
                'method': salesforce_config.method,
                'type': salesforce_config.type
            }

    def build_rest_composite_request_delete(self, salesforce_config, record_id):
        backend = self.env["salesforce.backend"].search([('id', '=', salesforce_config.salesforce_backend_id.id)], limit=1)
        authenticate = backend.authenticate()
        print("Authenticate")
        print(authenticate)
        if authenticate['access_token'] is not None:
            # Your custom logic for update event
            endpoint = salesforce_config.endpoint
            version = salesforce_config.version
            sobject_api_name = salesforce_config.sobject_api_name  # Assuming the SObject API name is Opportunity
            url = f"{endpoint}/services/data/v{version}/composite/tree/{sobject_api_name}"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {authenticate['access_token']}"
            }
            print("headers")
            print(headers)

            return {
                "url": url,
                "headers": headers,
                'method': salesforce_config.method,
                'type': salesforce_config.type
            }


    # CRUD REST
    def build_rest_request_query(self,query ,name):
        salesforce_config = self.env['salesforce.rest.config'].search([('name', '=', name),('active','=', True)], limit=1)
        if not salesforce_config:
            return
        backend = self.env["salesforce.backend"].search([('id', '=', salesforce_config.salesforce_backend_id.id)], limit=1)
        authenticate = backend.authenticate()
        print("Authenticate")
        print(authenticate)
        if authenticate['access_token'] is not None:
            # Your custom logic for update event
            endpoint = salesforce_config.endpoint
            version = salesforce_config.version
            url = f"{endpoint}/services/data/v{version}/query?q="+query
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
        
    def build_rest_request_create(self, record, fields ,name):
        salesforce_config = self.env['salesforce.rest.config'].search([('name', '=', name),('active','=', True)], limit=1)
        if not salesforce_config:
            return
        match salesforce_config.type:
            case 'single':
                return self.build_rest_single_request_create(salesforce_config,record, fields)
            case 'composite':
                return self.build_rest_composite_request_create(salesforce_config,record, fields)    
            case 'bulk':
                return
            
    def build_rest_request_update(self, record, fields ,name):
        salesforce_config = self.env['salesforce.rest.config'].search([('name', '=', name),('active','=', True)], limit=1)
        if not salesforce_config:
            return
        match salesforce_config.type:
            case 'single':
                return self.build_rest_single_request_update(salesforce_config,record, fields)
            case 'composite':
                return self.build_rest_composite_request_update(salesforce_config,record, fields)    
            case 'bulk':
                return
            
    def build_rest_request_delete(self, record_id ,name):
        salesforce_config = self.env['salesforce.rest.config'].search([('name', '=', name),('active','=', True)], limit=1)
        if not salesforce_config:
            return
        match salesforce_config.type:
            case 'single':
                return self.build_rest_single_request_delete(salesforce_config,record_id)
            case 'composite':
                return self.build_rest_composite_request_delete(salesforce_config,record_id)
            case 'bulk':
                return


class SalesforceRestFields(models.Model):
    _name = 'salesforce.rest.fields'
    _description = 'Salesforce REST Fields'
    
    salesforce_rest_config_id = fields.Many2one('salesforce.rest.config', 'Salesforce REST Configuration', required=True, default=lambda self: self.env.context.get('active_id'))
    odoo_model_id = fields.Many2one('ir.model', 'Odoo Model', related='salesforce_rest_config_id.odoo_model_id', readonly=True)
    odoo_field_id = fields.Many2one('ir.model.fields', 'Odoo Field', required=True, ondelete='cascade' , domain="[('model_id', '=', odoo_model_id)]")
    odoo_field_relation_model = fields.Char('Relation Model', related='odoo_field_id.relation', readonly=True)
    odoo_related_field_id = fields.Many2one('ir.model.fields', 'Odoo Related Field', ondelete='cascade', domain="[('model', '=', odoo_field_relation_model)]")
    salesforce_field = fields.Char('Salesforce Field', required=True)
    type = fields.Selection([('string', 'String'), ('integer', 'Integer'), ('float', 'Float'), ('boolean', 'Boolean'), ('date', 'Date'), ('datetime', 'Datetime'), ('related', 'Related')], 'Type', required=True)
    default_value = fields.Char('Default Value')
    active = fields.Boolean('Active', default=True)
    is_record_type = fields.Boolean('Is Record Type', default=False)

class SalesforceRecordType(models.Model):
    _name = 'salesforce.record.type'
    _description = 'Salesforce Record Type'

    salesforce_rest_config_id = fields.Many2one('salesforce.rest.config', 'Salesforce REST Configuration', required=True, default=lambda self: self.env.context.get('active_id'))
    odoo_model_id = fields.Many2one('ir.model', 'Odoo Model', related='salesforce_rest_config_id.odoo_model_id', readonly=True)
    odoo_field_id = fields.Many2one('ir.model.fields', 'Odoo Field', required=True, ondelete='cascade' , domain="[('model_id', '=', odoo_model_id)]")
    type = fields.Selection([('string', 'String'), ('related', 'Related')], 'Type', required=True)
    odoo_field_relation_model = fields.Char('Relation Model', related='odoo_field_id.relation', readonly=True)
    odoo_related_field_id = fields.Many2one('ir.model.fields', 'Odoo Related Field', ondelete='cascade', domain="[('model', '=', odoo_field_relation_model)]")
    odoo_field_value = fields.Char('Odoo Field Value', required=True)
    record_type_id = fields.Char('Record Type ID', required=True)
    active = fields.Boolean('Active', default=True)