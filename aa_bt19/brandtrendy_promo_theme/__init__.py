from . import controllers
from . import models

PREFIJO = "brandtrendy_promo_theme."


def uninstall_hook(env):
    """Retira solo lo que el módulo creó por función (assets e iconos del sitio y sus marcas).

    Los campos ``x_bt_*`` los declara este módulo: desinstalarlo borra esas columnas con sus datos.
    No se desinstala; ver README.
    """
    env["ir.asset"].with_context(active_test=False).search([("key", "=like", PREFIJO + "%")]).unlink()
    env["ir.ui.view"].with_context(active_test=False).search([("key", "=like", PREFIJO + "sitio_%")]).unlink()
    env["ir.config_parameter"].search([("key", "=like", PREFIJO + "%")]).unlink()
