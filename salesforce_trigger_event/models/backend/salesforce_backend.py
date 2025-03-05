from odoo import models, fields, _
import requests
from requests.auth import HTTPBasicAuth

from odoo.exceptions import UserError

class SalesforceBackend(models.Model):
    _name = 'salesforce.backend'
    _description = 'Salesforce Backend'

    name = fields.Char('Name', required=True)
    client_id = fields.Char('Client ID', required=True)
    client_secret = fields.Char('Client Secret', required=True)
    username = fields.Char('Username', required=True)
    password = fields.Char('Password', required=True)
    security_token = fields.Char('Security Token', required=True)
    refresh_token = fields.Char('Refresh Token', required=True)
    sandbox = fields.Boolean('Sandbox', default=False)
    api_version = fields.Char('API Version', default='v60.0')
    url = fields.Char('URL', required=True, default='https://login.salesforce.com')
    active = fields.Boolean('Active', default=True)

    def authenticate(self):
        url = 'https://login.salesforce.com/services/oauth2/token'
        if self.sandbox:
            url = 'https://test.salesforce.com/services/oauth2/token'
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }

        payload = {
            'grant_type': 'password',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'username': self.username,
            'password': f"{self.password}{self.security_token}"
        }

        response = requests.post(url, data=payload, headers=headers)
        if response.status_code == 200:
            tokens = response.json()
            self.write({'refresh_token': tokens.get('refresh_token')})
            return tokens
        else:
            if 'INVALID_SESSION_ID' in response.text:
                tokens = self.refresh_token()
                if tokens:
                    return tokens
            raise UserError (_(f"Failed to authenticate with Salesforce: {response.text}"))

    def refresh_token(self):
        url = 'https://login.salesforce.com/services/oauth2/token'
        if self.sandbox:
            url = 'https://test.salesforce.com/services/oauth2/token'
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }

        payload = {
            'grant_type': 'refresh_token',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': self.refresh_token
        }

        response = requests.post(url, data=payload, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            raise UserError (_(f"Failed to refresh token with Salesforce: {response.text}"))