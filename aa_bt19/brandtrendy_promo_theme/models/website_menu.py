"""Menú del sitio entregado por el módulo: árbol de dos niveles y megamenú de categorías sin conteos ni productos fijos.

Las categorías se resuelven por su ruta de nombres al aplicar; si una no existe, su entrada se omite y se registra.
"""
import logging
from html import escape

from odoo import models

_logger = logging.getLogger(__name__)

POR_OCASION = "Promocionales / Por ocasión"
POR_INDUSTRIA = "Promocionales / Por industria"

# (nombre, destino, hijos). Destino: URL literal, «cat:<ruta>» (categoría) o «mega» (megamenú de categorías).
MENU = [
    ("Productos", "mega", []),
    ("Por ocasión", None, [
        ("Agendas 2027", "/agendas-2027"),
        ("Fin de año", "/ocasiones/fin-de-ano"),
        ("Regalos ejecutivos", "/ocasiones/regalos-ejecutivos"),
        ("Bienvenida a colaboradores", "cat:%s / Bienvenida a colaboradores" % POR_OCASION),
        ("Eventos deportivos", "cat:%s / Eventos deportivos" % POR_OCASION),
        ("Oficina y home office", "cat:%s / Oficina y home office" % POR_OCASION),
        ("Ver todas las ocasiones", "cat:%s" % POR_OCASION),
    ]),
    ("Por industria", None, [
        ("Corporativo y oficinas", "cat:%s / Corporativo y oficinas" % POR_INDUSTRIA),
        ("Salud y farmacéutica", "cat:%s / Salud y farmacéutica" % POR_INDUSTRIA),
        ("Educación", "cat:%s / Educación" % POR_INDUSTRIA),
        ("Empresas de tecnología", "cat:%s / Empresas de tecnología" % POR_INDUSTRIA),
        ("Congresos y exposiciones", "cat:%s / Congresos y exposiciones" % POR_INDUSTRIA),
        ("Restaurantes y hotelería", "cat:%s / Restaurantes y hotelería" % POR_INDUSTRIA),
        ("Ver todas las industrias", "cat:%s" % POR_INDUSTRIA),
    ]),
    ("Kits", "/kits", []),
    ("Cómo funciona", "/proceso-de-personalizacion", []),
    ("Contacto", "/contactus", []),
]

# Columnas del megamenú «Productos»: categorías raíz bajo «Promocionales», agrupadas para escanear rápido.
MEGAMENU = [
    ("Para tomar y llevar", ["Termos y botellas", "Tazas y vasos", "Bolsas y mochilas", "Viaje"]),
    ("Oficina y escritura", ["Oficina", "Escritura", "Tecnología", "Reconocimientos"]),
    ("Textil y estilo de vida", ["Textiles", "Hogar", "Cuidado personal", "Deporte y bienestar"]),
    ("Regalos y eventos", ["Regalos corporativos", "Kits promocionales", "Eventos y exposiciones",
                           "Productos ecológicos"]),
]


class Website(models.Model):
    _inherit = "website"

    def _bt_promo_url_categoria(self, ruta, faltantes):
        categoria = self._bt_promo_categoria(ruta)
        if not categoria:
            faltantes.add(ruta)
            return None
        return "/shop/category/%s" % self.env["ir.http"]._slug(categoria)

    def _bt_promo_megamenu(self, faltantes):
        columnas = []
        for titulo, nombres in MEGAMENU:
            enlaces = []
            for nombre in nombres:
                url = self._bt_promo_url_categoria("Promocionales / %s" % nombre, faltantes)
                if url:
                    enlaces.append('<a href="%s" class="nav-link px-0" data-name="Menu Item">%s</a>'
                                   % (escape(url), escape(nombre)))
            columnas.append(
                '<div class="col-12 col-lg-3 pt16 pb24"><p class="h5 fw-bold mt-0 mb-2">%s</p>'
                '<nav class="nav flex-column">%s</nav></div>' % (escape(titulo), "".join(enlaces)))
        return (
            '<section class="s_mega_menu_odoo_menu pt16 o_colored_level o_cc o_cc1" data-name="Mega Menu">'
            '<div class="container"><div class="row">%s</div></div>'
            '<div class="container-fluid border-top s_mega_menu_odoo_menu_footer"><div class="container py-3">'
            '<a href="/shop" class="btn btn-primary">Ver todo el catálogo</a></div></div></section>'
        ) % "".join(columnas)

    def _bt_promo_menu(self):
        """Reconstruye el menú superior del sitio (se aplica por versión: entre versiones se respetan cambios hechos a
        mano). Quita también los menús que otros módulos agregan solos al instalarse (p. ej. «Jobs»)."""
        self.ensure_one()
        raiz = self.menu_id
        if not raiz:
            return "el sitio no tiene menú raíz"
        Menu = self.env["website.menu"].sudo().with_context(lang="es_MX")
        faltantes = set()
        raiz.child_id.unlink()
        for secuencia, (nombre, destino, hijos) in enumerate(MENU, start=1):
            vals = {"name": nombre, "parent_id": raiz.id, "website_id": self.id, "sequence": secuencia * 10}
            if destino == "mega":
                vals.update(url="#", mega_menu_content=self._bt_promo_megamenu(faltantes),
                            mega_menu_classes="border-top-0")
            elif destino:
                vals["url"] = destino
            else:
                vals["url"] = "#"
            menu = Menu.create(vals)
            for i, (hijo, url) in enumerate(hijos, start=1):
                if url.startswith("cat:"):
                    url = self._bt_promo_url_categoria(url[4:], faltantes)
                    if not url:
                        continue
                Menu.create({"name": hijo, "url": url, "parent_id": menu.id, "website_id": self.id,
                             "sequence": i * 10})
        if faltantes:
            _logger.warning("brandtrendy_promo_theme: categorías del menú inexistentes: %s", sorted(faltantes))
        texto = "menú: %s entradas" % len(MENU)
        return ("PENDIENTE (categorías faltantes: %s); " % sorted(faltantes) + texto) if faltantes else texto
