"""Vocabulario de cotización en el flujo de la tienda (decisión N2), por traducción de los términos de las vistas
estándar: sin copiar plantillas. Inventario y riesgos: odoo19/ref/R8_textos_flujo_cotizacion.md del proyecto.

Se aplica en cada instalación y actualización (una actualización de website_sale puede perder la traducción de un
término que cambió). Una clave que no existe se ignora sin error en Odoo; por eso se resuelve la fuente exacta con
get_field_translations y se reporta lo que falte.
"""
import logging
import re

from odoo import models

_logger = logging.getLogger(__name__)

TEXTOS = [  # (xmlid de la vista, término fuente en inglés, traducción es_MX)
    ('website_sale.header_cart_link', 'My Cart', 'Mi cotización'),  # H1
    ('website_sale.header_cart_link', 'eCommerce cart', 'Ver mi cotización'),  # H2
    ('website_sale.cta_wrapper', '<i class="fa fa-shopping-cart me-2"/> Add to cart', '<i class="fa fa-shopping-cart me-2"/> Agregar a cotización'),  # F1
    ('website_sale.cart', 'Order summary', 'Resumen de tu solicitud'),  # C1
    ('website_sale.cart_lines', 'Remove from cart', 'Quitar de la cotización'),  # C2
    ('website_sale.cart_lines', 'Your cart is empty!', 'Tu cotización está vacía.'),  # C3
    ('website_sale.cart_lines', 'Shop', 'Explorar el catálogo'),  # C4
    ('website_sale.cart_summary_content', 'Your cart is empty!', 'Tu cotización está vacía.'),  # C5
    ('website_sale.quick_reorder_button', '<i class="fa fa-rotate-left me-2"/>Quick reorder', '<i class="fa fa-rotate-left me-2"/>Repetir solicitud'),  # C6
    ('website_sale.quick_reorder_button', 'Login to reorder', 'Inicia sesión para repetir una solicitud anterior'),  # C7
    ('website_sale.quick_reorder_button', 'No previous products available for reorder.', 'No hay solicitudes anteriores para repetir.'),  # C8
    ('website_sale.quick_reorder_sidebar', 'Quick reorder', 'Repetir solicitud'),  # C9
    ('website_sale.quick_reorder_history', "Press 'Enter' to add to cart", 'Presiona Enter para agregar a la cotización'),  # C10
    ('website_sale.total', 'Delivery', 'Envío'),  # T1
    ('website_sale.total', 'Price will be updated after choosing a delivery method', 'El envío se cotiza aparte'),  # T2
    ('website_sale.navigation_buttons', '<i class="fa fa-angle-left me-2 fw-light"/> Continue shopping', '<i class="fa fa-angle-left me-2 fw-light"/> Seguir explorando el catálogo'),  # N1
    ('website_sale.navigation_buttons', 'Confirm Order', 'Confirmar solicitud'),  # N2
    ('website_sale.checkout_layout', 'Order', 'Solicitud'),  # N3
    ('website_sale.checkout_layout', 'Coupon, Gift card, Promo-code?', 'Revisar mi solicitud'),  # N4
    ('website_sale.checkout', 'Shop - Checkout', 'Datos de contacto'),  # D1
    ('website_sale.address_edit_button', '<i class="fa fa-pencil me-1"/>Want an invoice?', '<i class="fa fa-pencil me-1"/>¿Necesitas factura?'),  # D2
    ('website_sale.address', 'You are editing your <b>delivery and billing</b> addresses at the same time!<br/> If you want to modify your billing address, create a <a class="o_translate_inline" href="/shop/address?address_type=billing">new address</a>.', 'Estás editando tus direcciones de <b>entrega y facturación</b> al mismo tiempo.<br/> Si quieres modificar tu dirección de facturación, crea una <a class="o_translate_inline" href="/shop/address?address_type=billing">nueva dirección</a>.'),  # D3
    ('website_sale.delivery_method', '<span class="o_wsale_delivery_price_badge text-muted fw-bold text-end" name="price"> <small class="fw-normal">Select to compute delivery rate</small> </span>', '<span class="o_wsale_delivery_price_badge text-muted fw-bold text-end" name="price"> <small class="fw-normal">El envío se cotiza aparte</small> </span>'),  # D4
    ('l10n_mx_edi_website_sale.l10n_mx_edi_invoicing_info', 'Do you need an invoice?', '¿Necesitas factura?'),  # M1
    ('l10n_mx_edi_website_sale.l10n_mx_edi_invoicing_info', 'Yes', 'Sí'),  # M2
    ('l10n_mx_edi_website_sale.l10n_mx_edi_invoicing_info', 'Changing VAT number is not allowed once document(s) have been issued for your account. Please contact us directly for this operation.', 'No puedes cambiar el RFC una vez que se han emitido documentos para tu cuenta. Contáctanos directamente para realizar esta operación.'),  # M3
    ('auth_signup.login', "Don't have an account?", '¿No tienes una cuenta?'),  # L1
    ('website_sale.payment', 'Shop - Select Payment Method', 'Confirmar solicitud'),  # P1
    ('website_sale.payment', 'Confirm order', 'Confirmar solicitud'),  # P2
    ('payment.form', 'Pay', 'Confirmar solicitud'),  # P3
    ('payment.form', 'Payment method', 'Forma de pago'),  # P4
    ('website_sale.confirmation', 'Shop - Confirmed', 'Solicitud recibida'),  # K1
    ('website_sale.confirmation', 'Thank you for your order.', 'Recibimos tu solicitud de cotización.'),  # K2
    ('website_sale.confirmation', '<span>Order</span>', '<span>Solicitud</span>'),  # K3
    ('website_sale.confirmation', '<span class="align-middle">to follow your order.</span>', '<span class="align-middle">para dar seguimiento a tu solicitud.</span>'),  # K4
    ('website_sale.payment_confirmation_status', '<b>Communication: </b>', '<b>Referencia de tu solicitud: </b>'),  # K5
    ('website.list_hybrid', "Your search '", 'No encontramos resultados para «'),  # B1 (D6: sin ustedeo)
    ('website.list_hybrid', "' did not match anything.", '».'),  # B2
    ('website.list_hybrid', "' did not match anything. Results are displayed for '", '». Te mostramos los resultados para «'),  # B3
    ('website.list_hybrid', "'.", '».'),  # B4
    ('website.list_hybrid', 'Specify a search term.', 'Escribe qué producto buscas.'),  # B5
    ('website.list_hybrid', 'Search Results', 'Resultados de búsqueda'),  # B6
]

