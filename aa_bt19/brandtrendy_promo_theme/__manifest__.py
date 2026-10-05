{
    "name": "Brandtrendy · Promocionales (sitio de cotización)",
    "summary": "Reproduce el sitio «Promocionales Brandtrendy» sobre el estándar de Odoo 19: "
    "configuración, tema del sitio, pasos de cotización y solicitud ligada a su lead en servidor.",
    "author": "Brandtrendy",
    "website": "https://promocionales.brandtrendy.com.mx",
    "license": "LGPL-3",
    "category": "Website/Website",
    "version": "19.0.1.0.0",
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
        # Al final y sin noupdate: re-aplica la configuración del sitio en cada instalación y actualización.
        "data/aplicar.xml",
    ],
    "uninstall_hook": "uninstall_hook",
    "installable": True,
    "application": False,
}
