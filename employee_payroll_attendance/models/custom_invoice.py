from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = "account.move"

    discount = fields.Monetary(
        string="Discount",
        currency_field="currency_id",
        help="Enter the discount amount to apply on this invoice.",
        default=0.0,
    )
    tax_rate = fields.Float(string="Tax Rate", compute="_compute_tax_rate", store=True)
    bank_fee = fields.Monetary(
        string="Bank Fee", currency_field="currency_id", default=0.0
    )

    @api.depends("amount_tax", "amount_total")
    def _compute_tax_rate(self):
        for move in self:
            move.tax_rate = (
                (move.amount_tax / move.amount_total) * 100
                if move.amount_total
                else 0.0
            )
