import base64
import hashlib
import json
import logging
import re

from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.tools.misc import file_open

_logger = logging.getLogger(__name__)

MODULO = "brandtrendy_promo_theme"
SITIO = "Promocionales Brandtrendy"  # el sitio se resuelve por nombre; nunca por id
PARAM_RESULTADO = MODULO + ".ultimo_aplicar"
# Versión de la lógica de «aplicar». Los pasos de configuración se re-aplican cuando cambia este número (o en una base
# recién restaurada); entre versiones, un cambio deliberado de un administrador se respeta. Subirla al cambiar PASOS,
# VISTAS_APAGAR o los ajustes.
APLICAR_VERSION = "3"
PARAM_PASO = MODULO + ".aplicado."  # + nombre del paso → versión aplicada
PARAM_CODIGO_RESPALDO = MODULO + ".codigo_respaldo"
GSC_BLOQUE = re.compile(r"<!-- BT-GSC -->.*?<!-- /BT-GSC -->", re.S)  # verificación de Search Console: se conserva

# --- Tema del sitio: archivos del módulo cargados SOLO en este sitio (como hace Odoo con un theme_*) -----------
ASSETS_SITIO = [  # (key, bundle, directiva, ruta)
    (MODULO + ".primary_variables", "web._assets_primary_variables", "append",
     MODULO + "/static/src/scss/primary_variables.scss"),
    (MODULO + ".fuentes", "web.assets_frontend", "append", MODULO + "/static/src/scss/fuentes.scss"),
    (MODULO + ".tema", "web.assets_frontend", "append", MODULO + "/static/src/scss/tema.scss"),
    (MODULO + ".bootstrap", "web._assets_frontend_helpers", "prepend",
     MODULO + "/static/src/scss/bootstrap_overridden.scss"),
]
ICONOS_KEY = MODULO + ".sitio_iconos"
ICONOS_ARCH = """<data>
    <xpath expr="//link[@rel='apple-touch-icon']" position="attributes">
        <attribute name="t-att-href">'/%(m)s/static/img/apple-touch-icon-180.png?v=1'</attribute>
        <attribute name="sizes">180x180</attribute>
    </xpath>
    <xpath expr="//link[@rel='apple-touch-icon']" position="after">
        <link rel="icon" type="image/png" sizes="192x192" href="/%(m)s/static/img/android-chrome-192.png?v=1"/>
    </xpath>
</data>""" % {"m": MODULO}
FAVICON = MODULO + "/static/img/favicon-512.png"
PARAM_FAVICON = MODULO + ".favicon_sha1"

# --- Vistas del sitio que se apagan (key + sitio). Ver REPORTE_F1 §1 y el Anexo A del BPR ---------------------
VISTAS_APAGAR = [
    # rotas en 19 (capa 1)
    "brandtrendy_s3.bt_shop_products_only", "brandtrendy_s3.bt_lupa_products_only",
    "website_sale.header_cart_link", "brandtrendy_f4.bt_share_only_approved",
    # copias enteras de plantillas de la 17 (capa 2)
    "website_sale.address", "website_sale.payment", "website_sale.payment_delivery",
    "website_sale.confirmation", "website_appointment_sale.website_sale_confirmation_appointment",
    "website_sale.checkout_layout", "l10n_mx_edi_website_sale.l10n_mx_edi_invoicing_info", "website_sale.cart",
    "payment.form", "website_sale.checkout", "website_sale.address_list",
    "website_sale.payment_confirmation_status", "website_sale.filter_products_price",
    # extensiones propias cuyas anclas no existen en 19 (capa 3)
    "brandtrendy_f4.bt_card_polish", "website_sale.products_attributes", "brandtrendy_f4.bt_checkout_steps_cotizacion",
    "brandtrendy_f4.bt_cart_compact", "brandtrendy_f4.bt_total_iva", "brandtrendy_f4.bt_nav_quote_mode",
    "brandtrendy_f4.bt_product_quote_mode", "brandtrendy_f4.bt_pdp_polish", "brandtrendy_f4.bt_pdp_reorder",
    "brandtrendy_f4.bt_pdp_muestra",
    # sustituidas por el estándar o por este módulo
    "brandtrendy_f4.bt_qty_default_moq",  # → herencia del módulo (N4)
    "brandtrendy_f4.bt_mobile_search", "brandtrendy_f4.bt_search_count",
    "brandtrendy_i5.seo_head", "brandtrendy_i5.seo_producto", "brandtrendy_i5.seo_listado",
    "brandtrendy_i5.perf_lcp_ficha", "brandtrendy_m2.noindex_modulos", "brandtrendy_k3.jobs_sidebar_off",
    "website.cookies_bar",  # N3: barra de consentimiento apagada; aviso en el pie
    # copyright de la 17 con estilos en línea: borra el t-call web.brand_promotion que la vista primaria
    # planning.frontend_layout necesita y rompe la validación del pie; los enlaces legales van en el pie del módulo
    "brandtrendy_f4.bt_footer_copyright",
]

