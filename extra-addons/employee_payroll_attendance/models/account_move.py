from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    # ...existing code...

    subtotal_minus_discount = fields.Monetary(
        string='Subtotal Minus Discount',
        compute='_compute_subtotal_minus_discount',
        store=True,
        currency_field='currency_id'
    )

    @api.depends('amount_untaxed', 'discount')
    def _compute_subtotal_minus_discount(self):
        for move in self:
            move.subtotal_minus_discount = move.amount_untaxed - (move.discount or 0.0)
