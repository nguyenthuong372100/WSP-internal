from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):

    _inherit = "account.move"

    discount = fields.Monetary(
        string="Discount", currency_field="currency_id", default=0.0
    )
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
    amount_residual = fields.Float(
        string="Amount Residual",
        compute="_compute_amount_residual",
        store=True,
        currency_field="currency_id",
    )

    @api.depends("invoice_line_ids.price_subtotal")
    def _compute_subtotal(self):
        for move in self:
            try:
                move.subtotal = sum(
                    line.price_subtotal or 0.0 for line in move.invoice_line_ids
                )
            except Exception as e:
                _logger.error(
                    f"[AccountMove ID {move.id}] Error computing subtotal: {e}"
                )
                move.subtotal = 0.0

    @api.depends("subtotal")
    def _compute_tax_rate(self):
        for move in self:
            try:
                move.tax_rate = (move.subtotal or 0.0) * 0.15
            except Exception as e:
                _logger.error(
                    f"[AccountMove ID {move.id}] Error computing tax rate: {e}"
                )
                move.tax_rate = 0.0

    @api.depends("discount", "bank_fee")
    def _compute_amount_residual(self):
        for move in self:
            move.amount_residual = (
                move.amount_untaxed + move.tax_rate - move.discount + move.bank_fee
            )
