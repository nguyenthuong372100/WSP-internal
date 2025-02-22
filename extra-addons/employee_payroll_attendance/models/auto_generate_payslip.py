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

            employee = record.employee_id
            today = fields.Date.today()

            # Xác định ngày đầu và cuối tháng hiện tại
            first_day_current_month = today.replace(day=1)
            last_day_current_month = (
                first_day_current_month + timedelta(days=32)
            ).replace(day=1) - timedelta(days=1)

            # Dùng LOCK để đảm bảo chỉ một payslip được tạo trong transaction
            self.env.cr.execute(
                "SELECT id FROM hr_payslip WHERE employee_id = %s AND date_from = %s AND date_to = %s FOR UPDATE NOWAIT",
                (employee.id, first_day_current_month, last_day_current_month),
            )
            existing_payslip = self.env.cr.fetchone()

            _logger.info(
                f"Checking payslip for {employee.name} ({employee.id}) - Found: {bool(existing_payslip)}"
            )

            if existing_payslip or employee.id in employees_to_process:
                continue  # Bỏ qua nếu payslip đã tồn tại hoặc đã được xử lý

            employees_to_process.add(employee.id)

        # Tạo payslip sau khi quét toàn bộ attendance
        for employee_id in employees_to_process:
            employee = self.env["hr.employee"].browse(employee_id)

            first_day_last_month = (
                first_day_current_month - timedelta(days=1)
            ).replace(day=1)
            last_day_last_month = (first_day_last_month + timedelta(days=32)).replace(
                day=1
            ) - timedelta(days=1)

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
                    f"Duplicating payslip for {employee.name} ({employee.id}) from {first_day_last_month} to {last_day_last_month}"
                )
                wizard = self.env["hr.payslip.duplicate.wizard"].create(
                    {"currency_rate_fallback": payslip_last.currency_rate_fallback}
                )
                wizard.with_context(
                    active_ids=[payslip_last.id]
                ).action_duplicate_payslips()
            else:
                _logger.info(
                    f"Creating new payslip for {employee.name} ({employee.id}) for {first_day_current_month} to {last_day_current_month}"
                )
                self.env["hr.payslip"].sudo().create(
                    {
                        "employee_id": employee.id,
                        "date_from": first_day_current_month,
                        "date_to": last_day_current_month,
                    }
                )

        return records
