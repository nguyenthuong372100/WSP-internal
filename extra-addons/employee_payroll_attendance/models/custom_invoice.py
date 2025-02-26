from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = "account.move"

    bank_fee = fields.Monetary(
        string="Bank Fee",
        currency_field="currency_id",
        default=0.0,
        store=True,
        copy=True,
    )
    # Subtotal (Tổng phụ)
    subtotal = fields.Monetary(
        string="Subtotal",
        compute="_compute_subtotal",
        store=True,
        readonly=True,
    )

    # Thuế
    tax_rate = fields.Monetary(
        string="Tax Rate",
        compute="_compute_tax_rate",
        store=True,
        currency_field="currency_id",
    )

    # Tổng tiền chưa có thuế
    amount_untaxed = fields.Monetary(
        string="Amount Untaxed",
        compute="_compute_amount_untaxed",
        store=True,
        currency_field="currency_id",
    )

    # Tính Subtotal từ các dòng hóa đơn
    @api.depends("invoice_line_ids.price_subtotal")
    def _compute_subtotal(self):
        for move in self:
            move.subtotal = sum(
                line.price_subtotal or 0.0 for line in move.invoice_line_ids
            )

    # Tính tổng tiền chưa có thuế (thực ra có thể dùng luôn subtotal)
    @api.depends("invoice_line_ids.price_subtotal")
    def _compute_amount_untaxed(self):
        for move in self:
            move.amount_untaxed = move.subtotal

    # Tính tổng thuế dựa trên dòng hóa đơn
    @api.depends("subtotal", "invoice_line_ids.tax_ids")
    def _compute_tax_rate(self):
        for move in self:
            move.tax_rate = (
                sum(
                    line.price_subtotal * sum(tax.amount / 100 for tax in line.tax_ids)
                    for line in move.invoice_line_ids
                    if line.tax_ids
                )
                if move.invoice_line_ids
                else 0.0
            )

    @api.model_create_multi
    def create(self, vals_list):
        records = super(AccountMove, self).create(vals_list)
        for record in records:
            if record.bank_fee and record.bank_fee > 0:
                account_id = record.journal_id.default_account_id.id
                if not account_id:
                    raise ValueError(
                        "Không tìm thấy tài khoản kế toán hợp lệ cho Bank Fee."
                    )

                self.env["account.move.line"].create(
                    {
                        "move_id": record.id,
                        "name": "Bank Fee",
                        "quantity": 1,
                        "price_unit": record.bank_fee,
                        "account_id": account_id,  # Đảm bảo tài khoản hợp lệ
                        "credit": record.bank_fee,  # Tăng tổng tiền phải thu
                        "debit": 0.00,
                        "partner_id": record.partner_id.id,  # Đối tác phải có
                        "company_id": record.company_id.id,
                        "currency_id": record.currency_id.id,
                        "date": record.invoice_date,
                        "tax_ids": [(6, 0, [])],  # Không áp thuế
                    }
                )
        return records

    def write(self, vals):
        res = super(AccountMove, self).write(vals)
        for record in self:
            if "bank_fee" in vals and vals["bank_fee"] > 0:
                existing_fee_line = record.invoice_line_ids.filtered(
                    lambda l: l.name == "Bank Fee"
                )
                account_id = record.journal_id.default_account_id.id
                if not account_id:
                    raise ValueError(
                        "Không tìm thấy tài khoản kế toán hợp lệ cho Bank Fee."
                    )

                if existing_fee_line:
                    existing_fee_line.write({"price_unit": vals["bank_fee"]})
                else:
                    self.env["account.move.line"].create(
                        {
                            "move_id": record.id,
                            "name": "Bank Fee",
                            "quantity": 1,
                            "price_unit": vals["bank_fee"],
                            "account_id": account_id,
                            "credit": vals["bank_fee"],
                            "debit": 0.00,
                            "tax_ids": [(5, 0, 0)],  # Xóa thuế
                            "partner_id": record.partner_id.id,
                            "company_id": record.company_id.id,
                            "currency_id": record.currency_id.id,
                            "date": record.invoice_date,
                        }
                    )
        return res
