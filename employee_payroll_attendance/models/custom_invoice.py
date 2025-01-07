from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = "account.move"

    discount = fields.Monetary(
        string="Discount", currency_field="currency_id", default=0.0
    )
    tax_rate = fields.Float(string="Tax Rate", compute="_compute_tax_rate", store=True)
    bank_fee = fields.Monetary(
        string="Bank Fee", currency_field="currency_id", default=0.0
    )

    subtotal = fields.Monetary(
        string="Subtotal",
        compute="_compute_subtotal",
        store=True,
        currency_field="currency_id",
    )
    tax_rate = fields.Monetary(
        string="Tax Rate",
        compute="_compute_tax_rate",
        store=True,
        currency_field="currency_id",
    )

    @api.depends("invoice_line_ids.price_subtotal")
    def _compute_subtotal(self):
        for move in self:
            move.subtotal = sum(line.price_subtotal for line in move.invoice_line_ids)

    @api.depends("subtotal")
    def _compute_tax_rate(self):
        for move in self:
            move.tax_rate = move.subtotal * 0.15  # 15% Tax Rate