TEXTOS_LATENTES = [  # hoy no se pintan (opción apagada, estado raro o con sesión); aplicarlos es inocuo
    ('website_sale.cart', 'Your previous cart has already been completed.', 'Tu solicitud anterior ya fue completada.'),  # A1
    ('website_sale.cart', 'Please proceed your current cart.', 'Continúa con tu solicitud actual.'),  # A2
    ('website_sale.cart', 'This is your current cart.', 'Esta es tu solicitud actual.'),  # A3
    ('website_sale.cart', 'Click here', 'Haz clic aquí'),  # A4
    ('website_sale.cart', 'if you want to restore your previous cart. Your current cart will be replaced with your previous cart.', 'si quieres recuperar tu solicitud anterior. La solicitud actual se reemplazará por la anterior.'),  # A5
    ('website_sale.cart', 'if you want to merge your previous cart into current cart.', 'si quieres combinar tu solicitud anterior con la actual.'),  # A6
    ('website_sale.address', '<span class="align-middle">Already have an account?</span>', '<span class="align-middle">¿Ya tienes una cuenta?</span>'),  # A7
    ('website_sale.payment_confirmation_status', '<span>Unfortunately your order can not be confirmed as the amount of your payment does not match the amount of your cart. Please contact the responsible of the shop for more information.</span>', '<span>No podemos confirmar tu solicitud porque el monto recibido no coincide con el total de tu cotización. Escríbenos y te ayudamos.</span>'),  # A8
    ('website_sale.shop_product_buttons', 'Add to cart', 'Agregar a cotización'),  # A9
    ('website_sale.shop_product_buttons', '<i class="fa fa-fw fa-shopping-cart o_not-animable" role="presentation"/> <span class="o_label small ms-1">Add to Cart</span>', '<i class="fa fa-fw fa-shopping-cart o_not-animable" role="presentation"/> <span class="o_label small ms-1">Agregar a cotización</span>'),  # A10
    ('website_sale.dynamic_filter_template_product_product_products_item', 'Add to Cart', 'Agregar a cotización'),  # A11
    ('website_sale.dynamic_filter_template_product_product_products_item', '<i class="fa fa-shopping-cart fa-fw" role="presentation"/><span class="o_label small ms-1">Add to Cart</span>', '<i class="fa fa-shopping-cart fa-fw" role="presentation"/><span class="o_label small ms-1">Agregar a cotización</span>'),  # A12
    ('website_sale.s_add_to_cart', '<i class="fa fa-cart-plus me-2"/>Add to Cart', '<i class="fa fa-cart-plus me-2"/>Agregar a cotización'),  # A13
    ('website_sale.suggested_products_list', '<i class="d-md-none fa fa-shopping-cart" role="presentation"/> <span class="d-none d-md-inline">Add to cart</span>', '<i class="d-md-none fa fa-shopping-cart" role="presentation"/> <span class="d-none d-md-inline">Agregar a cotización</span>'),  # A14
    ('website_sale.product_buy_now', '<i class="fa fa-bolt me-2"/> Buy now', '<i class="fa fa-bolt me-2"/> Solicitar cotización'),  # A15
    ('website_sale.product', 'Contact Us', 'Solicitar cotización'),  # A16
    ('website.header_call_to_action', 'Contact Us', 'Contáctanos'),  # A17
    ('website_sale.sale_order_re_order_btn', '<i class="fa fa-rotate-right me-1"/> Order Again', '<i class="fa fa-rotate-right me-1"/> Repetir pedido'),  # A18
]

