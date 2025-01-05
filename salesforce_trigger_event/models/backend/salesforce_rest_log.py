from odoo import models, fields, api

class SalesforceRestLog(models.Model):
    _name = 'salesforce.rest.log'
    _description = 'Salesforce REST Log'

    name = fields.Char(string='Name', required=True)
    date = fields.Datetime(string='Log Date', default=fields.Datetime.now, required=True)
    request_url = fields.Char(string='Request URL', required=True)
    request_method = fields.Selection([
        ('GET', 'GET'),
        ('POST', 'POST'),
        ('PUT', 'PUT'),
        ('DELETE', 'DELETE')
    ], string='Request Method', required=True)
    request_headers = fields.Text(string='Request Headers')
    request_body = fields.Text(string='Request Body')
    response_status = fields.Integer(string='Response Status')
    response_headers = fields.Text(string='Response Headers')
    response_body = fields.Text(string='Response Body')
    error_message = fields.Text(string='Error Message')

    @api.model
    def create_log(self, name, request_url, request_method, request_headers, request_body, response_status, response_headers, response_body, error_message=None):
        self.create({
            'name': name,
            'request_url': request_url,
            'request_method': request_method,
            'request_headers': request_headers,
            'request_body': request_body,
            'response_status': response_status,
            'response_headers': response_headers,
            'response_body': response_body,
            'error_message': error_message,
        })