# --- Analítica (D11): GA4 por el campo nativo de Odoo (públicos en el código de la página; no son secretos).
GA4_PRODUCCION = "G-WNH0PQXKT1"  # propiedad «Promocionales Brandtrendy» (28_PLAN_ANALYTICS)
GA4_PRUEBAS = "G-HLGCJNRK8C"  # propiedad «Promocionales - PRUEBAS»: bases neutralizadas (staging de Odoo.sh)

# --- Pasos del checkout del sitio (D1), por step_href: (nombre, botón principal, botón de regreso) ------------
PASOS = {
    "/shop/cart": ("Revisar solicitud", False, "Regresar a mi solicitud"),
    "/shop/checkout": ("Datos de contacto", "Continuar", "Regresar a mis datos"),
    "/shop/extra_info": ("Información adicional", "Continuar", "Regresar a información adicional"),
    "/shop/payment": ("Confirmar solicitud", "Revisar y confirmar", False),
}
PASO_CFDI = "/shop/l10n_mx_invoicing_info"  # N1: fuera del flujo del sitio en modo cotización

# --- Cabecera del sitio: plantilla «Sale 2» de Odoo 19 (franja superior + logotipo, buscador y «Mi cotización» + menú)
CABECERA_ENCENDER = ["website.template_header_sales_two", "website.header_text_element"]
CABECERA_APAGAR = [
    "website.template_header_default", "website.template_header_search",  # otras plantillas de cabecera
    "portal.user_sign_in",  # sin cuentas de cliente en el sitio (account_on_checkout = disabled)
    "website.header_call_to_action",  # la acción principal es la cotización, no un botón aparte
]
CABECERA_TEXTO = """<data inherit_id="website.placeholder_header_text_element" name="Header Text element" active="True">
    <xpath expr="." position="inside">
        <li t-attf-class="#{_item_class}">
            <div t-attf-class="s_text_block #{_div_class}" data-name="Text">
                <small>Envíos a todo México · Facturación CFDI · Atención a empresas L–V 8:30–17:30 ·
                    <a href="https://wa.me/525555260418" class="text-reset">WhatsApp +52 55 5526 0418</a></small>
            </div>
        </li>
    </xpath>
</data>"""

# --- Automatizaciones de la base que este módulo sustituye (se archivan por nombre; no se borran) -------------
AUTOMATIZACIONES_RETIRAR = [
    "PROMOCIONALES · Avisar al equipo cuando entra una cotización del sitio",  # → aviso interno del módulo
    "BT acuse carrito web",  # dependía del JavaScript de la 17 y leía la descripción del lead
    "BT carrito web: valor real tras triage",  # leía «Total estimado $» de la descripción
]


