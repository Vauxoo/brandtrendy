from odoo import fields, models


class ProductPackaging(models.Model):
    _inherit = "product.packaging"

    length_uom_id = fields.Many2one(
        default=lambda self: self.env.ref("uom.product_uom_cm"),
    )
