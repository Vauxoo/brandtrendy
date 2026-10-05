"""Páginas del sitio como contenido del editor, entregadas por el módulo.

Cada archivo ``paginas/<nombre>.xml`` tiene un elemento raíz ``<pagina>`` con sus metadatos y, dentro, las secciones
(bloques del editor 19). Al aplicar, el módulo:
  * resuelve los marcadores ``{{categoria:<ruta>}}`` (id) y ``{{url_categoria:<ruta>}}`` (URL canónica) por la ruta
    de nombres de la categoría pública, ``{{filtro:<xmlid>}}`` (id del filtro del listado) y ``{{clases_tienda}}``
    (clases de diseño de tarjeta de la tienda del sitio); nunca ids escritos en el módulo;
  * adopta la página existente del sitio por su URL (o la crea) y escribe el contenido en en_US y es_MX;
  * no pisa una página que alguien editó en el editor después de la última aplicación (huella guardada en un
    parámetro): la deja y lo registra.
"""
import hashlib
import html
import logging
import os
import re

from lxml import etree

from odoo import models
from odoo.tools.misc import file_open, file_path

_logger = logging.getLogger(__name__)

MODULO = "brandtrendy_promo_theme"
PARAM_HUELLA = MODULO + ".pagina."  # + url → sha1 del arch que dejó el módulo
MARCADOR = re.compile(r"\{\{(categoria|url_categoria|filtro):([^}]+)\}\}")
CLASES_TIENDA = "{{clases_tienda}}"
LANGS = ("en_US", "es_MX")
COPYRIGHT_ARCH = """<data inherit_id="website.layout" priority="15">
    <xpath expr="//footer//span[hasclass('o_footer_copyright_name')]" position="replace">
        <span class="o_footer_copyright_name me-2 small">© Brandtrendy · Artículos promocionales para empresas</span>
    </xpath>
    <xpath expr="//div[hasclass('o_footer_copyright')]//div[hasclass('col-sm')]" position="attributes">
        <attribute name="class" remove="col-sm text-sm-start" add="col-md d-flex flex-column-reverse gap-2 text-md-start" separator=" "/>
    </xpath>
</data>"""


def _huella(texto):
    return hashlib.sha1((texto or "").encode()).hexdigest()


