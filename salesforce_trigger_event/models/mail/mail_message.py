import logging
from odoo import models, fields, api
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if
from ..backend.salesforce_rest_utils import SalesforceRestUtils

_logger = logging.getLogger(__name__)

class MailMessage(models.Model):
    _inherit = 'mail.message'

    is_salesforce = fields.Boolean(string='Salesforce Message', default=False)

    def create(self, vals):
        if len(self) > 1:
            return super(MailMessage, self).write(vals)
        
        if not self.is_salesforce:
            return super(MailMessage, self).create(vals)
        
        if self.env.context.get('skip_sync'):
            return super(MailMessage, self).create(vals)

        message = super(MailMessage, self).create(vals)
        fields = self._fields.keys()
        if self.is_salesforce:
            self._event('on_mail_message_create').notify(message, fields=fields)
        return message

    def write(self, vals):
        if len(self) > 1:
            return super(MailMessage, self).write(vals)
        
        if not self.is_salesforce:
            return super(MailMessage, self).create(vals)
        
        if self.env.context.get('skip_sync'):
            return super(MailMessage, self).write(vals)

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
        super(MailMessage, self.with_context(context_with_skip_sync)).write(vals)
        if self.sf_id is False and self.is_salesforce:
            self._event('on_mail_message_create').notify(self, changed_fields)
        if len(changed_fields) > 0 :
            self._event('on_mail_message_update').notify(self, changed_fields)
        return self

    def unlink(self):
        if len(self) > 1:
            return super(MailMessage, self).unlink()
        
        if not self.is_salesforce:
            return super(MailMessage, self).unlink()
    
        if self.env.context.get('skip_sync'):
            return super(MailMessage, self).unlink()

        message_ids = self.env['mail.message'].search([('id', 'in', self.ids)]).mapped('sf_id')
        self._event('on_mail_message_delete').notify(message_ids)
        return super(MailMessage, self).unlink()


class MailMessageEventListener(Component):
    _name = 'mail.message.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['mail.message']

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_mail_message_create(self, record, fields=None):
        rest_request = self.env['salesforce.rest.config'].build_request(record, fields, 'create', 'mail_message_create')
        if rest_request:
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            rest_response = SalesforceRestUtils.post(rest_request['url'], rest_request['headers'], rest_request['body'])
            if rest_response and rest_response.status_code in [200, 201]:
                SalesforceRestUtils._handle_successful_response(self, rest_request, rest_response, context_with_skip_sync)
            else:
                SalesforceRestUtils._handle_failed_response(record, rest_response, context_with_skip_sync)

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_mail_message_update(self, record, fields=None):
        if record.id:
            rest_request = self.env['salesforce.rest.config'].build_request(record, fields, 'update', 'mail_message_update')
            if rest_request:
                context_with_skip_sync = dict(self.env.context, skip_sync=True)
                rest_response = SalesforceRestUtils.patch(rest_request['url'], rest_request['headers'], rest_request['body'])
                SalesforceRestUtils._update_sf_integration_status(record, rest_response, context_with_skip_sync)

    @skip_if(lambda self, records: not records)
    def on_mail_message_delete(self, records):
        rest_request = self.env['salesforce.rest.config'].build_request(records, None, 'delete', 'mail_message_delete')
        if rest_request:
            context_with_skip_sync = dict(self.env.context, skip_sync=True)
            rest_response = SalesforceRestUtils.delete(rest_request['url'], rest_request['headers'])
            SalesforceRestUtils._handle_successful_response(self, rest_request, rest_response, context_with_skip_sync)