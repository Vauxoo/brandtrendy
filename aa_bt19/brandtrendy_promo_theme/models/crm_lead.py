from odoo import api, fields, models

# Triage de la solicitud (misma tabla que la acción de servidor «BT triage lead» de la base, 52_ §4).
DOMINIOS_PERSONALES = ("gmail.", "hotmail.", "outlook.", "yahoo.", "icloud.", "live.", "proton", "aol.", "msn.")
EMPRESAS_VACIAS = {
    "", "particular", "particulares", "personal", "na", "no", "x", "ninguna", "ninguno", "noaplica",
    "notengo", "nohay", "sinempresa", "personafisica", "fisica", "none", "yo", "casa", "micasa", "sn",
    "nn", "aunno", "independiente", "freelance", "freelancer",
}
BANDA_POR_CANTIDAD = {  # cantidad estimada → (banda, valor de referencia en MXN)
    "500_mas": ("a", 120000.0),
    "100_500": ("b", 48000.0),
    "25_100": ("b", 10000.0),
}


class CrmLead(models.Model):
    _inherit = "crm.lead"

    # Campos que ya existen en la base como campos manuales; al declararlos aquí pasan a ser del módulo y conservan
    # sus datos (mismo nombre, mismo tipo, mismos valores de selección).
    x_bt_banda = fields.Selection(
        [("a", "A - grande"), ("b", "B - estándar"), ("c", "C - pedido piloto")],
        string="Banda de triage (BT)",
    )
    x_bt_cantidad = fields.Selection(
        [("lt25", "Menos de 25"), ("25_100", "25 a 100"), ("100_500", "100 a 500"), ("500_mas", "Más de 500")],
        string="Cantidad estimada (BT)",
    )
    x_bt_fecha_entrega = fields.Date(string="Fecha de entrega deseada (BT)")
    x_bt_valor_estimado = fields.Float(string="Valor estimado MXN (BT)")
    x_bt_wa_optin = fields.Boolean(string="Acepta WhatsApp (BT)")
    x_bt_gclid = fields.Char(
        string="Click ID de Google (BT)",
        help="Folio del clic de anuncio (gclid, gbraid o wbraid). Lo llena el servidor desde las visitas del "
        "visitante; sirve para subir la conversión a Google Ads.",
    )
    x_bt_click_tipo = fields.Char(
        string="Tipo de click ID (BT)",
        help="gclid | gbraid | wbraid. Google los espera en columnas distintas al importar conversiones.",
    )

    @api.model
    def _bt_promo_cantidad_desde_piezas(self, piezas):
        """Convierte la cantidad objetivo en piezas al rango de la selección ``x_bt_cantidad``."""
        if not piezas or piezas <= 0:
            return False
        if piezas < 25:
            return "lt25"
        if piezas < 100:
            return "25_100"
        if piezas < 500:
            return "100_500"
        return "500_mas"

    def _bt_promo_banda(self):
        """Banda y valor de referencia del lead según la tabla de triage. No escribe nada."""
        self.ensure_one()
        correo = (self.email_from or "").lower()
        corporativo = False
        if "@" in correo:
            dominio = correo.split("@", 1)[1]
            corporativo = not dominio.startswith(DOMINIOS_PERSONALES)
        empresa = (self.partner_name or "").strip().lower()
        for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"),
                     (".", ""), ("/", ""), ("-", ""), (" ", "")):
            empresa = empresa.replace(a, b)
        empresa_real = empresa not in EMPRESAS_VACIAS
        cantidad = self.x_bt_cantidad or ""
        if cantidad in BANDA_POR_CANTIDAD:
            return BANDA_POR_CANTIDAD[cantidad]
        if cantidad == "lt25":
            return ("b" if (corporativo or empresa_real) else "c", 2000.0)
        return ("b", 0.0)