class Website(models.Model):
    _inherit = "website"

    def _bt_promo_archivos_pagina(self):
        try:
            carpeta = file_path(MODULO + "/paginas")
        except FileNotFoundError:
            return []
        return sorted(f for f in os.listdir(carpeta) if f.endswith(".xml"))

    def _bt_promo_categoria(self, ruta):
        Categoria = self.env["product.public.category"].sudo()
        padre = Categoria
        # El libxml2 del servidor puede serializar acentos de atributos como entidades (&#xF3;): se decodifican.
        ruta = html.unescape(ruta)
        for nombre in [p.strip() for p in ruta.split("/") if p.strip()]:
            dominio = [("name", "=", nombre), ("parent_id", "=", padre.id or False)]
            padre = Categoria.search(dominio, limit=1)
            if not padre:
                return Categoria
        return padre

    def _bt_promo_resolver(self, texto, faltantes):
        texto = texto.replace(CLASES_TIENDA, self.shop_opt_products_design_classes or "")

        def sustituye(m):
            if m.group(1) == "filtro":
                filtro = self.env.ref(m.group(2).strip(), raise_if_not_found=False)
                if not filtro:
                    faltantes.add(m.group(2).strip())
                return str(filtro.id) if filtro else "0"
            categoria = self._bt_promo_categoria(m.group(2))
            if not categoria:
                faltantes.add(m.group(2).strip())
                return "0" if m.group(1) == "categoria" else "/shop"
            if m.group(1) == "categoria":
                return str(categoria.id)
            return "/shop/category/%s" % self.env["ir.http"]._slug(categoria)
        return MARCADOR.sub(sustituye, texto)

    def _bt_promo_paginas(self):
        self.ensure_one()
        ICP = self.env["ir.config_parameter"].sudo()
        hechas, saltadas, faltantes = [], [], set()
        for archivo in self._bt_promo_archivos_pagina():
            with file_open("%s/paginas/%s" % (MODULO, archivo), "rb") as f:
                raiz = etree.fromstring(f.read())
            url = raiz.get("url")
            contenido = "".join(etree.tostring(hijo, encoding="unicode") for hijo in raiz)
            contenido = self._bt_promo_resolver(contenido, faltantes)
            vista, pagina = self._bt_promo_vista_de(url, raiz)
            arch = ('<t name="%s" t-name="%s"><t t-call="website.layout">'
                    '<div id="wrap" class="oe_structure oe_empty">%s</div></t></t>') % (
                raiz.get("nombre"), vista.key, contenido)
            clave = PARAM_HUELLA + url
            anterior = ICP.get_param(clave)
            actual = vista.with_context(lang="es_MX").arch_db
            if anterior and _huella(actual) != anterior:
                saltadas.append(url)  # alguien la editó después de la última aplicación: no se pisa
                continue
            self._bt_promo_apagar_herencias(vista)  # antes de escribir: una herencia rota invalidaría el arch nuevo
            for lang in LANGS:
                vista.with_context(lang=lang).write({
                    "arch_db": arch,
                    "website_meta_title": raiz.get("titulo") or False,
                    "website_meta_description": raiz.get("descripcion") or False,
                })
            if pagina:
                vals_pagina = {
                    "is_published": raiz.get("publicada", "1") == "1",
                    "website_indexed": raiz.get("indexada", "1") == "1",
                }
                if url != "/":
                    # En 19, renombrar una página regenera la key de su vista (website_page.py l.186-187): en la home
                    # eso rompería «website.homepage».
                    vals_pagina["name"] = raiz.get("nombre")
                pagina.write(vals_pagina)
            ICP.set_param(clave, _huella(vista.with_context(lang="es_MX").arch_db))
            hechas.append(url)
        if faltantes:
            _logger.warning("%s: categorías inexistentes en las páginas: %s", MODULO, sorted(faltantes))
        if saltadas:
            _logger.warning("%s: páginas editadas a mano, no se pisaron: %s", MODULO, saltadas)
        return "páginas: %s aplicadas, %s respetadas (editadas)%s" % (
            len(hechas), len(saltadas), "; categorías faltantes: %s" % sorted(faltantes) if faltantes else "")

    def _bt_promo_apagar_herencias(self, vista):
        """Las páginas que vienen de la 17 traen herencias propias del sitio (p. ej. /contactus: una con xpath roto y otra
        con el bloque viejo). El contenido ahora es completo en el arch de la página: se apagan las herencias del sitio
        que no son de este módulo."""
        hijas = vista.with_context(active_test=True).inherit_children_ids.filtered(
            lambda v: v.website_id == self and not (v.key or "").startswith(MODULO + "."))
        if hijas:
            hijas.write({"active": False})
        return hijas

    def _bt_promo_vista_de(self, url, raiz):
        """Vista (y página, si aplica) del sitio para esa URL; las crea si no existen."""
        self.ensure_one()
        View = self.env["ir.ui.view"].sudo()
        if url == "/":
            home = self.with_context(website_id=self.id).viewref("website.homepage")
            if home.website_id != self:
                # Primera vez en un sitio sin copia propia: el COW crea la copia del sitio.
                home.with_context(website_id=self.id).write({"active": True})
                home = self.with_context(website_id=self.id).viewref("website.homepage")
            pagina = self.env["website.page"].sudo().search([("view_id", "=", home.id)], limit=1)
            return home, pagina
        pagina = self.env["website.page"].sudo().search([("url", "=", url), ("website_id", "=", self.id)], limit=1)
        if pagina:
            return pagina.view_id, pagina
        clave = "%s.pagina_%s" % (MODULO, re.sub(r"[^a-z0-9]+", "_", url.strip("/").lower()) or "inicio")
        vista = View.create({"name": raiz.get("nombre"), "type": "qweb", "key": clave, "website_id": self.id,
                             "arch_db": '<t t-name="%s"><t t-call="website.layout"/></t>' % clave})
        pagina = self.env["website.page"].sudo().create({"url": url, "view_id": vista.id, "website_id": self.id})
        return vista, pagina

    def _bt_promo_pie(self):
        """Pie del sitio (copia del sitio de website.footer_custom) desde contenido/pie.xml, con la misma protección
        de huella que las páginas."""
        self.ensure_one()
        with file_open("%s/contenido/pie.xml" % MODULO, "rb") as f:
            raiz = etree.fromstring(f.read())
        faltantes = set()
        contenido = self._bt_promo_resolver("".join(etree.tostring(h, encoding="unicode") for h in raiz), faltantes)
        vista = self.with_context(website_id=self.id).viewref("website.footer_custom")
        if vista.website_id != self:
            vista.with_context(website_id=self.id).write({"active": True})  # COW: copia del sitio
            vista = self.with_context(website_id=self.id).viewref("website.footer_custom")
        arch = ('<data name="Default" active="True"><xpath expr="//div[@id=\'footer\']" position="replace">'
                '<div id="footer" class="oe_structure oe_structure_solo text-break" t-ignore="true" '
                't-if="not no_footer">%s</div></xpath></data>') % contenido
        ICP = self.env["ir.config_parameter"].sudo()
        clave = PARAM_HUELLA + "__pie__"
        anterior = ICP.get_param(clave)
        if anterior and _huella(vista.with_context(lang="es_MX").arch_db) != anterior:
            return "pie editado a mano: se respeta"
        for lang in LANGS:
            vista.with_context(lang=lang).write({"arch_db": arch, "active": True})
        ICP.set_param(clave, _huella(vista.with_context(lang="es_MX").arch_db))
        # Copyright propio del sitio (la plantilla estándar trae el texto de ejemplo «Copyright © Company name»).
        derechos = self._bt_promo_vista_del_sitio("website.footer_copyright_company_name", True)
        if derechos:
            for lang in LANGS:
                derechos.with_context(lang=lang, website_id=False).write({"arch_db": COPYRIGHT_ARCH})
        if faltantes:
            return "PENDIENTE (categorías faltantes: %s); pie aplicado" % sorted(faltantes)
        return "pie aplicado"

