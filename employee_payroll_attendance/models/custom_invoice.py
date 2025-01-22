from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    # Các trường tiền tệ (Monetary fields)
    discount = fields.Monetary(
        string="Discount",
        currency_field="currency_id",
        default=0.0,
        store=True,
        copy=True,  # Đảm bảo giá trị được copy khi duplicate
    )

    bank_fee = fields.Monetary(
        string="Bank Fee",
        currency_field="currency_id",
        default=0.0,
        store=True,
        copy=True,
    )
    custom_amount_residual = fields.Monetary(
        string="Amount Residual",  # Đổi tên hiển thị để tránh nhầm lẫn
        compute="_compute_custom_amount_residual",
        store=True,
        currency_field="currency_id",
        help="Amount due including custom discount and bank fees",
    )
    subtotal = fields.Monetary(
        string="Subtotal",  # Tên hiển thị
        compute="_compute_subtotal",  # Hàm tính toán giá trị
        store=True,
        readonly=True,
    )
    tax_rate = fields.Monetary(
        string="Tax Rate",
        compute="_compute_tax_rate",
        store=True,
        currency_field="currency_id",
    )
    amount_residual = fields.Monetary(  # Đổi từ Float sang Monetary
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

    # Trường quan hệ nhiều-nhiều với thuế
    tax_ids = fields.Many2many(
        "account.tax",
        string="Taxes",
        domain=["|", ("active", "=", False), ("active", "=", True)],
        help="Các loại thuế áp dụng trên số tiền cơ bản",
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

    # Trường trạng thái
    state = fields.Selection(
        string="State",
        required=True,
        readonly=True,
        default="draft",
        tracking=True,  # Theo dõi thay đổi
    )

    @api.depends("invoice_line_ids.price_subtotal")
    def _compute_subtotal(self):
        """Tính tổng phụ từ các dòng hóa đơn"""
        for move in self:
            try:
                move.subtotal = sum(
                    line.price_subtotal or 0.0 for line in move.invoice_line_ids
                )
            except Exception as e:
                _logger.error(f"[AccountMove ID {move.id}] Lỗi khi tính tổng phụ: {e}")
                move.subtotal = 0.0

    @api.depends("invoice_line_ids.price_subtotal")
    def _compute_amount_untaxed(self):
        """Tính số tiền chưa thuế"""
        for move in self:
            try:
                move.amount_untaxed = sum(
                    line.price_subtotal or 0.0 for line in move.invoice_line_ids
                )
            except Exception as e:
                _logger.error(
                    f"[AccountMove ID {move.id}] Lỗi khi tính số tiền chưa thuế: {e}"
                )
                move.amount_untaxed = 0.0

    @api.depends("subtotal", "invoice_line_ids.tax_ids")
    def _compute_tax_rate(self):
        """Tính thuế suất dựa trên các loại thuế áp dụng"""
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
                _logger.error(f"[AccountMove ID {move.id}] Lỗi khi tính thuế suất: {e}")
                move.tax_rate = 0.0

    @api.depends("discount", "bank_fee", "subtotal", "tax_rate")
    def _compute_amount_residual(self):
        """Tính số tiền còn lại sau khi trừ chiết khấu và cộng phí"""
        for move in self:
            try:
                move.amount_residual = (
                    move.subtotal + move.tax_rate - move.discount + move.bank_fee
                )
            except Exception as e:
                _logger.error(
                    f"[AccountMove ID {move.id}] Lỗi khi tính số tiền còn lại: {e}"
                )
                move.amount_residual = 0.0

    @api.depends("subtotal", "discount")
    def _compute_subtotal_less_discount(self):
        """Tính tổng phụ sau khi trừ chiết khấu"""
        for move in self:
            try:
                move.subtotal_less_discount = move.subtotal - (move.discount or 0.0)
            except Exception as e:
                _logger.error(
                    f"[AccountMove ID {move.id}] Lỗi khi tính tổng phụ sau chiết khấu: {e}"
                )
                move.subtotal_less_discount = 0.0

    @api.depends(
        "discount", "bank_fee", "subtotal", "tax_rate", "state", "amount_residual"
    )
    def _compute_custom_amount_residual(self):
        for move in self:
            if move.state == "draft":
                # Trong trạng thái draft, tính theo logic tùy chỉnh
                move.custom_amount_residual = (
                    move.subtotal + move.tax_rate - move.discount + move.bank_fee
                )
            else:
                # Trong các trạng thái khác, sử dụng amount_residual của Odoo
                # nhưng vẫn áp dụng discount và bank fee
                standard_residual = move.amount_residual
                move.custom_amount_residual = (
                    standard_residual - move.discount + move.bank_fee
                )

    # Theo dõi sự thay đổi của các trường discount và bank_fee
    def write(self, vals):
        for record in self:
            # Kiểm tra nếu discount hoặc bank_fee được thay đổi
            discount_changed = (
                "discount" in vals and vals["discount"] != record.discount
            )
            bank_fee_changed = (
                "bank_fee" in vals and vals["bank_fee"] != record.bank_fee
            )

            if discount_changed:
                record.preserved_discount = vals["discount"]
                _logger.info(
                    f"[AccountMove ID {record.id}] Discount updated to {vals['discount']}, preserved value updated."
                )

            if bank_fee_changed:
                record.preserved_bank_fee = vals["bank_fee"]
                _logger.info(
                    f"[AccountMove ID {record.id}] Bank Fee updated to {vals['bank_fee']}, preserved value updated."
                )

        # Gọi phương thức write gốc để lưu thay đổi
        return super(AccountMove, self).write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        records = super(AccountMove, self).create(vals_list)
        for record in records:
            # Khi tạo mới, lưu giá trị khởi tạo vào các trường preserved
            record.preserved_discount = record.discount
            record.preserved_bank_fee = record.bank_fee
            _logger.info(
                f"[AccountMove ID {record.id}] Created with discount={record.discount}, bank_fee={record.bank_fee}."
            )
        return records

    def _update_custom_amounts(self):
        """Cập nhật giá trị tùy chỉnh khi chuyển trạng thái"""
        self.ensure_one()
        # Lưu giá trị hiện tại vào các trường riêng
        self.preserved_discount = self.discount
        self.preserved_bank_fee = self.bank_fee
        _logger.info(
            f"[AccountMove ID {self.id}] State changed. Preserved discount={self.discount}, bank_fee={self.bank_fee}"
        )

    @api.onchange("discount", "invoice_line_ids", "bank_fee", "tax_rate", "state")
    def _onchange_amount_total(self):
        """Cập nhật lại các trường tính toán khi có thay đổi"""
        self._compute_subtotal()
        self._compute_subtotal_less_discount()
        self._compute_amount_residual()
