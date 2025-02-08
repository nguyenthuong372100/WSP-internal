from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = "account.move"

    # Monetary fields
    discount = fields.Monetary(
        string="Discount",
        currency_field="currency_id",
        default=0.0,
        store=True,
        copy=True,  # Make sure the value is copied when duplicating
    )

    bank_fee = fields.Monetary(
        string="Bank Fee",
        currency_field="currency_id",
        default=0.0,
        store=True,
        copy=True,
    )

    custom_amount_residual = fields.Monetary(
        string="Amount Residual",
        compute="_compute_custom_amount_residual",
        store=True,
        currency_field="currency_id",
        help="Amount due including custom discount and bank fees",
    )

    subtotal = fields.Monetary(
        string="Subtotal",  # Display name
        compute="_compute_subtotal",  # Computation method
        store=True,
        readonly=True,
    )

    tax_rate = fields.Monetary(
        string="Tax Rate",
        compute="_compute_tax_rate",
        store=True,
        currency_field="currency_id",
    )

    amount_residual = fields.Monetary(  # Change from Float to Monetary
        string="Amount Residual",
        compute="_compute_amount_residual",
        store=True,
        currency_field="currency_id",
    )

    amount_untaxed = fields.Monetary(
        string="Amount Untaxed",
        compute="_compute_amount_untaxed",
        store=True,
        currency_field="currency_id",
    )

    subtotal_less_discount = fields.Monetary(
        string="Subtotal Less Discount",
        compute="_compute_subtotal_less_discount",
        store=True,
        readonly=True,
    )

    # Many2many field with taxes
    tax_ids = fields.Many2many(
        "account.tax",
        string="Taxes",
        domain=["|", ("active", "=", False), ("active", "=", True)],
        help="Taxes applied on the total amount",
    )

    preserved_discount = fields.Monetary(
        string="Preserved Discount",
        readonly=True,
        currency_field="currency_id",
    )

    preserved_bank_fee = fields.Monetary(
        string="Preserved Bank Fee",
        readonly=True,
        currency_field="currency_id",
    )

    # State field
    state = fields.Selection(
        string="State",
        required=True,
        readonly=True,
        default="draft",
        tracking=True,  # Track changes
    )

    @api.depends("invoice_line_ids.price_subtotal")
    def _compute_subtotal(self):
        """Compute subtotal from invoice lines"""
        for move in self:
            try:
                move.subtotal = sum(
                    line.price_subtotal or 0.0 for line in move.invoice_line_ids
                )
            except Exception as e:
                move.subtotal = 0.0

    @api.depends("invoice_line_ids.price_subtotal")
    def _compute_amount_untaxed(self):
        """Compute amount untaxed"""
        for move in self:
            try:
                move.amount_untaxed = sum(
                    line.price_subtotal or 0.0 for line in move.invoice_line_ids
                )
            except Exception as e:
                move.amount_untaxed = 0.0

    @api.depends("subtotal", "invoice_line_ids.tax_ids")
    def _compute_tax_rate(self):
        """Compute tax rate based on taxes applied"""
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
                move.tax_rate = 0.0

    @api.depends("discount", "bank_fee", "subtotal", "tax_rate")
    def _compute_amount_residual(self):
        """Compute amount residual after applying custom discount and bank fees"""
        for move in self:
            try:
                move.amount_residual = (
                    move.subtotal + move.tax_rate - move.discount + move.bank_fee
                )
            except Exception as e:
                move.amount_residual = 0.0

    @api.depends("subtotal", "discount")
    def _compute_subtotal_less_discount(self):
        """Compute subtotal less discount"""
        for move in self:
            try:
                move.subtotal_less_discount = move.subtotal - (move.discount or 0.0)
            except Exception as e:
                move.subtotal_less_discount = 0.0

    @api.depends(
        "discount", "bank_fee", "subtotal", "tax_rate", "state", "amount_residual"
    )
    def _compute_custom_amount_residual(self):
        for move in self:
            if move.state == "draft":
                # In draft state, compute using custom logic
                move.custom_amount_residual = (
                    move.subtotal + move.tax_rate - move.discount + move.bank_fee
                )
            else:
                # In other states, use Odoo's amount_residual
                # but apply custom discount and bank fee
                standard_residual = move.amount_residual
                move.custom_amount_residual = (
                    standard_residual - move.discount + move.bank_fee
                )

    # Track changes to discount and bank_fee
    def write(self, vals):
        for record in self:
            # Check if discount or bank_fee changed
            discount_changed = (
                "discount" in vals and vals["discount"] != record.discount
            )
            bank_fee_changed = (
                "bank_fee" in vals and vals["bank_fee"] != record.bank_fee
            )

            if discount_changed:
                record.preserved_discount = vals["discount"]

            if bank_fee_changed:
                record.preserved_bank_fee = vals["bank_fee"]

        # Call original write method to save changes
        return super(AccountMove, self).write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        records = super(AccountMove, self).create(vals_list)
        for record in records:
            # When creating, store initial values in preserved fields
            record.preserved_discount = record.discount
            record.preserved_bank_fee = record.bank_fee
        return records

    def _update_custom_amounts(self):
        """Update custom amounts when state changes"""
        self.ensure_one()
        # Store current values in preserved fields
        self.preserved_discount = self.discount
        self.preserved_bank_fee = self.bank_fee

    @api.onchange("discount", "invoice_line_ids", "bank_fee", "tax_rate", "state")
    def _onchange_amount_total(self):
        """Update custom amounts when related fields change"""
        self._compute_subtotal()
        self._compute_subtotal_less_discount()
        self._compute_amount_residual()
