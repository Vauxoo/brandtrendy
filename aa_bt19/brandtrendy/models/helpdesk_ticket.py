from odoo import api, fields, models


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    order_id = fields.Many2one("sale.order")

    @api.onchange("order_id")
    def _onchange_order_id(self):
        self.partner_id = self.order_id.partner_id
