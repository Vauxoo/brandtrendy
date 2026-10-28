"""Encabezados de seguridad solo para los hosts del sitio Promocionales.

El backend (brandtrendy.odoo.com) no se toca: el filtro es por host, configurable en el parámetro
`bt_security_headers.hosts` (lista separada por comas). HSTS y la cookie Secure solo se ponen sobre HTTPS.
La CSP va en modo reporte: no bloquea nada (editor del sitio, GA4, pixeles) mientras se revisa.
"""
import logging

from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)

PARAM_HOSTS = "bt_security_headers.hosts"
HOSTS_DEFAULT = "promocionales.brandtrendy.com.mx"
HSTS = "max-age=31536000"
HEADERS = {
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy-Report-Only": (
        "default-src 'self' https: data: blob: 'unsafe-inline' 'unsafe-eval'; "
        "frame-ancestors 'self'; object-src 'none'; base-uri 'self'; upgrade-insecure-requests"
    ),
}


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
        valor = request.env["ir.config_parameter"].sudo().get_param(PARAM_HOSTS, HOSTS_DEFAULT)
        hosts = {h.strip().lower() for h in (valor or "").split(",") if h.strip()}
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
            headers["Strict-Transport-Security"] = HSTS
        cookies = headers.getlist("Set-Cookie")
        if cookies:
            headers.remove("Set-Cookie")
            for cookie in cookies:
                minus = cookie.lower()
                if "; secure" not in minus:
                    cookie += "; Secure"
                if "samesite=" not in minus:
                    cookie += "; SameSite=Lax"
                headers.add("Set-Cookie", cookie)
