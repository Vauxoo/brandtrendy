from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Ya existe como campo manual con datos (lo mantiene el sync del catálogo): al declararlo aquí pasa a ser del
    # módulo sin perderlos. Es la fuente del mínimo (decisión D5); el atributo «Cantidad mínima» se deriva de él.
    x_bt_moq = fields.Integer(string="Cantidad mínima pública (MOQ BT)")
