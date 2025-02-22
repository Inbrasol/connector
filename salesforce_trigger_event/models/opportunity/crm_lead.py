import requests
import logging
import json

_logger = logging.getLogger(__name__)

from odoo import models, fields, api , _
from datetime import date,datetime
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if
from ..backend.salesforce_rest_utils import SalesforceRestUtils

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
        rest_request = SalesforceRestUtils.build_request(record, fields, 'create', 'crm_lead_create')
        if rest_request:
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            rest_response = SalesforceRestUtils.post(rest_request['url'],rest_request['headers'],rest_request['body'])
            SalesforceRestUtils.update_sf_integration_status(record, rest_response.status_code, rest_response.json(), context_with_skip_sync)
    

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_crm_lead_update(self, record, fields=None):
        if record.sf_id not in [False, None, '']:
            rest_request = SalesforceRestUtils.build_request(record, fields, 'update', 'crm_lead_update')
            if rest_request:
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                rest_response = SalesforceRestUtils.patch(rest_request['url'],rest_request['headers'],rest_request['body'])
                SalesforceRestUtils.update_sf_integration_status(record, rest_response.status_code, rest_response.json(), context_with_skip_sync)


    @skip_if(lambda self: not self)
    def on_crm_lead_unlink(self,record,record_id):
        if record.sf_id not in [False, None, '']:
            rest_request = SalesforceRestUtils.build_request(record, None,'delete','crm_lead_delete')
            if rest_request:
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                rest_response = SalesforceRestUtils.delete(rest_request['url'],rest_request['headers'])
                SalesforceRestUtils.update_sf_integration_status(record, rest_response.status_code, rest_response.json(), context_with_skip_sync)