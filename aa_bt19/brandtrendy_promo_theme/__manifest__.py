{
    "name": "Brandtrendy · Promocionales (sitio de cotización)",
    "summary": "Reproduce el sitio «Promocionales Brandtrendy» sobre el estándar de Odoo 19: "
    "configuración, tema del sitio, pasos de cotización y solicitud ligada a su lead en servidor.",
    "author": "Brandtrendy",
    "website": "https://promocionales.brandtrendy.com.mx",
    "license": "LGPL-3",
    "category": "Website/Website",
    "version": "19.0.1.0.2",
    "depends": [
        "website_sale",
        "website_crm",
        "sale_crm",
        "sale_management",
        "base_automation",
    ],
    "data": [
        "data/lista_blanca.xml",
        "data/filtros_listado.xml",
        "data/plantillas_correo.xml",
        "data/automatizacion.xml",
        "views/plantillas_sitio.xml",
        "views/plantillas_listado.xml",
        "views/plantillas_ficha.xml",
        "views/reportes_cotizacion.xml",
        # Al final y sin noupdate: re-aplica la configuración del sitio en cada instalación y actualización.
        "data/aplicar.xml",
    ],
    # El CSS del PDF de cotización va en el bundle de reportes (wkhtmltopdf); todas sus reglas cuelgan de clases bt-*.
    "assets": {"web.report_assets_common": ["brandtrendy_promo_theme/static/src/scss/reporte_cotizacion.scss"]},
    "uninstall_hook": "uninstall_hook",
    "installable": True,
    "application": False,
}
