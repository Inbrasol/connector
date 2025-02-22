from odoo import models, fields, api

class SalesforceRestFields(models.Model):
    _name = 'salesforce.rest.fields'
    _description = 'Salesforce REST Fields'
    
    salesforce_rest_config_id = fields.Many2one('salesforce.rest.config', 'Salesforce REST Configuration', required=True, default=lambda self: self.env.context.get('active_id'))
    odoo_model_id = fields.Many2one('ir.model', 'Odoo Model', related='salesforce_rest_config_id.odoo_model_id', readonly=True)
    odoo_field_id = fields.Many2one('ir.model.fields', 'Odoo Field', required=True, ondelete='cascade' , domain="[('model_id', '=', odoo_model_id)]")
    odoo_field_relation_model = fields.Char('Relation Model', related='odoo_field_id.relation', readonly=True)
    odoo_related_field_id = fields.Many2one('ir.model.fields', 'Odoo Related Field', ondelete='cascade', domain="[('model', '=', odoo_field_relation_model)]")
    salesforce_field = fields.Char('Salesforce Field', required=True)
    type = fields.Selection([('string', 'String'), ('integer', 'Integer'), ('float', 'Float'), ('boolean', 'Boolean'), ('date', 'Date'), ('datetime', 'Datetime'), ('related', 'Related')], 'Type', required=True)
    default_value = fields.Char('Default Value')
    active = fields.Boolean('Active', default=True)
    is_record_type = fields.Boolean('Is Record Type', default=False)
    is_always_update = fields.Boolean('Is Always Update', default=False)
    remove_to_composite = fields.Boolean('Remove to Tree', default=False)