class Website(models.Model):
    _inherit = "website"

    bt_quote_mode = fields.Boolean(
        string="Modo cotización (Brandtrendy)",
        help="El sitio opera por solicitud de cotización: sin paso de facturación en el checkout, lead ligado a la "
        "solicitud en servidor y acuse con la voz de la casa.",
    )

    # ------------------------------------------------------------------ N1
    def _get_allowed_steps_domain(self):
        dominio = super()._get_allowed_steps_domain()
        if self.bt_quote_mode:
            dominio = list(dominio) + [("step_href", "!=", PASO_CFDI)]  # lista, igual que el método original
        return dominio

    # ------------------------------------------------------------------ aplicar (cada -i y -u)
    @api.model
    def _bt_promo_sitio(self):
        sitio = self.sudo().with_context(active_test=False).search([("name", "=", SITIO)])
        if len(sitio) != 1:
            _logger.warning("%s: se esperaba 1 sitio «%s» y hay %s; no se aplica nada", MODULO, SITIO, len(sitio))
            return self.browse()
        return sitio

    @api.model
    def _bt_promo_aplicar(self):
        """Deja el sitio como lo define el módulo. Idempotente; cada paso aislado: si uno falla, los demás siguen y el
        resultado queda en el parámetro ``brandtrendy_promo_theme.ultimo_aplicar``."""
        sitio = self._bt_promo_sitio()
        resultado = {"sitio": sitio.id or False, "pasos": {}}
        if sitio:
            ICP = self.env["ir.config_parameter"].sudo()
            # (nombre, método, regla): «siempre» = idempotente; «version» = cuando cambia APLICAR_VERSION;
            # «una_vez» = solo la primera vez en esta base (no deshace decisiones posteriores de un administrador).
            for nombre, metodo, regla in [
                ("modo", sitio._bt_promo_modo, "version"),
                ("tema", sitio._bt_promo_tema, "siempre"),
                ("vistas", sitio._bt_promo_vistas, "version"),
                ("codigo", sitio._bt_promo_codigo, "una_vez"),
                ("ajustes", sitio._bt_promo_ajustes, "version"),
                ("pasos", sitio._bt_promo_pasos, "version"),
                ("cabecera", sitio._bt_promo_cabecera, "version"),
                ("textos", sitio._bt_promo_textos, "siempre"),
                ("automatizaciones", sitio._bt_promo_automatizaciones, "una_vez"),
                ("paginas", sitio._bt_promo_paginas, "siempre"),  # protege con huella lo editado a mano
                ("pie", sitio._bt_promo_pie, "siempre"),
                ("rutas", sitio._bt_promo_rutas, "version"),
                ("menu", sitio._bt_promo_menu, "version"),
            ]:
                marca = ICP.get_param(PARAM_PASO + nombre)
                if (regla == "version" and marca == APLICAR_VERSION) or (regla == "una_vez" and marca):
                    resultado["pasos"][nombre] = "ya aplicado (%s)" % marca
                    continue
                try:
                    with self.env.cr.savepoint():
                        texto = metodo() or "ok"
                        resultado["pasos"][nombre] = texto
                        # «PENDIENTE…» = faltan datos (p. ej. categorías de otro lote): no se marca y se reintenta.
                        if regla != "siempre" and not str(texto).startswith("PENDIENTE"):
                            ICP.set_param(PARAM_PASO + nombre, APLICAR_VERSION)
                except Exception as error:  # noqa: BLE001 — se registra y se sigue con los demás pasos
                    _logger.exception("%s: falló el paso «%s»", MODULO, nombre)
                    resultado["pasos"][nombre] = "ERROR: %s" % error
        resultado["fecha"] = fields.Datetime.to_string(fields.Datetime.now())
        self.env["ir.config_parameter"].sudo().set_param(PARAM_RESULTADO, json.dumps(resultado, ensure_ascii=False))
        _logger.info("%s: aplicado %s", MODULO, resultado)
        return True

    def bt_promo_reaplicar(self):
        """Vuelve a aplicar la configuración del sitio sin esperar una actualización del módulo (solo administradores).
        Fuerza los pasos por versión; los de «una sola vez» y las páginas editadas a mano se siguen respetando."""
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(self.env._("Solo un administrador puede reaplicar la configuración del sitio."))
        ICP = self.env["ir.config_parameter"].sudo()
        for paso in ("modo", "vistas", "ajustes", "pasos", "cabecera", "rutas", "menu"):
            ICP.set_param(PARAM_PASO + paso, False)
        self._bt_promo_aplicar()
        return json.loads(ICP.get_param(PARAM_RESULTADO) or "{}")

    def _bt_promo_modo(self):
        self.ensure_one()
        if not self.bt_quote_mode:
            self.bt_quote_mode = True
        return "modo cotización encendido"

    # ------------------------------------------------------------------ tema
    def _bt_promo_tema(self):
        self.ensure_one()
        IrAsset = self.env["ir.asset"].sudo().with_context(active_test=False, website_id=False)
        for key, bundle, directiva, ruta in ASSETS_SITIO:
            vals = {"name": key, "key": key, "bundle": bundle, "directive": directiva, "path": ruta,
                    "target": False, "active": True, "sequence": 16, "website_id": self.id}
            asset = IrAsset.search([("key", "=", key), ("website_id", "=", self.id)])
            if not asset:
                IrAsset.create(vals)
            elif any(asset[c] != v for c, v in vals.items() if c != "website_id"):
                asset.write(vals)
        View = self.env["ir.ui.view"].sudo().with_context(active_test=False, website_id=False)
        vista = View.search([("key", "=", ICONOS_KEY), ("website_id", "=", self.id)])
        vals = {"name": "Promocionales · iconos táctiles", "key": ICONOS_KEY, "type": "qweb", "mode": "extension",
                "inherit_id": self.env.ref("website.layout").id, "website_id": self.id, "arch_db": ICONOS_ARCH,
                "active": True, "priority": 60}
        if not vista:
            View.create(vals)
        elif vista.arch_db != ICONOS_ARCH or not vista.active:
            vista.write({"arch_db": ICONOS_ARCH, "active": True})
        with file_open(FAVICON, "rb") as archivo:
            crudo = archivo.read()
        huella = hashlib.sha1(crudo).hexdigest()
        ICP = self.env["ir.config_parameter"].sudo()
        if ICP.get_param(PARAM_FAVICON) != huella:
            self.with_context(website_id=False).write({"favicon": base64.b64encode(crudo)})
            ICP.set_param(PARAM_FAVICON, huella)
        return "assets %s, iconos y favicon" % len(ASSETS_SITIO)

    # ------------------------------------------------------------------ vistas y código inyectado
    def _bt_promo_vistas(self):
        self.ensure_one()
        # Sin website_id en el contexto: se escriben las vistas ya específicas del sitio, sin crear copias.
        vistas = self.env["ir.ui.view"].sudo().with_context(active_test=False, website_id=False).search(
            [("key", "in", VISTAS_APAGAR), ("website_id", "=", self.id), ("active", "=", True)])
        if vistas:
            vistas.write({"active": False})
        return "%s vistas apagadas" % len(vistas)

    def _bt_promo_codigo(self):
        """Una sola vez: respalda el código inyectado de la 17 en un parámetro, conserva únicamente el bloque de
        verificación de Google Search Console y vacía lo demás (el JavaScript y los estilos de la 17)."""
        self.ensure_one()
        cabeza, pie = self.custom_code_head or "", self.custom_code_footer or ""
        if not cabeza and not pie:
            return "sin código inyectado"
        self.env["ir.config_parameter"].sudo().set_param(
            PARAM_CODIGO_RESPALDO, json.dumps({"head": cabeza, "footer": pie}, ensure_ascii=False))
        gsc = GSC_BLOQUE.search(cabeza)
        self.write({"custom_code_head": gsc.group(0) if gsc else False, "custom_code_footer": False})
        return "código inyectado respaldado y vaciado%s" % (" (se conservó la verificación de GSC)" if gsc else "")

    # ------------------------------------------------------------------ ajustes del sitio
    def _bt_promo_ajustes(self):
        self.ensure_one()
        vals = {
            "cookies_bar": False,  # N3: consentimiento tácito con aviso (LFPDPPP), como opera hoy producción
            "add_to_cart_action": "go_to_cart",  # D2: del primer «Agregar» a revisar la solicitud
            "account_on_checkout": "disabled",  # solicitud como invitado; sin cuentas de cliente en el flujo
            "prevent_zero_price_sale": True,  # artículos sin precio: «Contáctanos» con el producto en el asunto
            "contact_us_button_url": "/contactus",
            # Redes públicas de la marca (13_DATOS_EMPRESA); X/Twitter no se publica.
            "social_facebook": "https://www.facebook.com/Brandtrendy",
            "social_instagram": "https://www.instagram.com/brandtrendy_mexico",
            "social_tiktok": "https://www.tiktok.com/@brandtrendy_mexico",
            "social_youtube": "https://www.youtube.com/@brandtrendy-xf9ij",
            "social_linkedin": "https://www.linkedin.com/company/brandtrendy",
            "social_twitter": False,
        }
        # En una base neutralizada (copia de prueba) se mide en la propiedad de pruebas, para no ensuciar la real.
        neutralizada = self.env["ir.config_parameter"].sudo().get_param("database.is_neutralized")
        vals["google_analytics_key"] = GA4_PRUEBAS if neutralizada else GA4_PRODUCCION
        if self.salesteam_id:
            vals["crm_default_team_id"] = self.salesteam_id.id  # el formulario de contacto cae en el equipo del sitio
        if self.salesperson_id:
            vals["crm_default_user_id"] = self.salesperson_id.id
        cambios = {c: v for c, v in vals.items() if (self[c].id if hasattr(self[c], "id") else self[c]) != v}
        if cambios:
            self.write(cambios)
        return "ajustes: %s" % (", ".join(sorted(cambios)) or "sin cambios")

    # ------------------------------------------------------------------ pasos del checkout (D1, H3)
    def _bt_promo_pasos(self):
        self.ensure_one()
        sitio_ctx = self.with_context(website_id=self.id)
        extra = sitio_ctx.viewref("website_sale.extra_info")
        if not extra.active:
            # Con website_id en el contexto: crea la copia del sitio (las extensiones del módulo la siguen).
            extra.with_context(website_id=self.id).write({"active": True})
        hechos = []
        for href, (nombre, principal, regreso) in PASOS.items():
            paso = self._get_checkout_step(href)
            if not paso:
                continue
            vals = {"is_published": True}
            paso.with_context(lang="es_MX").write(dict(vals, name=nombre, main_button_label=principal,
                                                       back_button_label=regreso))
            hechos.append(href)
        return "pasos: %s" % ", ".join(hechos)

    # ------------------------------------------------------------------ cabecera
    def _bt_promo_vista_del_sitio(self, key, activa):
        """Deja la vista ``key`` en el estado pedido SOLO para este sitio (copia del sitio vía COW si no existe)."""
        View = self.env["ir.ui.view"].sudo().with_context(active_test=False)
        propia = View.search([("key", "=", key), ("website_id", "=", self.id)], limit=1)
        if propia:
            if propia.active != activa:
                propia.with_context(website_id=False).write({"active": activa})
            return propia
        generica = View.search([("key", "=", key), ("website_id", "=", False)], limit=1)
        if not generica:
            return View
        generica.with_context(website_id=self.id).write({"active": activa})  # el COW crea la copia del sitio
        return View.search([("key", "=", key), ("website_id", "=", self.id)], limit=1)

    def _bt_promo_cabecera(self):
        self.ensure_one()
        for key in CABECERA_APAGAR:
            self._bt_promo_vista_del_sitio(key, False)
        for key in CABECERA_ENCENDER:
            self._bt_promo_vista_del_sitio(key, True)
        texto = self._bt_promo_vista_del_sitio("website.header_text_element", True)
        if texto:
            for lang in ("en_US", "es_MX"):
                texto.with_context(lang=lang, website_id=False).write({"arch_db": CABECERA_TEXTO})
        return "cabecera «Sale 2» con franja de texto; sin botón de acción ni inicio de sesión"

    # ------------------------------------------------------------------ automatizaciones sustituidas
    def _bt_promo_automatizaciones(self):
        reglas = self.env["base.automation"].sudo().with_context(active_test=False).search(
            [("name", "in", AUTOMATIZACIONES_RETIRAR), ("active", "=", True)])
        if reglas:
            reglas.write({"active": False})
        return "%s automatizaciones archivadas" % len(reglas)
