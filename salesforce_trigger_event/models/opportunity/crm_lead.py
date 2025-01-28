import requests
import logging
import json

_logger = logging.getLogger(__name__)

from odoo import models, fields, api , _
from datetime import date,datetime
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if


class CrmLead(models.Model):
    _inherit = 'crm.lead'
    
    @api.model
    def create(self, vals):
        lead = super(CrmLead, self).create(vals)
        self._event('on_crm_lead_create').notify(lead,fields=vals.keys())
        return lead


    @api.model
    def write(self, vals):
        if self.env.context.get('skip_sync'):
            super(CrmLead, self).write(vals)
            return self
        print("Vals")
        print(vals)
        # Set skip_sync in context to avoid recursion
        context_with_skip_sync = dict(self.env.context, skip_sync=True)
        changed_fields = []
        for field, value in vals.items():
            print("Field")
            print(field)
            print("Value")
            print(value)
            if self._fields[field].type in ['one2many', 'many2many']:
                continue
            elif isinstance(self[field], models.BaseModel):
                if self[field].id != value:
                    changed_fields.append(field)
            elif self[field] != value:
                changed_fields.append(field)
        super(CrmLead, self.with_context(context_with_skip_sync)).write(vals)
        if len(changed_fields) > 0:
            self._event('on_crm_lead_update').notify(self, changed_fields)

        print("CRM Lead Update")
        print(self)
        return self
    

    @api.model
    def unlink(self, vals):
        lead = super(CrmLead, self).unlink()
        self._event('on_crm_lead_unlink').notify(lead,lead.id)
        return lead


class CrmLeadEventListener(Component):
    _name = 'crm.lead.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['crm.lead']


    @skip_if(lambda self, record, fields: not record or not fields)
    def on_crm_lead_create(self, record, fields=None):
        print("Fields")
        print(fields)
        rest_request = self.env['salesforce.rest.config'].build_rest_request_create(record,fields,'crm_lead_create')
        if rest_request:
            rest_response = self.env['salesforce.rest.config'].post(rest_request['url'],rest_request['headers'],rest_request['fields'])
            print("Response")
            print(rest_response)
            if rest_response.status_code == 201:
                record.write({
                    'sf_id': rest_response.json()['id'],
                    'sf_integration_status': 'success',
                    'sf_integration_datetime': datetime.now()
                })
            else:
                _logger.error(f"Failed to update Salesforce record: {rest_response.content}")
                record.write({
                    'sf_integration_status': 'failed',
                    'sf_integration_datetime': datetime.now(),
                    'sf_integration_error': rest_response.json()
                    })
    

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_crm_lead_update(self, record, fields=None):
        print("Fields")
        print(fields)
        if record.sf_id not in [False, None, '']:
            rest_request = self.env['salesforce.rest.config'].build_rest_request_update(record,fields,'crm_lead_update')
            if rest_request:
                rest_response = self.env['salesforce.rest.config'].patch(rest_request['url'],rest_request['headers'],rest_request['fields'])
                print("Response")
                print(rest_response)
                if rest_response.status_code == 204:
                    record.write({
                        'sf_integration_status': 'success',
                        'sf_integration_datetime': datetime.now()
                    })
                else:
                    _logger.error(f"Failed to update Salesforce record: {rest_response.content}")
                    record.write({
                        'sf_integration_status': 'failed',
                        'sf_integration_datetime': datetime.now(),
                        'sf_integration_error': rest_response.json()
                    })

    @skip_if(lambda self: not self)
    def on_crm_lead_unlink(self,record,record_id):
        print("record_id")
        print(record_id)
        if record.sf_id not in [False, None, '']:
            rest_request = self.env['salesforce.rest.config'].build_rest_request_delete(record_id,'crm_lead_delete')
            if rest_request:
                rest_response = self.env['salesforce.rest.config'].delete(rest_request['url'],rest_request['headers'])
                print("Response")
                print(rest_response)
                if rest_response.status_code != 204:
                    _logger.error(f"Failed to update Salesforce record: {rest_response.content}")
                    record.write({
                        'sf_integration_status': 'failed',
                        'sf_integration_datetime': datetime.now(),
                        'sf_integration_error': rest_response.json()
                    })