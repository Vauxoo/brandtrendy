import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import column_exists

_logger = logging.getLogger(__name__)


DEPRECATED_FIELDS = [
    ("x_studio_date_field_fefil", "product.product"),
    ("x_studio_date_field_wFPvj", "product.product"),
    ("x_studio_binary_field_elCGq", "product.product"),
    ("x_studio_datetime_field_R24zu", "product.product"),
]


def migrate(cr, version):
    if not version:
        return
    delete_studio_fields(cr)


def delete_studio_fields(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for field in DEPRECATED_FIELDS:
        model = env[field[1]]
        old_field_name = field[0]
        views = env["ir.ui.view"].search([("arch_db", "like", old_field_name)])
        for view in views:
            view.write({"active": False})
        if column_exists(cr, model._table, old_field_name):
            field_orm = model._fields[old_field_name]
            field_id = env["ir.model.fields"]._get(field_orm.model_name, field_orm.name)
            query = "UPDATE ir_model_fields set state = 'manual' WHERE id = %s;"
            env.cr.execute(query, [field_id.id])
            field_id.unlink()
