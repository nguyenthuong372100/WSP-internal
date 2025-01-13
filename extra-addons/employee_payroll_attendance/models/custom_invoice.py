from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    discount = fields.Monetary( string="Discount", currency_field="currency_id", default=0.0
    )
    bank_fee = fields.Monetary( string="Bank Fee", currency_field="currency_id", default=0.0
    )
    subtotal = fields.Monetary( string="Subtotal", compute="_compute_subtotal", store=True, currency_field="currency_id",
    )
    tax_rate = fields.Monetary( string="Tax Rate", compute="_compute_tax_rate", store=True, currency_field="currency_id",
    )
    amount_residual = fields.Float( string="Amount Residual", compute="_compute_amount_residual", store=True, currency_field="currency_id",
    )
    tax_ids = fields.Many2many(
        "account.tax", string="Taxes", domain=["|", ("active", "=", False), ("active", "=", True)], help="Taxes that apply on the base amount",
    )
    amount_untaxed = fields.Monetary( string="Untaxed Amount", compute="_compute_amount_untaxed", store=True, currency_field="currency_id",
    )
    subtotal_minus_discount = fields.Monetary( string="Subtotal Minus Discount", compute="_compute_subtotal_minus_discount", store=True, currency_field="currency_id",
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

    @api.depends("invoice_line_ids.price_subtotal")
    def _compute_amount_untaxed(self):
        for move in self:
            move.amount_untaxed = sum(
                line.price_subtotal or 0.0 for line in move.invoice_line_ids
            )

    @api.depends("subtotal", "invoice_line_ids.tax_ids")
    def _compute_tax_rate(self):
        for move in self:
            try:
                if not move.invoice_line_ids.mapped("tax_ids"):
                    move.tax_rate = 0.0
                else:
                    total_tax = sum(
                        line.price_subtotal
                        * sum(tax.amount / 100 for tax in line.tax_ids)
                        for line in move.invoice_line_ids
                    )
                    move.tax_rate = total_tax
            except Exception as e:
                _logger.error(
                    f"[AccountMove ID {move.id}] Error computing tax rate: {e}"
                )
                move.tax_rate = 0.0

    @api.depends("discount", "bank_fee", "subtotal", "tax_rate")
    def _compute_amount_residual(self):
        for move in self:
            move.amount_residual = (
                move.subtotal + move.tax_rate - move.discount + move.bank_fee
            )

    @api.depends("amount_untaxed", "discount")
    def _compute_subtotal_minus_discount(self):
        for move in self:
            move.subtotal_minus_discount = move.amount_untaxed - (move.discount or 0.0)

    @api.onchange("amount_untaxed", "discount")
    def _onchange_amount_untaxed_discount(self):
        self._compute_subtotal_minus_discount()
