import requests
import json
import logging
from datetime import date, timedelta
_logger = logging.getLogger(__name__)

class SalesforceRestUtils:

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

    def replace_value(self, json_data, key_to_replace, new_value):
        for item in json_data:
            rich_input = item.get("richInput")
            if rich_input and key_to_replace in rich_input:
                rich_input[key_to_replace] = new_value
        return json_data
    
    def get_operation_type_by_size(self, config, record):
        if config.type == 'composite':
            count = len(record[config.child_field_name.name])
            if count > 200:
                return 'bulk'
            elif 24 <= count <= 199:
                return 'composite_tree'
            else:
                return 'composite_single'
        return config.type

    def update_sf_integration_status(self, record, status_code, response_json, context_with_skip_sync):
        if status_code  in [200, 201, 204]:
            record.with_context(context_with_skip_sync).write({
                'sf_id': response_json['id'],
                'sf_integration_status': 'success',
                'sf_integration_datetime': date.today()
            })
        else:
            _logger.error(f"Failed to update Salesforce record: {response_json}")
            record.with_context(context_with_skip_sync).write({
                'sf_integration_status': 'failed',
                'sf_integration_datetime': date.today(),
                'sf_integration_error': response_json
            })
    
    #  REST API
    def build_rest_fields(self, config, record, fields):
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

        return fields_to_rest

    #  COMPOSITE REST API
    def build_rest_composite_fields(self, config, record , fields):
        request_fields = {"allOrNone" : True, 'compositeRequest': []}
        map_ref_fields = {}
        composite_request = []
        map_ref_fields.update({f"New{config.sobject_api_name}": {'id': record.id, 'model':config.odoo_model_id.model}})
        fields = self.build_rest_fields(config,record,fields)
        composite_request.append({
            "method": config.method,
            "url": f"/services/data/v{config.version}/sobjects/{config.sobject_api_name}",
            "referenceId": f"New{config.sobject_api_name}",
            "body": fields
        })
        composite_request.append({
            "method": "GET",
            "referenceId": f"New{config.sobject_api_name}Info",
            "url": f"/services/data/v{config.version}/sobjects/{config.sobject_api_name}/@{{New{config.sobject_api_name}.id}}"
        })
        for line in record[config['child_field_name']['name']].filtered_domain(eval(config.child_rel_filter)):
            ref_key = f"New{config.sobject_api_name}" + str(len(map_ref_fields) + 1)
            map_ref_fields.update({ref_key: {'id': line.id,'model':config['line_rest_config_id']['odoo_model_id']['model']}})
            composite_request.append({
                "method": config.line_rest_config_id.method,
                "url": f"/services/data/v{config.line_rest_config_id.version}/sobjects/{config.line_rest_config_id.sobject_api_name}",
                "referenceId": f"New{config.line_rest_config_id.sobject_api_name}{len(map_ref_fields)}",
                "body": self.build_rest_fields(config.line_rest_config_id, line, line._fields)
            })

        request_fields['compositeRequest'] = composite_request
        return {
            'body': request_fields,
            'map_ref_fields': map_ref_fields
        }
    
    #   COMPOSITE REST TREE
    def build_rest_composite_tree_fields(self, config, record, fields):
        tree_request = {
            "records": []
        }
        map_ref_fields = {}
        map_ref_fields.update({f"New{config.sobject_api_name}": {'id': record.id, 'model': config.odoo_model_id.model}})
        fields = self.build_rest_fields(config, record, fields)
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
            childs_fields = self.build_rest_fields(config.line_rest_config_id, line, line._fields)
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

    #  COMPOSITE REST BATCH
    def build_rest_composite_batch_fields(self, config, records):
        batch_request = []
        map_ref_fields = {}
        for line in records:
            batch_request.append({
            "method": config.method,
            "url": f"/services/data/v{config.version}/sobjects/{config.sobject_api_name}",
            "richInput": self.build_rest_fields(config, line, line._fields)
            })

        return {
            'batchRequest': batch_request,
            'map_ref_fields': map_ref_fields
        }

    #  BULK 2.0
    def build_bulk_request_fields(self, config, records):
        json_records = []
        for line in records:
            json_records.append(self.build_rest_fields(config, line, line._fields))

        return json.dumps(json_records, default=self.json_serial)