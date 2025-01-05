import requests
import json
from datetime import date

class SalesforceRestUtils:

    def get(self, url, headers):
        response = requests.get(url, headers= headers)
        return response.json()

    def post(self, url, headers, data):
        response = requests.post(url, headers=headers, data=data)
        return response.json()

    def patch(self, url, headers, data):
        response = requests.patch(url, headers= headers, data=data)
        return response.json()

    def delete(self, url, headers):
        response = requests.delete(url, headers = headers)
        return response.status_code

    def json_serial(self,obj):
        #JSON serializer for objects not serializable by default json code
        if isinstance(obj, date):
            return obj.strftime('%Y-%m-%d')
        raise TypeError(f"Type {type(obj)} not serializable")
    

    def build_rest_fields(self, sf_config, record):
        fields_to_rest = {}
        for field in sf_config.rest_fields:
            match field.type:
                case 'string' | 'integer' | 'float' | 'boolean':
                    fields_to_rest[field.salesforce_field] = getattr(record,field.odoo_field_id.name)
                case 'date' | 'datetime':
                    fields_to_rest[field.salesforce_field] = getattr(record,field.odoo_field_id.name)
                case 'related':
                    fields_to_rest[field.salesforce_field] = getattr(record,field.odoo_field_id.name)[field.odoo_related_field_id.name]
                case _:
                    fields_to_rest[field.salesforce_field] = getattr(record,field.odoo_field_id.name)
        
        return json.dumps(fields_to_rest, default=self.json_serial)

    def build_rest_request_create(self, listener, record,name):
        salesforce_config = listener.env['salesforce.rest.config'].search([('name', '=', name),('active','=', True)], limit=1)
        if not salesforce_config:
            return
        backend = listener.env["salesforce.backend"].search([('id', '=', salesforce_config.salesforce_backend_id.id)], limit=1)
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
            
            fields = self.build_rest_fields(salesforce_config,record)

            return {
                "url": url,
                "headers": headers,
                'fields': fields
            }