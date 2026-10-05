import logging
import re
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from odoo import fields, models
from odoo.http import request

_logger = logging.getLogger(__name__)

PARAM_ACUSE_WHATSAPP = "brandtrendy_promo_theme.acuse_whatsapp"  # «1» lo enciende; manda mensajes a clientes
PLANTILLA_WHATSAPP = "acuse_cotizacion_bt"
CLICK_IDS = ("gclid", "gbraid", "wbraid")


def _ultimos_10(telefono):
    digitos = re.sub(r"\D", "", telefono or "")
    return digitos[-10:] if len(digitos) >= 10 else ""


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # Paso «Información adicional» del checkout del sitio (lista blanca en data/lista_blanca.xml).
    x_bt_cantidad_objetivo = fields.Integer(string="Cantidad objetivo (piezas)", copy=False)
    x_bt_fecha_entrega_deseada = fields.Date(string="Fecha de entrega deseada", copy=False)
    x_bt_optin_whatsapp_orden = fields.Boolean(string="Preferencia de contacto por WhatsApp", copy=False)
    bt_promo_solicitud_enviada = fields.Boolean(
        string="Solicitud del sitio procesada", copy=False, readonly=True,
        help="Técnico: la solicitud confirmada ya actualizó su lead y avisó al equipo.",
    )

    # ------------------------------------------------------------------ correo al cliente
    def _send_payment_succeeded_for_order_mail(self):
        """En el sitio en modo cotización, el cliente recibe UN acuse con la voz de la casa en lugar del correo
        estándar de «pago»; el resto de los sitios sigue igual."""
        plantilla = self.env.ref("brandtrendy_promo_theme.mail_template_acuse_solicitud", raise_if_not_found=False)
        cotizaciones = self.filtered(lambda o: o.website_id.bt_quote_mode) if plantilla else self.browse()
        if cotizaciones:
            cotizaciones.with_context(force_user_recomputation=True)._compute_user_id()
            for order in cotizaciones:
                order._send_order_notification_mail(plantilla)
        resto = self - cotizaciones
        if resto:
            return super(SaleOrder, resto)._send_payment_succeeded_for_order_mail()
        return None

    # ------------------------------------------------------------------ solicitud → lead (decisión D2)
    def _bt_promo_sync_lead(self):
        """Llamado por la automatización «Solicitud del sitio → lead». Nunca lanza excepción hacia el checkout:
        si un paso falla deja nota y actividad para revisarlo a mano."""
        for order in self:
            if not order.website_id.bt_quote_mode:
                continue
            try:
                with self.env.cr.savepoint():
                    order._bt_promo_sync_lead_una()
            except Exception:
                _logger.exception("brandtrendy_promo_theme: falló la liga solicitud→lead de %s", order.name)
                order._bt_promo_dejar_rastro("ligar la solicitud con su lead")

    def _bt_promo_sync_lead_una(self):
        self.ensure_one()
        sitio = self.website_id
        if not self.partner_id or self.partner_id == sitio.user_id.partner_id:
            return  # carrito anónimo: todavía no hay contacto
        if self.state == "draft" and not self.order_line:
            return  # carrito recién creado por alguien con sesión: aún no es una solicitud
        if self.partner_id.user_ids.filtered(lambda u: not u.share):
            return  # personal interno navegando con su sesión: no es un cliente
        lead = self.opportunity_id
        if not lead:
            lead = self._bt_promo_lead_reutilizable() or self._bt_promo_crear_lead()
            self.opportunity_id = lead
        confirmada = self.state in ("sent", "sale") and self.transaction_ids.filtered(
            lambda t: t.state in ("pending", "authorized", "done"))  # la confirmó el cliente en el checkout
        if confirmada and not self.bt_promo_solicitud_enviada:
            self._bt_promo_solicitud_confirmada(lead)
            self.bt_promo_solicitud_enviada = True

    def _bt_promo_lead_reutilizable(self):
        """Un lead abierto del mismo contacto en los últimos 30 días (un registro por hecho; no se archiva nada)."""
        self.ensure_one()
        partner = self.partner_id
        equipo = self.website_id.salesteam_id
        dominio = [
            ("active", "=", True),
            ("probability", "<", 100),
            ("create_date", ">=", fields.Datetime.now() - timedelta(days=30)),
            ("company_id", "in", [False, self.company_id.id]),
        ]
        if equipo:
            dominio.append(("team_id", "=", equipo.id))
        criterios = []
        if partner.email_normalized:
            criterios.append([("email_normalized", "=", partner.email_normalized)])
        tel = _ultimos_10(partner.phone)
        if tel:
            criterios.append([("phone_sanitized", "=like", "%" + tel)])
        if not criterios:
            return self.env["crm.lead"]
        o = ["|"] * (len(criterios) - 1) + [c for crit in criterios for c in crit]
        lead = self.env["crm.lead"].sudo().search(dominio + o, order="create_date desc", limit=1)
        if lead:
            lead.message_post(
                body=self.env._("Otra solicitud del mismo contacto en el sitio: %s.", self.name),
                message_type="comment", subtype_xmlid="mail.mt_note",
            )
        return lead

    def _bt_promo_crear_lead(self):
        self.ensure_one()
        sitio = self.website_id
        partner = self.partner_id
        empresa = partner.commercial_company_name or partner.company_name or ""
        Lead = self.env["crm.lead"].sudo()
        vals = {
            "name": self.env._("Solicitud %(folio)s · %(quien)s", folio=self.name, quien=empresa or partner.name),
            "type": "opportunity",
            "partner_id": partner.id,
            "contact_name": partner.name,
            "email_from": partner.email,
            "phone": partner.phone,
            "partner_name": empresa,
            "team_id": sitio.salesteam_id.id,
            "user_id": sitio.salesperson_id.id,
            "source_id": self.source_id.id,
            "medium_id": self.medium_id.id,
            "campaign_id": self.campaign_id.id,
        }
        vals.update(self._bt_promo_valores_extra_info())
        vals.update(self._bt_promo_click_id())
        # Sin banda a propósito: el triage de la base corre al crear (banda, SLA, aviso de banda A).
        lead = Lead.create(vals)
        if self.amount_untaxed:
            lead.write({"expected_revenue": self.amount_untaxed, "x_bt_valor_estimado": self.amount_untaxed})
        lead.message_post(
            body=self.env._("Solicitud del sitio ligada: %(folio)s, total con IVA %(total)s.",
                            folio=self.name, total=self._bt_promo_total()),
            message_type="comment", subtype_xmlid="mail.mt_note",
        )
        return lead

    def _bt_promo_valores_extra_info(self):
        vals = {}
        cantidad = self.env["crm.lead"]._bt_promo_cantidad_desde_piezas(self.x_bt_cantidad_objetivo)
        if cantidad:
            vals["x_bt_cantidad"] = cantidad
        if self.x_bt_fecha_entrega_deseada:
            vals["x_bt_fecha_entrega"] = self.x_bt_fecha_entrega_deseada
        if self.x_bt_optin_whatsapp_orden:
            vals["x_bt_wa_optin"] = True
        return vals

    def _bt_promo_click_id(self):
        """gclid/gbraid/wbraid de las visitas del visitante de esta petición, si las hay (sin JavaScript)."""
        try:
            if not request or not getattr(request, "env", None):
                return {}
            visitante = request.env["website.visitor"].sudo()._get_visitor_from_request()
            if not visitante:
                return {}
            for track in visitante.website_track_ids.sorted("visit_datetime", reverse=True):
                consulta = parse_qs(urlparse(track.url or "").query)
                for clave in CLICK_IDS:
                    if consulta.get(clave):
                        return {"x_bt_gclid": consulta[clave][0][:200], "x_bt_click_tipo": clave}
        except Exception:
            _logger.info("brandtrendy_promo_theme: sin click id para %s", self.name, exc_info=True)
        return {}

    def _bt_promo_total(self):
        return "%s %s" % (self.currency_id.symbol or "$", "{:,.2f}".format(self.amount_total))

    def _bt_promo_solicitud_confirmada(self, lead):
        """La solicitud quedó enviada: se actualiza el MISMO lead, se agenda la cotización y se avisa al equipo."""
        self.ensure_one()
        sitio = self.website_id
        partner = self.partner_id
        vals = self._bt_promo_valores_extra_info()
        vals["name"] = self.env._("Solicitud %(folio)s confirmada · %(quien)s", folio=self.name,
                                  quien=lead.partner_name or partner.name)
        if self.amount_untaxed:
            vals.update(expected_revenue=self.amount_untaxed, x_bt_valor_estimado=self.amount_untaxed)
        if self.x_bt_fecha_entrega_deseada and not lead.date_deadline:
            vals["date_deadline"] = self.x_bt_fecha_entrega_deseada
        lead.write(vals)
        if vals.get("x_bt_cantidad") or not lead.x_bt_banda:
            banda, _valor = lead._bt_promo_banda()
            lead.x_bt_banda = banda
        responsable = lead.user_id or sitio.salesperson_id
        resumen = self.env._("Cotizar solicitud %(folio)s (total con IVA %(total)s)", folio=self.name,
                             total=self._bt_promo_total())
        if not lead.activity_ids.filtered(lambda a: a.summary == resumen):
            lead.activity_schedule("mail.mail_activity_data_todo", user_id=responsable.id or self.env.uid,
                                   summary=resumen)
        self._bt_promo_aviso_interno()
        self._bt_promo_acuse_whatsapp(lead)

    def _bt_promo_aviso_interno(self):
        """Aviso al líder y a los miembros del equipo del sitio (sustituye la regla 29 y su plantilla)."""
        plantilla = self.env.ref("brandtrendy_promo_theme.mail_template_aviso_interno", raise_if_not_found=False)
        equipo = self.website_id.salesteam_id
        socios = (equipo.user_id | equipo.member_ids).partner_id.filtered("email")
        if not plantilla or not socios:
            return
        try:
            with self.env.cr.savepoint():
                plantilla.send_mail(self.id, email_values={"recipient_ids": [(6, 0, socios.ids)]})
        except Exception:
            _logger.exception("brandtrendy_promo_theme: aviso interno falló en %s", self.name)
            self._bt_promo_dejar_rastro("aviso interno al equipo")

    def _bt_promo_acuse_whatsapp(self, lead):
        """Acuse por WhatsApp solo si está encendido por parámetro (manda mensajes a clientes: requiere el «va»)."""
        ICP = self.env["ir.config_parameter"].sudo()
        if ICP.get_param(PARAM_ACUSE_WHATSAPP, "0") != "1" or not lead.x_bt_wa_optin or lead.x_bt_banda == "c":
            return
        if len(re.sub(r"\D", "", lead.phone or "")) < 8 or "whatsapp.composer" not in self.env:
            return
        plantilla = self.env["whatsapp.template"].sudo().search(
            [("template_name", "=", PLANTILLA_WHATSAPP), ("status", "=", "approved"), ("model", "=", "crm.lead")],
            limit=1)
        if not plantilla:
            return
        try:
            with self.env.cr.savepoint():
                compositor = self.env["whatsapp.composer"].sudo().create(
                    {"res_model": "crm.lead", "res_ids": str(lead.id), "wa_template_id": plantilla.id})
                compositor.action_send_whatsapp_template()
        except Exception:
            _logger.exception("brandtrendy_promo_theme: acuse de WhatsApp falló en %s", self.name)
            self._bt_promo_dejar_rastro("acuse por WhatsApp")

    def _bt_promo_dejar_rastro(self, paso):
        """Nota en la orden (y en su lead) + actividad para la vendedora del sitio. Nunca lanza."""
        try:
            with self.env.cr.savepoint():
                texto = self.env._("Promocionales: falló el paso «%s»; revisar a mano.", paso)
                for registro in (self, self.opportunity_id):
                    if registro:
                        registro.message_post(body=texto, message_type="comment", subtype_xmlid="mail.mt_note")
                usuario = self.website_id.salesperson_id or self.user_id
                if usuario:
                    (self.opportunity_id or self).activity_schedule(
                        "mail.mail_activity_data_todo", user_id=usuario.id, summary=texto)
        except Exception:
            _logger.exception("brandtrendy_promo_theme: no se pudo dejar rastro en %s", self.name)
