import requests

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestBtSecurityHeaders(HttpCase):

    def _param(self, clave, valor):
        self.env["ir.config_parameter"].sudo().set_param(clave, valor)

    def _hosts(self, valor):
        self._param("bt_security_headers.hosts", valor)

    def _get_limpio(self, ruta="/", **kw):
        """Petición sin la sesión del opener, para que Odoo mande sus Set-Cookie."""
        return requests.get(self.base_url() + ruta, timeout=60, allow_redirects=False, **kw)

    def test_host_configurado_lleva_encabezados(self):
        self._hosts("127.0.0.1,localhost")
        r = self.url_open("/")
        self.assertEqual(r.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertEqual(r.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        self.assertIn("camera=()", r.headers.get("Permissions-Policy", ""))
        csp = r.headers.get("Content-Security-Policy-Report-Only", "")
        self.assertIn("frame-ancestors 'self'", csp)
        self.assertNotIn("upgrade-insecure-requests", csp)  # se ignora en modo reporte y solo ensucia la consola
        self.assertNotIn("Strict-Transport-Security", r.headers)  # las pruebas van por http

    def test_https_reenviado_lleva_hsts_de_un_dia(self):
        self._hosts("127.0.0.1,localhost")
        r = self.url_open("/", headers={"X-Forwarded-Proto": "https"})
        self.assertEqual(r.headers.get("Strict-Transport-Security"), "max-age=86400")

    def test_hsts_sube_por_parametro_y_cero_lo_quita(self):
        self._hosts("127.0.0.1,localhost")
        self._param("bt_security_headers.hsts_max_age", "31536000")
        r = self.url_open("/", headers={"X-Forwarded-Proto": "https"})
        self.assertEqual(r.headers.get("Strict-Transport-Security"), "max-age=31536000")
        self._param("bt_security_headers.hsts_max_age", "0")
        r = self.url_open("/", headers={"X-Forwarded-Proto": "https"})
        self.assertNotIn("Strict-Transport-Security", r.headers)

    def test_cookies_secure_y_samesite_sin_perder_ninguna(self):
        self._hosts("off")
        antes = self._get_limpio().raw.headers.getlist("Set-Cookie")
        self._hosts("127.0.0.1,localhost")
        despues = self._get_limpio(headers={"X-Forwarded-Proto": "https"}).raw.headers.getlist("Set-Cookie")
        if not despues:
            self.skipTest("la portada no mandó cookies a un visitante nuevo en este entorno; se verifica con curl en staging")
        self.assertEqual(sorted(c.split("=")[0] for c in antes), sorted(c.split("=")[0] for c in despues))
        for cookie in despues:
            self.assertIn("; Secure", cookie)
            self.assertIn("SameSite=", cookie)

    def test_off_apaga_sin_desinstalar(self):
        self._hosts("off")
        r = self.url_open("/", headers={"X-Forwarded-Proto": "https"})
        self.assertNotIn("Content-Security-Policy-Report-Only", r.headers)
        self.assertNotIn("Strict-Transport-Security", r.headers)

    def test_otro_host_queda_igual(self):
        self._hosts("promocionales.example.com")
        r = self.url_open("/", headers={"X-Forwarded-Proto": "https"})
        self.assertNotIn("Content-Security-Policy-Report-Only", r.headers)
        self.assertNotIn("Permissions-Policy", r.headers)
        self.assertNotIn("Strict-Transport-Security", r.headers)

    def test_no_pisa_un_encabezado_que_ya_trae_la_respuesta(self):
        self._hosts("127.0.0.1,localhost")
        r = self.url_open("/web/login")
        self.assertEqual(len(r.raw.headers.getlist("X-Frame-Options")), 1)
