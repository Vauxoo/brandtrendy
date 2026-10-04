# Prueba de upgrade 17 -> 19 (staging). sale_self_invoicing (producto Vauxoo, codigo 17) no es instalable en 19
# y deja la base en estado inconsistente. Se marca 'to remove' para que la carga de modulos lo desinstale
# (paso 5 de odoo.modules.loading). Decision de negocio pendiente: licencia 19 o baja definitiva.
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        "UPDATE ir_module_module SET state = 'to remove' "
        "WHERE name = 'sale_self_invoicing' AND state IN ('installed', 'to upgrade')"
    )
    _logger.info("sale_self_invoicing marcado 'to remove': %s fila(s)", cr.rowcount)
