"""D3 · las páginas de industria y de ocasión de la versión 17 pasan a categorías públicas con redirección 301.

Una página existente se sirve antes que la redirección (website/models/ir_http.py: primero _serve_page, después
_serve_redirect) aunque esté despublicada; por eso se borra la página vieja y se crea la 301. Si la categoría destino no
existe todavía (los datos de categorías van en un lote aparte), no se toca nada de esa URL y se registra.
"""
import logging

from odoo import models

_logger = logging.getLogger(__name__)

POR_OCASION = "Promocionales / Por ocasión"
POR_INDUSTRIA = "Promocionales / Por industria"

REDIRECCIONES = [  # (URL vieja, ruta de la categoría destino)
    ("/industrias", POR_INDUSTRIA),
    ("/industrias/corporativo-y-oficinas", POR_INDUSTRIA + " / Corporativo y oficinas"),
    ("/industrias/salud", POR_INDUSTRIA + " / Salud y farmacéutica"),
    ("/industrias/educacion", POR_INDUSTRIA + " / Educación"),
    ("/industrias/tecnologia", POR_INDUSTRIA + " / Empresas de tecnología"),
    ("/industrias/eventos-y-expos", POR_INDUSTRIA + " / Congresos y exposiciones"),
    ("/industrias/restaurantes-y-hoteleria", POR_INDUSTRIA + " / Restaurantes y hotelería"),
    ("/ocasiones", POR_OCASION),
    ("/ocasiones/onboarding", POR_OCASION + " / Bienvenida a colaboradores"),
    ("/ocasiones/regreso-a-clases", POR_INDUSTRIA + " / Educación"),
]


class Website(models.Model):
    _inherit = "website"

    def _bt_promo_rutas(self):
        self.ensure_one()
        Pagina = self.env["website.page"].sudo()
        Rewrite = self.env["website.rewrite"].sudo().with_context(active_test=False)
        hechas, pendientes = [], []
        for url_vieja, ruta in REDIRECCIONES:
            categoria = self._bt_promo_categoria(ruta)
            if not categoria:
                pendientes.append(url_vieja)
                continue
            destino = "/shop/category/%s" % self.env["ir.http"]._slug(categoria)
            pagina = Pagina.search([("url", "=", url_vieja), ("website_id", "=", self.id)])
            if pagina:
                pagina.unlink()
            vals = {"name": "Promocionales · %s" % url_vieja, "url_from": url_vieja, "url_to": destino,
                    "redirect_type": "301", "website_id": self.id, "active": True}
            regla = Rewrite.search([("url_from", "=", url_vieja), ("website_id", "=", self.id)], limit=1)
            if regla:
                regla.write(vals)
            else:
                Rewrite.create(vals)
            hechas.append(url_vieja)
        if pendientes:
            _logger.warning("brandtrendy_promo_theme: 301 pendientes (falta la categoría): %s", pendientes)
        texto = "301: %s hechas" % len(hechas)
        return ("PENDIENTE (falta la categoría de %s); " % pendientes + texto) if pendientes else texto
