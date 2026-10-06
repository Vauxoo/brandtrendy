# Seguro para el corte a 19: las integraciones externas que escriben por API (VentiApp, usuario api: ~3/4 de los pedidos
# de marketplace) pueden mandar nombres de campo de Odoo 17. En 19, un solo campo inexistente hace fallar el alta completa
# del registro («Invalid field»). Estos alias NO se almacenan (no tocan el esquema ni los datos migrados) y traducen al
# campo de 19; se retiran sin migración cuando el integrador confirme que ya usa los nombres de 19.
from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # 17 → 19: product_uom → product_uom_id · tax_id → tax_ids · route_id → route_ids
    # product_packaging_id / product_packaging_qty: el modelo de empaques ya no existe en 19 (pasó a unidades de medida);
    # se aceptan y se ignoran para que no tumben el alta.
    product_uom = fields.Many2one("uom.uom", string="UdM (compat. 17)", compute="_compute_compat17",
                                  inverse="_inverse_compat17", search="_search_compat17_uom")
    tax_id = fields.Many2many("account.tax", string="Impuestos (compat. 17)", compute="_compute_compat17",
                              inverse="_inverse_compat17", search="_search_compat17_tax")
    route_id = fields.Many2one("stock.route", string="Ruta (compat. 17)", compute="_compute_compat17",
                               inverse="_inverse_compat17")
    product_packaging_id = fields.Integer(string="Empaque (compat. 17, se ignora)", compute="_compute_compat17",
                                          inverse="_inverse_ignorar")
    product_packaging_qty = fields.Float(string="Cantidad de empaques (compat. 17, se ignora)",
                                         compute="_compute_compat17", inverse="_inverse_ignorar")

    @api.depends("product_uom_id", "tax_ids", "route_ids")
    def _compute_compat17(self):
        for linea in self:
            linea.product_uom = linea.product_uom_id
            linea.tax_id = linea.tax_ids
            linea.route_id = linea.route_ids[:1]
            linea.product_packaging_id = 0
            linea.product_packaging_qty = 0.0

    def _inverse_compat17(self):
        for linea in self:
            if linea.product_uom and linea.product_uom != linea.product_uom_id:
                linea.product_uom_id = linea.product_uom
            if linea.tax_id != linea.tax_ids:
                linea.tax_ids = linea.tax_id
            if linea.route_id and linea.route_id not in linea.route_ids:
                linea.route_ids = linea.route_id

    def _inverse_ignorar(self):
        return

    def _search_compat17_uom(self, operator, value):
        return [("product_uom_id", operator, value)]

    def _search_compat17_tax(self, operator, value):
        return [("tax_ids", operator, value)]


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # 17: detailed_type == 'product' era el almacenable. 19: type == 'consu' + is_storable.
    detailed_type = fields.Selection([("consu", "Consumible"), ("service", "Servicio"), ("product", "Almacenable"),
                                      ("combo", "Combo")], string="Tipo (compat. 17)",
                                     compute="_compute_detailed_type_compat17", search="_search_detailed_type_compat17")

    @api.depends("type", "is_storable")
    def _compute_detailed_type_compat17(self):
        for producto in self:
            producto.detailed_type = "product" if (producto.type == "consu" and producto.is_storable) else producto.type

    def _search_detailed_type_compat17(self, operator, value):
        valores = value if isinstance(value, (list, tuple)) else [value]
        positivo = operator in ("=", "in")
        if operator not in ("=", "!=", "in", "not in"):
            return [("type", operator, value)]
        partes = []
        for v in valores:
            if v == "product":
                partes.append([("type", "=", "consu"), ("is_storable", "=", True)])
            elif v == "consu":
                partes.append([("type", "=", "consu"), ("is_storable", "=", False)])
            else:
                partes.append([("type", "=", v)])
        dominio = []
        for i, parte in enumerate(partes):
            if i:
                dominio = ["|"] + dominio
            dominio += ["&"] * (len(parte) - 1) + parte
        return dominio if positivo else ["!"] + dominio


class ResPartner(models.Model):
    _inherit = "res.partner"

    # 17: mobile. 19: solo phone. Medido en producción: los contactos que crea la integración traen phone, no mobile;
    # el alias evita que un mobile vacío en el payload tumbe el alta. Escribir mobile llena phone si está vacío.
    mobile = fields.Char(string="Móvil (compat. 17)", compute="_compute_mobile_compat17",
                         inverse="_inverse_mobile_compat17", search="_search_mobile_compat17")

    @api.depends("phone")
    def _compute_mobile_compat17(self):
        for contacto in self:
            contacto.mobile = contacto.phone

    def _inverse_mobile_compat17(self):
        for contacto in self:
            if contacto.mobile and not contacto.phone:
                contacto.phone = contacto.mobile

    def _search_mobile_compat17(self, operator, value):
        return [("phone", operator, value)]
