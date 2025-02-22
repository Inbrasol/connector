from odoo import models, fields, api

class SalesforceRecordType(models.Model):
    _name = 'salesforce.record.type'
    _description = 'Salesforce Record Type'

    salesforce_rest_config_id = fields.Many2one('salesforce.rest.config', 'Salesforce REST Configuration', required=True, default=lambda self: self.env.context.get('active_id'))
    odoo_model_id = fields.Many2one('ir.model', 'Odoo Model', related='salesforce_rest_config_id.odoo_model_id', readonly=True)
    odoo_field_id = fields.Many2one('ir.model.fields', 'Odoo Field', required=True, ondelete='cascade' , domain="[('model_id', '=', odoo_model_id)]")
    type = fields.Selection([('string', 'String'), ('related', 'Related')], 'Type', required=True)
    odoo_field_relation_model = fields.Char('Relation Model', related='odoo_field_id.relation', readonly=True)
    odoo_related_field_id = fields.Many2one('ir.model.fields', 'Odoo Related Field', ondelete='cascade', domain="[('model', '=', odoo_field_relation_model)]")
    odoo_field_value = fields.Char('Odoo Field Value', required=True)
    record_type_id = fields.Char('Record Type ID', required=True)
    active = fields.Boolean('Active', default=True)