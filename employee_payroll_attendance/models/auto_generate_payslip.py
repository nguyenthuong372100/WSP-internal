from datetime import timedelta
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        employees_to_process = set()

        if not records:
            return records  # Không làm gì nếu không có attendance

        for record in records:
            if not record.employee_id:
                _logger.warning("Skipping attendance with missing employee_id")
                continue

            employee = record.employee_id.sudo()
            today = fields.Date.today()

            # Xác định ngày đầu và cuối tháng hiện tại
            first_day_current_month = today.replace(day=1)
            last_day_current_month = (
                first_day_current_month + timedelta(days=32)
            ).replace(day=1) - timedelta(days=1)

            # Dùng LOCK để đảm bảo chỉ một payslip được tạo trong transaction
            self.env.cr.execute(
                """
                SELECT id FROM hr_payslip 
                WHERE employee_id = %s AND date_from = %s AND date_to = %s 
                FOR UPDATE NOWAIT
                """,
                (employee.id, first_day_current_month, last_day_current_month),
            )
            existing_payslip = self.env.cr.fetchone()

            _logger.info(
                f"Payslip check for Employee ID {employee.id} - Found: {bool(existing_payslip)}"
            )

            if existing_payslip or employee.id in employees_to_process:
                continue  # Bỏ qua nếu payslip đã tồn tại hoặc đã được xử lý

            employees_to_process.add(employee.id)

        # Tạo payslip sau khi quét toàn bộ attendance
        for employee_id in employees_to_process:
            employee = self.env["hr.employee"].sudo().browse(employee_id)

            first_day_last_month = (
                first_day_current_month - timedelta(days=1)
            ).replace(day=1)
            last_day_last_month = (first_day_last_month + timedelta(days=32)).replace(
                day=1
            ) - timedelta(days=1)

            # Tìm payslip của tháng trước bằng sudo
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
                _logger.info(
                    f"Found last month payslip for Employee ID {employee.id}, attempting to duplicate..."
                )

                try:
                    # Kiểm tra nếu wizard duplicate tồn tại
                    wizard_model = self.env["hr.payslip.duplicate.wizard"].sudo()
                    if not wizard_model:
                        _logger.error("Payslip duplicate wizard model not found!")
                        continue

                    # Tạo wizard duplicate payslip với sudo
                    wizard = wizard_model.create(
                        {
                            "currency_rate_fallback": payslip_last.sudo().currency_rate_fallback
                        }
                    )

                    # Kiểm tra xem wizard có thực sự được tạo không
                    if not wizard:
                        _logger.error(
                            f"Failed to create duplicate wizard for Employee ID {employee.id}"
                        )
                        continue

                    # **Chạy action duplicate với quyền sudo**
                    context = {
                        "active_ids": [payslip_last.id],
                        "active_id": payslip_last.id,
                        "active_model": "hr.payslip",
                    }
                    wizard.with_context(**context).sudo().action_duplicate_payslips()
                    _logger.info(
                        f"✅ Successfully duplicated payslip for Employee ID {employee.id}"
                    )

                except Exception as e:
                    _logger.error(
                        f"❌ Error duplicating payslip for Employee ID {employee.id}: {str(e)}"
                    )
            else:
                _logger.info(
                    f"No previous payslip found for Employee ID {employee.id}, creating new payslip."
                )

                # Tạo mới payslip với quyền sudo
                self.env["hr.payslip"].sudo().create(
                    {
                        "employee_id": employee.id,
                        "date_from": first_day_current_month,
                        "date_to": last_day_current_month,
                    }
                )

        return records
