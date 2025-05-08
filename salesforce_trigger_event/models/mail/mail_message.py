import logging
from odoo import models, fields, api
from odoo.tools import html2plaintext
import requests
from odoo.addons.component.core import Component
from odoo.addons.component_event import skip_if
from ..backend.salesforce_rest_utils import SalesforceRestUtils

_logger = logging.getLogger(__name__)

class MailMessage(models.Model):
    _inherit = 'mail.message'

    is_salesforce = fields.Boolean(string='Salesforce Message', default=False)
    
    """
    def create(self, vals):
        _logger.error("Create message in Salesforce...")
        _logger.error(f"Is Salesforce: {self.is_salesforce}")
        _logger.error(f"Is vals: {vals}")
        if len(self) > 1:
            return super(MailMessage, self).create(vals)
        
        if self.env.context.get('skip_sync'):
            return super(MailMessage, self).create(vals)

        message = super(MailMessage, self).create(vals)
        fields = self._fields.keys()
        _logger.error(f"Message fields: {fields}")
        self._event('on_mail_message_create').notify(message, fields=fields)
        return message
    """

    def write(self, vals):
        _logger.error("Modify message in Salesforce...")
        _logger.error(f"Is Salesforce: {self.is_salesforce}")
        _logger.error(f"sf_id : {self.sf_id}")
        _logger.error(f"vals : {vals}")
        if len(self) > 1:
            return super(MailMessage, self).write(vals)
        
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
        _logger.error(f"Message fields: {changed_fields}")
        if self.sf_id in [False, None, ''] and self.is_salesforce:
            self._event('on_mail_message_create').notify(self, changed_fields)
        if self.sf_id and len(changed_fields) > 0 :
            self._event('on_mail_message_update').notify(self, changed_fields)
        return self

    def unlink(self):
        if len(self) > 1:
            return super(MailMessage, self).unlink()
        
        if not self.is_salesforce:
            return super(MailMessage, self).unlink()
    
        if self.env.context.get('skip_sync'):
            return super(MailMessage, self).unlink()

        self._event('on_mail_message_delete').notify(self)
        return super(MailMessage, self).unlink()
    

