from odoo import fields, models


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    doc_number = fields.Char(string="Document number", help="Field used to refer to the transaction number")
    concept = fields.Char(
        help="Field used to hold the transaction concept, for example: Commission, sale, discount, etc."
    )
