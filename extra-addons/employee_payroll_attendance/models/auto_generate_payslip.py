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

            # Tìm Payslip chính xác theo employee và đúng tháng trước
            payslip_last = self.env["hr.payslip"].search(
                [
                    ("employee_id", "=", employee.id),
                    ("date_from", "=", first_day_last_month),
                    ("date_to", "=", last_day_last_month),
                ],
                limit=1,
            )

            if payslip_last:
                # Kiểm tra xem payslip đã từng được duplicate chưa
                existing_payslip = self.env["hr.payslip"].search(
                    [
                        ("employee_id", "=", employee.id),
                        ("date_from", "=", today.replace(day=1)),
                        (
                            "date_to",
                            "=",
                            (today.replace(day=1) + timedelta(days=32)).replace(day=1)
                            - timedelta(days=1),
                        ),
                    ],
                    limit=1,
                )

                if not existing_payslip:
                    # Gọi hàm action_duplicate_payslips từ Wizard
                    wizard = self.env["hr.payslip.duplicate.wizard"].create(
                        {"currency_rate_fallback": 1.0}
                    )
                    wizard.with_context(
                        active_ids=[payslip_last.id]
                    ).action_duplicate_payslips()
            else:
                # Nếu không có payslip tháng trước, tạo mới Payslip đơn giản
                self.env["hr.payslip"].create(
                    {
                        "employee_id": employee.id,
                        "date_from": today.replace(day=1),
                        "date_to": (today.replace(day=1) + timedelta(days=32)).replace(
                            day=1
                        )
                        - timedelta(days=1),
                        # "name": f"Payslip for {employee.name} - {today.strftime('%B %Y')}",
                    }
                )
        return records