TITULOS_VISTA = [  # (xmlid de la vista, website_meta_title es_MX): el <title> sale del NOMBRE de la vista (no traducible) salvo que este campo exista
    ('website_sale.products', 'Catálogo de artículos promocionales'),  # TI1
    ('website_sale.cart', 'Mi cotización'),  # TI2
    ('website_sale.address', 'Datos de contacto'),  # TI3
    ('website_sale.extra_info', 'Información adicional'),  # TI4
    ('website.list_hybrid', 'Resultados de búsqueda'),  # TI5
    ('web.login', 'Iniciar sesión'),  # TI6
]


def _norm(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


class Website(models.Model):
    _inherit = "website"

    def _bt_promo_textos(self, lang="es_MX"):
        """Sin website_id en el contexto: se traducen las vistas genéricas (con website_id el COW crearía copias)."""
        env = self.env(context=dict(self.env.context, website_id=False))
        View = env["ir.ui.view"].sudo().with_context(active_test=False)
        faltan, aplicados = [], 0
        for lista in (TEXTOS, TEXTOS_LATENTES):
            for xmlid, fuente, destino in lista:
                vista = env.ref(xmlid, raise_if_not_found=False)
                if not vista:
                    faltan.append("%s: vista inexistente" % xmlid)
                    continue
                vista = vista.sudo()
                terminos, _contexto = vista.get_field_translations("arch_db", langs=[lang])
                exactos = {t["source"] for t in terminos if _norm(t["source"]) == _norm(fuente)}
                if not exactos:
                    faltan.append("%s: «%s»" % (xmlid, _norm(fuente)[:60]))
                    continue
                vista.update_field_translations("arch_db", {lang: {src: destino for src in exactos}})
                aplicados += 1
        for xmlid, titulo in TITULOS_VISTA:
            for vista in View.search([("key", "=", xmlid)]):  # genérica y copias del sitio (extra_info tiene copia)
                vista.update_field_translations("website_meta_title", {lang: titulo})
        if faltan:
            _logger.warning("brandtrendy_promo_theme: términos sin traducir: %s", faltan)
        return "textos: %s aplicados, %s títulos%s" % (
            aplicados, len(TITULOS_VISTA), "; sin fuente: %s" % faltan if faltan else "")
