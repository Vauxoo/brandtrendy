"""Encabezados de seguridad solo para los hosts del sitio Promocionales.

El backend (brandtrendy.odoo.com) no se toca: el filtro es por host, configurable en el parámetro
`bt_security_headers.hosts` (lista separada por comas; `off` apaga el módulo sin desinstalarlo). HSTS y la cookie
Secure solo se ponen sobre HTTPS. La vigencia de HSTS sale de `bt_security_headers.hsts_max_age` y arranca en un día
para subirla por etapas (semana, mes, año) sin desplegar código. La CSP va en modo reporte: no bloquea nada (editor
del sitio, GA4, pixeles) mientras se revisa.
"""
import logging

from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)

PARAM_HOSTS = "bt_security_headers.hosts"
PARAM_HSTS = "bt_security_headers.hsts_max_age"
HOSTS_DEFAULT = "promocionales.brandtrendy.com.mx"
HSTS_DEFAULT = 86400
APAGADO = "off"
HEADERS = {
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy-Report-Only": (
        "default-src 'self' https: data: blob: 'unsafe-inline' 'unsafe-eval'; "
        "frame-ancestors 'self'; object-src 'none'; base-uri 'self'"
    ),
}


def _cookie_segura(cookie):
    minus = cookie.lower()
    if "; secure" not in minus:
        cookie += "; Secure"
    if "samesite=" not in minus:
        cookie += "; SameSite=Lax"
    return cookie


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _post_dispatch(cls, response):
        super()._post_dispatch(response)
        try:
            cls._bt_security_headers(response)
        except Exception:  # un encabezado nunca debe tumbar una respuesta
            _logger.exception("bt_security_headers: no se pudieron poner los encabezados")

    @classmethod
    def _bt_security_headers(cls, response):
        if not request.db:
            return
        req = request.httprequest
        icp = request.env["ir.config_parameter"].sudo()
        valor = (icp.get_param(PARAM_HOSTS, HOSTS_DEFAULT) or "").strip().lower()
        if valor == APAGADO:
            return
        hosts = {h.strip() for h in valor.split(",") if h.strip()}
        if req.host.split(":")[0].lower() not in hosts:
            return
        headers = response.headers
        for nombre, contenido in HEADERS.items():
            if nombre not in headers:
                headers[nombre] = contenido
        reenviado = req.headers.get("X-Forwarded-Proto", "").split(",")[0].strip().lower()
        if req.scheme != "https" and reenviado != "https":
            return
        if "Strict-Transport-Security" not in headers:
            try:
                vigencia = int(icp.get_param(PARAM_HSTS, HSTS_DEFAULT))
            except (TypeError, ValueError):
                vigencia = HSTS_DEFAULT
            if vigencia > 0:
                headers["Strict-Transport-Security"] = f"max-age={vigencia}"
        cookies = headers.getlist("Set-Cookie")
        if cookies:
            # se arma la lista nueva antes de tocar la respuesta: si algo falla, las cookies originales quedan intactas
            nuevas = [_cookie_segura(c) for c in cookies]
            headers.remove("Set-Cookie")
            for cookie in nuevas:
                headers.add("Set-Cookie", cookie)
