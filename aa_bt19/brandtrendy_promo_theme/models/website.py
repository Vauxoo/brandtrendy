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
APLICAR_VERSION = "4"
PARAM_PASO = MODULO + ".aplicado."  # + nombre del paso → versión aplicada
PARAM_CODIGO_RESPALDO = MODULO + ".codigo_respaldo"
GSC_BLOQUE = re.compile(r"<!-- BT-GSC -->.*?<!-- /BT-GSC -->", re.S)  # verificación de Search Console: se conserva
# Atribución propia de la 17 que se conserva en el pie (no depende de las páginas de la 17): BT-UTM guarda la primera y
# la última fuente de la visita (cookies bt_touch_first/bt_touch_last, 30 días) y bt-wa-ref agrega esa referencia a los
# enlaces de WhatsApp, para que un lead de WhatsApp que viene de Google Ads conserve su gclid. Declaradas en la política
# de cookies.
ATRIBUCION_BLOQUES = [
    re.compile(r"<!-- BT-UTM v\d+ -->.*?<!-- /BT-UTM -->", re.S),
    re.compile(r'<script id="bt-wa-ref".*?</script>', re.S),
]

# --- Tema del sitio: archivos del módulo cargados SOLO en este sitio (como hace Odoo con un theme_*) -----------
ASSETS_SITIO = [  # (key, bundle, directiva, ruta)
    (MODULO + ".primary_variables", "web._assets_primary_variables", "append",
     MODULO + "/static/src/scss/primary_variables.scss"),
    (MODULO + ".fuentes", "web.assets_frontend", "append", MODULO + "/static/src/scss/fuentes.scss"),
    (MODULO + ".tema", "web.assets_frontend", "append", MODULO + "/static/src/scss/tema.scss"),
    (MODULO + ".tienda", "web.assets_frontend", "append", MODULO + "/static/src/scss/tienda.scss"),
    (MODULO + ".ficha", "web.assets_frontend", "append", MODULO + "/static/src/scss/ficha.scss"),
    (MODULO + ".bootstrap", "web._assets_frontend_helpers", "prepend",
     MODULO + "/static/src/scss/bootstrap_overridden.scss"),
]
# Al terminar cada actualización de módulos, Odoo 19 copia toda vista genérica nueva bajo TODAS las copias por sitio de
# su vista padre, activas o no, y la valida ahí (website/models/ir_ui_view.py, _create_all_specific_views, llamado desde
# ir.model.data._process_end). Si una copia por sitio no tiene las anclas de 19, la validación falla, la actualización
# aborta (código 255) y Odoo.sh deja el build en rojo aunque el sitio responda (5-oct: copia 5685 de la 17 de
# website_sale.cart sin div#shop_cart). Los pasos «jubilar» y «herencias_sitio» lo evitan (ver sus docstrings).
# PDF de la 17 que vivían como registros sueltos de la base (sin módulo): report_name → reporte del módulo que lo sustituye.
REPORTES_17 = {
    "brandtrendy_f4.bt_report_saleorder_document": MODULO + ".accion_reporte_cotizacion",
    "brandtrendy_f4.bt_carta_membretada": MODULO + ".accion_reporte_carta",
}
VISTAS_REPORTE_17 = [
    "brandtrendy_f4.bt_external_layout",
    "brandtrendy_f4.bt_report_saleorder_document",
    "brandtrendy_f4.bt_carta_membretada",
]
SUFIJO_JUBILADA = ".bt17_jubilada"
PARAM_INSTALADO = MODULO + ".instalado_en"  # primera aplicación del módulo en esta base: separa copias de la 17 de las de 19
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
                ("jubilar", sitio._bt_promo_jubilar, "siempre"),
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
                ("reportes", sitio._bt_promo_reportes, "siempre"),
                # al final: los pasos anteriores crean copias por sitio (checkout, cabecera, pie)
                ("herencias_sitio", sitio._bt_promo_herencias_sitio, "siempre"),
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
        View = self.env["ir.ui.view"].sudo().with_context(active_test=False, website_id=False, no_cow=True)
        vistas = View.search([("key", "in", VISTAS_APAGAR), ("website_id", "=", self.id), ("active", "=", True)])
        if vistas:
            vistas.write({"active": False})
        return "%s vistas apagadas" % len(vistas)

    # ------------------------------------------------------------------ reportes PDF
    def _bt_promo_reportes(self):
        """Los PDF de la 17 (registros sin módulo: «Cotización · Promocionales» y «Carta membretada BT») ceden su lugar a
        los del módulo, que funcionan en 19: se quitan del menú Imprimir y sus vistas se archivan. No se borra nada.
        Idempotente. Reversa: volver a poner binding_model_id y active."""
        nuevos = [self.env.ref(xmlid, raise_if_not_found=False) for xmlid in REPORTES_17.values()]
        if not all(nuevos):
            return "PENDIENTE: faltan los reportes del módulo; no se toca lo de la 17"
        Reporte = self.env["ir.actions.report"].sudo()
        viejos = Reporte.search([("report_name", "in", list(REPORTES_17)), ("binding_model_id", "!=", False)])
        if viejos:
            viejos.write({"binding_model_id": False})
        View = self.env["ir.ui.view"].sudo().with_context(active_test=False, website_id=False, no_cow=True)
        vistas = View.search([("key", "in", VISTAS_REPORTE_17), ("active", "=", True)])
        if vistas:
            vistas.write({"active": False})
        return "%s reportes de la 17 fuera del menú Imprimir; %s vistas de la 17 archivadas" % (len(viejos), len(vistas))

    def _bt_promo_instalado_en(self):
        """Momento de la primera aplicación del módulo en esta base. Lo creado antes (en la 17 o en la migración) es
        anterior; lo creado después (p. ej. con el editor de la 19) se respeta."""
        ICP = self.env["ir.config_parameter"].sudo()
        valor = ICP.get_param(PARAM_INSTALADO)
        if not valor:
            valor = fields.Datetime.to_string(self.env.cr.now())
            ICP.set_param(PARAM_INSTALADO, valor)
        return fields.Datetime.to_datetime(valor)

    def _bt_promo_jubilar(self):
        """Jubila las copias del sitio de plantillas PRIMARIAS de la 17 que el paso «vistas» apaga (carrito, checkout,
        dirección, pago, confirmación, cabecera del carrito, filtro de precio, CFDI): las que están inactivas, son
        anteriores a la instalación del módulo y tienen su plantilla genérica en 19. Jubilar = cambiar la key (sufijo
        SUFIJO_JUBILADA) de la copia y de todo su subárbol del mismo sitio, para que Odoo deje de tratarlos como copias
        de la plantilla: ya no reciben herencias nuevas al actualizar módulos (de este módulo o de Odoo).

        Nada visible cambia: una primaria inactiva no se pinta (el sitio ya usa la genérica) y su subárbol no entra en
        ningún árbol de herencia; en el staging las huellas del flujo (inicio, tienda, Mi cotización con líneas, datos,
        pago, confirmación) son idénticas antes y después, y is_view_active da lo mismo (las hijas activas, como la de
        campos B2B, tienen genérica activa con el mismo arch). No toca extensiones (su copia inactiva es la que apaga
        una opción en el sitio, p. ej. la barra de cookies). Idempotente. Reversa: quitar el sufijo de las keys."""
        self.ensure_one()
        View = self.env["ir.ui.view"].sudo().with_context(active_test=False, website_id=False, no_cow=True)
        instalado = self._bt_promo_instalado_en()
        jubiladas = View.browse()
        for copia in View.search([("key", "in", VISTAS_APAGAR), ("website_id", "=", self.id), ("active", "=", False),
                                  ("mode", "=", "primary")]):
            if copia.create_date and copia.create_date >= instalado:
                continue  # copia hecha en la 19: no es de la 17
            if not View.search_count([("key", "=", copia.key), ("website_id", "=", False), ("mode", "=", "primary")]):
                continue
            pila = [copia]
            while pila:
                vista = pila.pop()
                if vista in jubiladas:
                    continue
                jubiladas |= vista
                pila.extend(vista.inherit_children_ids.filtered(lambda hija: hija.website_id == copia.website_id))
        for vista in jubiladas:
            vista.write({"key": vista.key + SUFIJO_JUBILADA})
        self.env.flush_all()  # _create_all_specific_views lee con SQL directo
        return "%s copias de la 17 jubiladas (con su subárbol)" % len(jubiladas)

    def _bt_promo_herencias_sitio(self):
        """Hace por adelantado, par por par y dentro de un savepoint, lo que Odoo hará al terminar la actualización con
        las vistas genéricas de ESTE módulo: copiarlas bajo cada copia por sitio de su vista padre. Si un par valida, la
        copia queda hecha (igual que la haría Odoo). Si falla —una copia por sitio sin las anclas de 19, p. ej. una
        edición hecha con el editor de la 17 en producción antes del corte—, deja para ese sitio un marcador INACTIVO con
        la key de la vista del módulo: Odoo ya no ve el par pendiente y la actualización termina; la personalización del
        módulo no aplica en esa plantilla de ese sitio hasta que alguien revise la copia (aviso en el log y en el
        resultado). Corre al final y siempre; sin pares pendientes no hace nada."""
        self.ensure_one()
        View = self.env["ir.ui.view"].sudo().with_context(active_test=False, website_id=False, no_cow=True)
        copiadas, marcadores = 0, []
        for generica in View.search([("type", "=", "qweb"), ("website_id", "=", False), ("inherit_id", "!=", False),
                                     ("key", "=like", MODULO + ".%")]):
            clave_padre = generica.inherit_id.key
            if not clave_padre:
                continue
            for copia_padre in View.search([("key", "=", clave_padre), ("website_id", "!=", False)]):
                sitio_id = copia_padre.website_id.id
                if View.search_count([("key", "=", generica.key), ("website_id", "=", sitio_id)]):
                    continue
                try:
                    with self.env.cr.savepoint():
                        generica.with_context(website_id=sitio_id, no_cow=False).write({"inherit_id": copia_padre.id})
                    copiadas += 1
                except Exception as error:  # noqa: BLE001 — la validación de la copia falló: marcador y aviso
                    View.create({
                        "name": "%s · marcador: no aplica en esta copia del sitio" % generica.name,
                        "key": generica.key, "website_id": sitio_id, "type": "qweb", "mode": "primary",
                        "active": False, "arch": '<t t-name="%s"/>' % generica.key,
                    })
                    marcadores.append("%s→%s" % (generica.key, copia_padre.id))
                    _logger.warning("%s: %s no aplica en la copia %s (%s) del sitio %s; se dejó un marcador. %s",
                                    MODULO, generica.key, copia_padre.id, clave_padre, sitio_id,
                                    " ".join(str(error).split())[:300])
        self.env.flush_all()
        texto = "%s herencias copiadas a copias por sitio" % copiadas
        return texto + ("; marcadores (revisar): %s" % ", ".join(marcadores) if marcadores else "")

    def _bt_promo_codigo(self):
        """Una sola vez: respalda el código inyectado de la 17 en un parámetro, conserva la verificación de Google Search
        Console y la atribución propia (ATRIBUCION_BLOQUES), y vacía lo demás (el JavaScript y los estilos de la 17)."""
        self.ensure_one()
        cabeza, pie = self.custom_code_head or "", self.custom_code_footer or ""
        if not cabeza and not pie:
            return "sin código inyectado"
        self.env["ir.config_parameter"].sudo().set_param(
            PARAM_CODIGO_RESPALDO, json.dumps({"head": cabeza, "footer": pie}, ensure_ascii=False))
        gsc = GSC_BLOQUE.search(cabeza)
        atribucion = [m.group(0) for patron in ATRIBUCION_BLOQUES for m in [patron.search(pie)] if m]
        self.write({"custom_code_head": gsc.group(0) if gsc else False,
                    "custom_code_footer": "\n".join(atribucion) or False})
        return "código inyectado respaldado y vaciado (se conservó: %s)" % (
            ", ".join((["verificación de GSC"] if gsc else []) + ["%s bloques de atribución" % len(atribucion)]))

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
