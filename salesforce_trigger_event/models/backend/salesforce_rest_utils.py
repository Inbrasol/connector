import requests
import json
import logging
from datetime import date, datetime, timedelta

_logger = logging.getLogger(__name__)

class SalesforceRestUtils:

    @staticmethod
    def get(url, headers):
        try:
            _logger.error(f"GET request url: {url}")
            _logger.error(f"GET request headers: {headers}")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            _logger.error(f"GET request data: {response}")
            return response
        except requests.exceptions.RequestException as e:
            _logger.error(f"GET request failed: {e}")
            return None

    @staticmethod
    def post(url, headers, data):
        try:
            _logger.error(f"POST request url: {url}")
            _logger.error(f"POST request headers: {headers}")
            _logger.error(f"POST request data: {data}")
            response = requests.post(url, headers=headers, data=data)
            _logger.error(f"POST request data: {response.json()}")
            response.raise_for_status()
            _logger.error(f"POST request data: {response}")
            _logger.error(f"POST request data: {response.json()}")
            return response
        except requests.exceptions.RequestException as e:
            _logger.error(f"POST request failed: {e}")
            return None

    @staticmethod
    def put(url, headers, data):
        try:
            _logger.error(f"PUT request url: {url}")
            _logger.error(f"PUT request headers: {headers}")
            _logger.error(f"PUT request data: {data}")
            response = requests.put(url, headers=headers, data=data)
            response.raise_for_status()
            _logger.error(f"PUT request data: {response}")
            return response
        except requests.exceptions.RequestException as e:
            _logger.error(f"PUT request failed: {e}")
            return None
    
    @staticmethod
    def patch(url, headers, data):
        try:
            _logger.error(f"PATCH request url: {url}")
            _logger.error(f"PATCH request headers: {headers}")
            _logger.error(f"PATCH request data: {data}")
            response = requests.patch(url, headers=headers, data=data)
            response.raise_for_status()
            _logger.error(f"PATCH request data: {response}")
            return response
        except requests.exceptions.RequestException as e:
            _logger.error(f"PATCH request failed: {e}")
            return None

    @staticmethod
    def delete(url, headers):
        try:
            _logger.error(f"DELETE request url: {url}")
            _logger.error(f"DELETE request headers: {headers}")
            response = requests.delete(url, headers=headers)
            response.raise_for_status()
            _logger.error(f"DELETE request data: {response}")
            return response
        except requests.exceptions.RequestException as e:
            _logger.error(f"DELETE request failed: {e}")
            return None

    @staticmethod
    def json_serial(obj):
        if isinstance(obj, date):
            return obj.strftime('%Y-%m-%d')
        raise TypeError(f"Type {type(obj)} not serializable")

    @staticmethod
    def replace_value(json_data, key_to_replace, new_value):
        if isinstance(json_data, list):
            for item in json_data:
                rich_input = item.get("richInput")
                if rich_input and key_to_replace in rich_input:
                    rich_input[key_to_replace] = new_value
        return json_data

    #UPDATE RECORDS
    
    @staticmethod
    def build_rest_fields(config, record, fields):
        _logger.error(f"fields in build: {fields}")
        fields_to_rest = {}
        date_mappings = {
            'YESTERDAY': lambda: date.today() - timedelta(days=1),
            'TODAY': lambda: date.today(),
            'TOMORROW': lambda: date.today() + timedelta(days=1),
            'LAST_WEEK': lambda: date.today() - timedelta(days=date.today().weekday() + 7),
            'THIS_WEEK': lambda: date.today() - timedelta(days=date.today().weekday()),
            'NEXT_WEEK': lambda: date.today() + timedelta(days=6 - date.today().weekday() + 7),
            'LAST_MONTH': lambda: date.today().replace(day=1) - timedelta(days=1),
            'THIS_MONTH': lambda: date.today().replace(day=1),
            'NEXT_MONTH': lambda: date.today().replace(day=28) + timedelta(days=4),
            'LAST_90_DAYS': lambda: date.today() - timedelta(days=90),
            'NEXT_90_DAYS': lambda: date.today() + timedelta(days=90),
        }

        datetime_mappings = {
            'YESTERDAY': lambda: (date.today() - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'TODAY': lambda: date.today().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'TOMORROW': lambda: (date.today() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'LAST_WEEK': lambda: (date.today() - timedelta(days=date.today().weekday() + 7)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'THIS_WEEK': lambda: (date.today() - timedelta(days=date.today().weekday())).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'NEXT_WEEK': lambda: (date.today() + timedelta(days=6 - date.today().weekday() + 7)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'LAST_MONTH': lambda: (date.today().replace(day=1) - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'THIS_MONTH': lambda: date.today().replace(day=1).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'NEXT_MONTH': lambda: (date.today().replace(day=28) + timedelta(days=4)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'LAST_90_DAYS': lambda: (date.today() - timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'NEXT_90_DAYS': lambda: (date.today() + timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%SZ'),
        }

        def get_default_value(field):
            if field.type == 'date':
                return date_mappings.get(field.default_value, lambda: date.today())()
            elif field.type == 'datetime':
                return datetime_mappings.get(field.default_value, lambda: date.today().strftime('%Y-%m-%dT%H:%M:%SZ'))()
            return field.default_value
        
        for field in config.rest_fields.filtered(lambda f: f.active):
            if field.default_value not in [None, '', False]:
                fields_to_rest[field.salesforce_field] = get_default_value(field)
            elif field.odoo_field_id.name in fields:
                value = getattr(record, field.odoo_field_id.name)
                if field.type == 'related' and value:
                    value = value[field.odoo_related_field_id.name]
                if value not in [None, '', False]:
                    fields_to_rest[field.salesforce_field] = value
            elif field.is_always_update:
                fields_to_rest[field.salesforce_field] = getattr(record, field.odoo_field_id.name)

        for record_type in config.record_types.filtered(lambda r: r.active):
            related_value = getattr(record, record_type.odoo_field_id.name)
            if (record_type.type == 'string' and related_value == record_type.odoo_field_value) or \
               (record_type.type == 'related' and related_value and related_value[record_type.odoo_related_field_id.name] == record_type.odoo_field_value):
                fields_to_rest['RecordTypeId'] = record_type.record_type_id

        _logger.error(f"fields_to_rest: {fields_to_rest}")
        return fields_to_rest

    @staticmethod
    def _update_sf_integration_status(record, rest_response, context_with_skip_sync):
        if rest_response is None:
            _logger.error("Salesforce response is None. Cannot update integration status.")
            record.with_context(context_with_skip_sync).write({
                'sf_integration_status': 'failed',
                'sf_integration_datetime': datetime.now(),
                'sf_integration_error': 'No response received from Salesforce'
            })
            return

        timestamp = datetime.now()
        response_json = {}

        # Si la respuesta es 204 (No Content), simplemente marcar como éxito sin parsear JSON
        if rest_response.status_code == 204:
            record.with_context(context_with_skip_sync).write({
                'sf_integration_status': 'success',
                'sf_integration_datetime': timestamp
            })
            return

        # Intentar parsear JSON solo si la respuesta tiene contenido
        if rest_response.text:
            try:
                if rest_response.headers.get("Content-Type", "").startswith("application/json"):
                    response_json = rest_response.json()
            except ValueError:
                _logger.error(f"Failed to parse JSON response: {rest_response.text}")

        if rest_response.status_code in {200, 201}:
            update_values = {
                'sf_integration_status': 'success',
                'sf_integration_datetime': timestamp
            }
            if response_json.get('id'):
                update_values['sf_id'] = response_json['id']
            record.with_context(context_with_skip_sync).write(update_values)
        else:
            error_message = response_json if response_json else rest_response.text or f"HTTP {rest_response.status_code} (No content)"
            _logger.error(f"Salesforce update failed. Status: {rest_response.status_code}, Response: {error_message}")

            record.with_context(context_with_skip_sync).write({
                'sf_integration_status': 'failed',
                'sf_integration_datetime': timestamp,
                'sf_integration_error': error_message
            })

    def _handle_successful_response(self, rest_request, rest_response, context_with_skip_sync):
        if rest_request['type'] in ['composite_collection','composite_tree','composite']:
            SalesforceRestUtils._process_composite_response(self, rest_request, rest_response, context_with_skip_sync)
        elif rest_request['type'] == 'rest':
            SalesforceRestUtils._update_record_with_response(self, rest_request, rest_response, context_with_skip_sync)

    def _process_composite_response(self, rest_request, rest_response, context_with_skip_sync):
        response_data = rest_response.json()
        if rest_request['type'] == 'composite':
            SalesforceRestUtils._update_records_from_composite_response(self,response_data['compositeResponse'], rest_request, context_with_skip_sync)
        elif rest_request['type'] == 'composite_tree':
            SalesforceRestUtils._update_records_from_composite_response(self, response_data['results'], rest_request, context_with_skip_sync)
        elif rest_request['type'] == 'composite_collection':
            SalesforceRestUtils._update_sf_integration_status_collection(self, response_data, rest_request, context_with_skip_sync)

    def _update_records_from_composite_response(self, responses, rest_request, context_with_skip_sync):
        for record_response in responses:
            if record_response['referenceId'] in rest_request['map_ref_fields']:
                map_field = rest_request['map_ref_fields'][record_response['referenceId']]
                record_to_update = self.env[map_field['model']].browse(map_field['id'])
                record_to_update.with_context(context_with_skip_sync).write({
                    'sf_id': record_response.get('id'),
                    'sf_integration_status': 'success',
                    'sf_integration_datetime': datetime.now()
                })

    def _update_sf_integration_status_collection(self, responses, rest_request, context_with_skip_sync):
        for record_response in responses:
            map_field = rest_request['map_ref_fields'][record_response['id']]
            record_to_update = self.env[map_field['model']].browse(map_field['id'])
            if record_response.get('success', False):
                record_to_update.with_context(context_with_skip_sync).write({
                    'sf_id': record_response.get('id'),
                    'sf_integration_status': 'success',
                    'sf_integration_datetime': datetime.now()
                })
            else:
                error_message = record_response.get('errors', 'Unknown error')
                _logger.error(f"Salesforce update failed for record {record_to_update.id}. Error: {error_message}")
                record_to_update.with_context(context_with_skip_sync).write({
                    'sf_integration_status': 'failed',
                    'sf_integration_datetime': datetime.now(),
                    'sf_integration_error': error_message
                })

    def _update_record_with_response(self, rest_request, rest_response, context_with_skip_sync):
        record = self.env[rest_request['model']].browse(rest_request['id'])
        record.with_context(context_with_skip_sync).write({
            'sf_id': rest_response.json()['id'],
            'sf_integration_status': 'success',
            'sf_integration_datetime': datetime.now()
        })
    
    def _handle_failed_response(record, rest_response, context_with_skip_sync):
        #_logger.error(f"Failed to update Salesforce record: {rest_response.content}")
        if rest_response is not None:
            record.with_context(context_with_skip_sync).write({
            'sf_integration_status': 'failed',
            'sf_integration_datetime': datetime.now(),
            'sf_integration_error': rest_response.text
            })


    #SINGLE RECORD
    @staticmethod
    def build_rest_composite_tree_nested_fields(config, record, fields):
        tree_request = {"records": []}
        map_ref_fields = {}
        map_ref_fields.update({f"New{config.sobject_api_name}": {'id': record.id, 'model': config.odoo_model_id.model}})
        fields = SalesforceRestUtils.build_rest_fields(config, record, fields)
        main_record = {
            "attributes": {
                "type": config.sobject_api_name,
                "referenceId": f"New{config.sobject_api_name}"
            },
            **fields,
            config.child_rel_name: {
                "records": []
            }
        }
        for line in record[config.child_field_name.name].filtered_domain(eval(config.child_rel_filter)):
            ref_key = f"New{config.sobject_api_name}" + str(len(map_ref_fields) + 1)
            map_ref_fields.update({ref_key: {'id': line.id, 'model': config.line_rest_config_id.odoo_model_id.model}})
            childs_fields = SalesforceRestUtils.build_rest_fields(config.line_rest_config_id, line, line._fields)
            fields_to_remove = config.line_rest_config_id.rest_fields.filtered(lambda f: f.remove_to_composite)
            for field in fields_to_remove:
                if field.salesforce_field in childs_fields:
                    del childs_fields[field.salesforce_field]
            
            main_record[config.child_rel_name]["records"].append({
                "attributes": {
                    "type": config.line_rest_config_id.sobject_api_name,
                    "referenceId": f"New{config.line_rest_config_id.sobject_api_name}{len(map_ref_fields)}"
                },
                **childs_fields
            })
            
        tree_request["records"].append(main_record)
        
        return {
            'body': tree_request,
            'map_ref_fields': map_ref_fields
        }

    @staticmethod
    def build_rest_composite_nested_fields(config, record, fields):
        request_fields = {"allOrNone": True, 'compositeRequest': []}
        map_ref_fields = {}
        map_ref_fields.update({f"New{config.sobject_api_name}": {'id': record.id, 'model': config.odoo_model_id.model}})
        fields = SalesforceRestUtils.build_rest_fields(config, record, fields)
        composite_request = [
            {
                "method": config.method,
                "url": f"/services/data/v{config.version}/sobjects/{config.sobject_api_name}",
                "referenceId": f"New{config.sobject_api_name}",
                "body": fields
            },
            {
                "method": "GET",
                "referenceId": f"New{config.sobject_api_name}Info",
                "url": f"/services/data/v{config.version}/sobjects/{config.sobject_api_name}/@{{New{config.sobject_api_name}.id}}"
            }
        ]
        for line in record[config['child_field_name']['name']].filtered_domain(eval(config.child_rel_filter)):
            ref_key = f"New{config.sobject_api_name}" + str(len(map_ref_fields) + 1)
            map_ref_fields.update({ref_key: {'id': line.id, 'model': config['line_rest_config_id']['odoo_model_id']['model']}})
            composite_request.append({
                "method": config.line_rest_config_id.method,
                "url": f"/services/data/v{config.line_rest_config_id.version}/sobjects/{config.line_rest_config_id.sobject_api_name}",
                "referenceId": f"New{config.line_rest_config_id.sobject_api_name}{len(map_ref_fields)}",
                "body": SalesforceRestUtils.build_rest_fields(config.line_rest_config_id, line, line._fields)
            })

        request_fields['compositeRequest'] = composite_request
        return {
            'body': request_fields,
            'map_ref_fields': map_ref_fields
        }
    
    #COLLECTION RECORDS
    @staticmethod
    def build_rest_composite_fields(config, records, fields):
        request_fields = {"allOrNone": True, 'compositeRequest': []}
        map_ref_fields = {}
        for record in records:
            map_ref_fields.update({f"New{config.sobject_api_name}{record.id}": {'id': record.id, 'model': config.odoo_model_id.model}})
            record_fields = SalesforceRestUtils.build_rest_fields(config, record, fields)
            composite_request = {
                "method": config.method,
                "url": f"/services/data/v{config.version}/sobjects/{config.sobject_api_name}",
                "referenceId": f"New{config.sobject_api_name}{record.id}",
                "body": record_fields
            }
            request_fields['compositeRequest'].append(composite_request)

        return {
            'body': request_fields,
            'map_ref_fields': map_ref_fields
        }

    @staticmethod
    def build_rest_composite_tree_fields(config, records, fields):
        tree_request = {"records": []}
        map_ref_fields = {}
        for record in records:
            map_ref_fields.update({f"New{config.sobject_api_name}{record.id}": {'id': record.id, 'model': config.odoo_model_id.model}})
            record_fields = SalesforceRestUtils.build_rest_fields(config, record, fields)
            main_record = {
                "attributes": {
                    "type": config.sobject_api_name,
                    "referenceId": f"New{config.sobject_api_name}{record.id}"
                },
                **record_fields
            }    
            tree_request["records"].append(main_record)
        return {
            'body': tree_request,
            'map_ref_fields': map_ref_fields
        }

    @staticmethod
    def build_rest_composite_collection_fields(config, records, fields, operation):
        request_fields = {"allOrNone": True, "records": []}
        for record in records:
            record_fields = SalesforceRestUtils.build_rest_fields(config, record, fields)
            if operation == 'update':
                record_fields['id'] = record.sf_id
            
            record_data = {
                "attributes": {"type": config.sobject_api_name},
                **record_fields
            }
            request_fields["records"].append(record_data)
        
        return {
            'body': request_fields,
            'map_ref_fields': None
        }

    @staticmethod
    def build_rest_composite_batch_fields(config, records):
        batch_request = []
        map_ref_fields = {}
        for line in records:
            batch_request.append({
                "method": config.method,
                "url": f"/services/data/v{config.version}/sobjects/{config.sobject_api_name}",
                "richInput": SalesforceRestUtils.build_rest_fields(config, line, line._fields)
            })

        return {
            'batchRequest': batch_request,
            'map_ref_fields': map_ref_fields
        }

    @staticmethod
    def build_bulk_request_fields(config, records):
        json_records = []
        for line in records:
            json_records.append(SalesforceRestUtils.build_rest_fields(config, line, line._fields))

        return json.dumps(json_records, default=SalesforceRestUtils.json_serial)