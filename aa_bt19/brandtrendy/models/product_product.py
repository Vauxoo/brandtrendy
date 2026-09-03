from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    dimensional_uom_id = fields.Many2one(
        "uom.uom",
        default=lambda self: self.env.ref("uom.product_uom_cm"),
    )
