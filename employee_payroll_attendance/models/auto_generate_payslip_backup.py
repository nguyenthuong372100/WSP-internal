from datetime import timedelta
from odoo import models, fields, api


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            employee = record.employee_id
            today = fields.Date.today()

            # Tính ngày đầu và cuối tháng trước
            first_day_last_month = (today.replace(day=1) - timedelta(days=1)).replace(
                day=1
            )
            last_day_last_month = (first_day_last_month + timedelta(days=32)).replace(
                day=1
            ) - timedelta(days=1)

            # Kiểm tra xem đã có payslip tháng này chưa
            first_day_current_month = today.replace(day=1)
            last_day_current_month = (
                first_day_current_month + timedelta(days=32)
            ).replace(day=1) - timedelta(days=1)

            existing_payslip = (
                self.env["hr.payslip"]
                .sudo()
                .search(
                    [
                        ("employee_id", "=", employee.id),
                        ("date_from", "=", first_day_current_month),
                        ("date_to", "=", last_day_current_month),
                    ],
                    limit=1,
                )
            )

            if not existing_payslip:
                # Tìm Payslip chính xác của tháng trước
                payslip_last = (
                    self.env["hr.payslip"]
                    .sudo()
                    .search(
                        [
                            ("employee_id", "=", employee.id),
                            ("date_from", "=", first_day_last_month),
                            ("date_to", "=", last_day_last_month),
                        ],
                        limit=1,
                    )
                )

                if payslip_last:
                    # Nếu có payslip tháng trước, gọi wizard để duplicate
                    wizard = (
                        self.env["hr.payslip.duplicate.wizard"]
                        .sudo()
                        .create({"currency_rate_fallback": 1.0})
                    )
                    wizard.with_context(
                        active_ids=[payslip_last.id]
                    ).action_duplicate_payslips()
                else:
                    # Nếu không có payslip tháng trước, tạo mới Payslip đơn giản
                    self.env["hr.payslip"].create(
                        {
                            "employee_id": employee.id,
                            "date_from": first_day_current_month,
                            "date_to": last_day_current_month,
                        }
                    )
            # Nếu payslip đã tồn tại, chỉ cho phép ghi nhận chấm công mà không tạo payslip mới
            else:
                continue
        return records
