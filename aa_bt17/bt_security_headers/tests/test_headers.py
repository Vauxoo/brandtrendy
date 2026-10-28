from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestBtSecurityHeaders(HttpCase):

    def _hosts(self, valor):
        self.env["ir.config_parameter"].sudo().set_param("bt_security_headers.hosts", valor)

    def test_host_configurado_lleva_encabezados(self):
        self._hosts("127.0.0.1,localhost")
        r = self.url_open("/")
        self.assertEqual(r.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertEqual(r.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        self.assertIn("frame-ancestors 'self'", r.headers.get("Content-Security-Policy-Report-Only", ""))
        self.assertNotIn("Strict-Transport-Security", r.headers)  # las pruebas van por http

    def test_https_reenviado_lleva_hsts_y_cookie_secure(self):
        self._hosts("127.0.0.1,localhost")
        r = self.url_open("/", headers={"X-Forwarded-Proto": "https"})
        self.assertEqual(r.headers.get("Strict-Transport-Security"), "max-age=31536000")
        cookies = r.headers.get("Set-Cookie")
        if cookies:
            self.assertIn("Secure", cookies)

    def test_otro_host_queda_igual(self):
        self._hosts("promocionales.example.com")
        r = self.url_open("/")
        self.assertNotIn("X-Frame-Options", r.headers)
        self.assertNotIn("Content-Security-Policy-Report-Only", r.headers)
