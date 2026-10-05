# D6 · en el sitio en modo cotización la búsqueda de productos no busca en la descripción: «termo» no debe traer agendas
# por «termograbado» en su texto. Firmas verificadas contra odoo 19.0 (website_sale/controllers/main.py l.158 y l.214;
# website/controllers/main.py l.620). La caja de la cabecera ya pide products_only (views/plantillas_listado.xml).
from odoo.http import request

from odoo.addons.website.controllers.main import Website
from odoo.addons.website_sale.controllers.main import WebsiteSale


class BtWebsiteSale(WebsiteSale):

    def _get_search_options(self, *args, **kwargs):
        opciones = super()._get_search_options(*args, **kwargs)
        if request.website.bt_quote_mode:
            opciones["displayDescription"] = False
        return opciones

    def _get_shop_domain(self, search, category, attribute_value_dict, search_in_description=True):
        return super()._get_shop_domain(
            search, category, attribute_value_dict,
            search_in_description=search_in_description and not request.website.bt_quote_mode,
        )


class BtWebsite(Website):

    def _get_hybrid_search_options(self, **post):
        opciones = super()._get_hybrid_search_options(**post)
        if request.website.bt_quote_mode:
            opciones["displayDescription"] = False
        return opciones
