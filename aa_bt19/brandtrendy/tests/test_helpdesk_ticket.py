from odoo.tests import Form, TransactionCase


class TestHelpdeskTicket(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Test Partner",
            }
        )
        cls.sale_order = cls.env["sale.order"].create(
            {
                "partner_id": cls.partner.id,
            }
        )
        cls.helpdesk_ticket = cls.env["helpdesk.ticket"].create(
            {
                "name": "Test Ticket",
            }
        )

    def test_01_onchange_order(self):
        self.assertFalse(self.helpdesk_ticket.partner_id)
        ticket_form = Form(self.helpdesk_ticket)
        ticket_form.order_id = self.sale_order
        ticket_form.save()
        self.assertEqual(self.helpdesk_ticket.partner_id, self.sale_order.partner_id)
