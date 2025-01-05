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
        print("Authenticate")
        print(response.status_code)
        print(response.text)
        if response.status_code == 200:
            token_data = response.json()
            return token_data
        else:
            raise UserError (_(f"Failed to authenticate with Salesforce: {response.text}"))