class MailMessageEventListener(Component):
    _name = 'mail.message.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['mail.message']

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_mail_message_create(self, record, fields=None):
        if record.is_salesforce:
            _logger.info("Creating message in Salesforce...")
            salesforce_backend = self.env['salesforce.backend'].search([('active', '=', True)], limit=1)
            if not salesforce_backend:
                _logger.error("No active Salesforce backend found.")
                return

            authenticate = salesforce_backend.authenticate()
            if not authenticate:
                _logger.error("Salesforce authentication failed.")
                return

            headers = {
                'Authorization': f'Bearer {authenticate["access_token"]}',
                'Content-Type': 'application/json'
            }

            url = f"{salesforce_backend.url}/services/data/v{salesforce_backend.api_version}/chatter/feed-elements"
            record_id = self.env[record.model].browse(record.res_id).sf_id

            sf_user = self.env['salesforce.user'].search([('partner_id', 'in', record.partner_ids.ids)], limit=1)
            if not sf_user:
                _logger.error("No Salesforce user found for the record.")
                return

            if not record_id:
                _logger.error("No Salesforce ID found for the record.")
                return
            if not record.body:
                _logger.error("No body found for the record.")
                return
            if not record.res_id:
                _logger.error("No resource ID found for the record.")
                return
            if not record.model:
                _logger.error("No resource model found for the record.")
                return

            data = {
                "body": {
                    "messageSegments": [
                        {
                            "type": "Mention",
                            "id": sf_user.sf_id,
                        },
                        {
                            "type": "Text",
                            "text": html2plaintext(record.body)
                        }
                    ]
                },
                "feedElementType": "FeedItem",
                "subjectId": record_id
            }

            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 201:
                _logger.info("Message successfully created in Salesforce.")
                response_data = response.json()
                record.write({'sf_id': response_data.get('id')})
                _logger.info(f"Salesforce ID: {record.sf_id}")
                # Handle attachments if present
                attachments = self.env['ir.attachment'].search([('res_model', '=', 'mail.message'), ('res_id', '=', record.id)])
                for attachment in attachments:
                    attachment_url = f"{salesforce_backend.url}/services/data/v{salesforce_backend.api_version}/sobjects/ContentVersion"
                    attachment_data = {
                        "Title": attachment.name,
                        "PathOnClient": attachment.name,
                        "VersionData": attachment.datas.decode('utf-8'),
                    }
                    attachment_response = requests.post(attachment_url, headers=headers, json=attachment_data)
                    if attachment_response.status_code == 201:
                        _logger.info(f"Attachment {attachment.name} successfully uploaded to Salesforce.")
                        # Associate the uploaded attachment with the FeedItem
                        content_document_id = attachment_response.json().get('contentDocumentId')
                        if content_document_id:
                            feed_attachment_url = f"{salesforce_backend.url}/services/data/v{salesforce_backend.api_version}/chatter/feed-elements/{response_data.get('id')}/capabilities/files/items"
                            feed_attachment_data = {
                                "contentDocumentId": content_document_id
                            }
                            feed_attachment_response = requests.post(feed_attachment_url, headers=headers, json=feed_attachment_data)
                            if feed_attachment_response.status_code == 201:
                                _logger.info(f"Attachment {attachment.name} successfully associated with FeedItem in Salesforce.")
                            else:
                                _logger.error(f"Failed to associate attachment {attachment.name} with FeedItem in Salesforce. Status: {feed_attachment_response.status_code}, Response: {feed_attachment_response.text}")
                        else:
                            _logger.error(f"Failed to retrieve contentDocumentId for attachment {attachment.name}.")
                    else:
                        _logger.error(f"Failed to upload attachment {attachment.name} to Salesforce. Status: {attachment_response.status_code}, Response: {attachment_response.text}")
            else:
                _logger.error(f"Failed to create message in Salesforce. Status: {response.status_code}, Response: {response.text}")

    @skip_if(lambda self, record, fields: not record or not fields)
    def on_mail_message_update(self, record, fields=None):
        if record.is_salesforce:
            _logger.info("Updating message in Salesforce...")
            salesforce_backend = self.env['salesforce.backend'].search([('active', '=', True)], limit=1)
            if not salesforce_backend:
                _logger.error("No active Salesforce backend found.")
                return

            authenticate = salesforce_backend.authenticate()
            if not authenticate:
                _logger.error("Salesforce authentication failed.")
                return

            headers = {
                'Authorization': f'Bearer {authenticate["access_token"]}',
                'Content-Type': 'application/json'
            }

            if not record.sf_id:
                _logger.error("No Salesforce ID found for the record.")
                return
            if not record.body:
                _logger.error("No body found for the record.")
                return
            if not record.res_id:
                _logger.error("No resource ID found for the record.")
                return
            if not record.model:
                _logger.error("No resource model found for the record.")
                return

            # Delete the previous message
            _logger.error(f"Salesforce ID: {record.sf_id}")
            url_delete = f"{salesforce_backend.url}/services/data/v{salesforce_backend.api_version}/sobjects/FeedItem/{record.sf_id}"
            response_delete = requests.delete(url_delete, headers=headers)
            _logger.error(f"response_delete: {response_delete}")
            if response_delete.status_code == 204:
                _logger.info("Previous message successfully deleted in Salesforce.")
                url = f"{salesforce_backend.url}/services/data/v{salesforce_backend.api_version}/chatter/feed-elements"
                record_id = self.env[record.model].browse(record.res_id).sf_id
                sf_user = self.env['salesforce.user'].search([('partner_id', 'in', record.partner_ids.ids)], limit=1)
                if not sf_user:
                    _logger.error("No Salesforce user found for the record.")
                    return
                if not record_id:
                    _logger.error("No Salesforce ID found for the record.")
                    return
                if not record.body:
                    _logger.error("No body found for the record.")
                    return

                data = {
                    "body": {
                        "messageSegments": [
                            {
                                "type": "Mention",
                                "id": sf_user.sf_id,
                            },
                            {
                                "type": "Text",
                                "text": html2plaintext(record.body)
                            }
                        ]
                    },
                    "feedElementType": "FeedItem",
                    "subjectId": record_id
                }
                response = requests.post(url, headers=headers, json=data)
                if response.status_code == 201:
                    _logger.info("Message successfully created in Salesforce.")
                    response_data = response.json()
                    record.write({'sf_id': response_data.get('id')})
                    _logger.info(f"Salesforce ID: {record.sf_id}")
                    # Handle attachments if present
                    attachments = self.env['ir.attachment'].search([('res_model', '=', 'mail.message'), ('res_id', '=', record.id)])
                    for attachment in attachments:
                        attachment_url = f"{salesforce_backend.url}/services/data/v{salesforce_backend.api_version}/sobjects/ContentVersion"
                        attachment_data = {
                            "Title": attachment.name,
                            "PathOnClient": attachment.name,
                            "VersionData": attachment.datas.decode('utf-8'),
                        }
                        attachment_response = requests.post(attachment_url, headers=headers, json=attachment_data)
                        if attachment_response.status_code == 201:
                            _logger.info(f"Attachment {attachment.name} successfully uploaded to Salesforce.")
                            # Associate the uploaded attachment with the FeedItem
                            content_document_id = attachment_response.json().get('contentDocumentId')
                            if content_document_id:
                                feed_attachment_url = f"{salesforce_backend.url}/services/data/v{salesforce_backend.api_version}/chatter/feed-elements/{response_data.get('id')}/capabilities/files/items"
                                feed_attachment_data = {
                                    "contentDocumentId": content_document_id
                                }
                                feed_attachment_response = requests.post(feed_attachment_url, headers=headers, json=feed_attachment_data)
                                if feed_attachment_response.status_code == 201:
                                    _logger.info(f"Attachment {attachment.name} successfully associated with FeedItem in Salesforce.")
                                else:
                                    _logger.error(f"Failed to associate attachment {attachment.name} with FeedItem in Salesforce. Status: {feed_attachment_response.status_code}, Response: {feed_attachment_response.text}")
                            else:
                                _logger.error(f"Failed to retrieve contentDocumentId for attachment {attachment.name}.")
                        else:
                            _logger.error(f"Failed to upload attachment {attachment.name} to Salesforce. Status: {attachment_response.status_code}, Response: {attachment_response.text}")
                else:
                    _logger.error(f"Failed to create message in Salesforce. Status: {response.status_code}, Response: {response.text}")

    @skip_if(lambda self, record: not record)
    def on_mail_message_delete(self, record):
        if record.is_salesforce and record.sf_id:
            _logger.info("Deleting message in Salesforce...")
            salesforce_backend = self.env['salesforce.backend'].search([('active', '=', True)], limit=1)
            if not salesforce_backend:
                _logger.error("No active Salesforce backend found.")
                return
    
            authenticate = salesforce_backend.authenticate()
            if not authenticate:
                _logger.error("Salesforce authentication failed.")
                return
            headers = {
                'Authorization': f'Bearer {authenticate["access_token"]}',
                'Content-Type': 'application/json'
            }
            if not record.sf_id:
                _logger.error("No Salesforce ID found for the record.")
                return
            url = f"{salesforce_backend.url}/services/data/v{salesforce_backend.api_version}/sobjects/FeedItem/{record.sf_id}"
            response = requests.delete(url, headers=headers)
            if response.status_code == 204:
                _logger.info("Message successfully deleted in Salesforce.")
            else:
                _logger.error(f"Failed to delete message in Salesforce. Status: {response.status_code}, Response: {response.text}")