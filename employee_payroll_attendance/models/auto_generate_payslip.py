from datetime import timedelta
import logging
from odoo import models, fields, api, SUPERUSER_ID
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    @api.model
    def create(self, vals):
        record = super().create(vals)

        if not record:
            return record

        today = fields.Date.today()
        first_day_current_month = today.replace(day=1)
        last_day_current_month = (
            first_day_current_month + relativedelta(months=1)
        ) - timedelta(days=1)

        employee = record.employee_id

        existing_payslip = (
            self.env["hr.payslip"]
            .with_user(SUPERUSER_ID)
            .search(
                [
                    ("employee_id", "=", employee.id),
                    ("date_from", "=", first_day_current_month),
                    ("date_to", "=", last_day_current_month),
                ],
                limit=1,
            )
        )

        if existing_payslip:
            if existing_payslip.status != "done":
                existing_payslip._auto_update_attendance_records()
                existing_payslip._onchange_salary_fields()
                existing_payslip._onchange_bonus_vnd()
                _logger.info(
                    f"Attendances updated for existing payslip {existing_payslip.id} (Employee: {employee.name})"
                )
            else:
                _logger.info(
                    f"Payslip {existing_payslip.id} already finalized. No update applied."
                )
            return record

        # Nếu chưa có payslip, thì thực hiện tạo mới từ tháng trước
        payslip_last_month = (
            self.env["hr.payslip"]
            .with_user(SUPERUSER_ID)
            .search(
                [
                    ("employee_id", "=", employee.id),
                    (
                        "date_from",
                        "=",
                        first_day_current_month - relativedelta(months=1),
                    ),
                    ("date_to", "=", first_day_current_month - timedelta(days=1)),
                ],
                limit=1,
            )
        )

        if payslip_last_month:
            try:
                new_payslip = payslip_last_month.copy(
                    {
                        "date_from": first_day_current_month,
                        "date_to": last_day_current_month,
                        "currency_rate_fallback": payslip_last_month.currency_rate_fallback,
                    }
                )
                new_payslip._auto_update_attendance_records()
                new_payslip._onchange_salary_fields()
                new_payslip._onchange_bonus_vnd()
                _logger.info(
                    f"Payslip duplicated successfully for Employee: {employee.name}"
                )
            except Exception as e:
                _logger.error(
                    f"Error duplicating payslip for Employee ID {employee.id}: {str(e)}"
                )
        else:
            # Create brand new payslip if last month payslip not found
            try:
                new_payslip = self.env["hr.payslip"].create(
                    {
                        "employee_id": employee.id,
                        "date_from": first_day_current_month,
                        "date_to": last_day_current_month,
                    }
                )
                new_payslip._auto_update_attendance_records()
                new_payslip._onchange_salary_fields()
                new_payslip._onchange_bonus_vnd()
                _logger.info(
                    f"New payslip created successfully for Employee: {employee.name}"
                )
            except Exception as e:
                _logger.error(
                    f"Error creating new payslip for Employee ID {employee.id}: {str(e)}"
                )

        return record


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    def duplicate_payslip(self, currency_rate_fallback):
        """
        Duplicate payslip with:
        - New currency rate fallback.
        - Adjusted date for the next month.
        - Ensuring no duplicate payslips exist.
        - Copying attendance records.
        """
        self.ensure_one()

        # Xác định ngày tháng mới
        new_start_date = self.date_from + relativedelta(months=1)
        new_end_date = self.date_to + relativedelta(months=1)

        # Kiểm tra nếu đã có payslip cho tháng kế tiếp
        existing_payslip = (
            self.env["hr.payslip"]
            .with_user(SUPERUSER_ID)
            .search(
                [
                    ("employee_id", "=", self.employee_id.id),
                    ("date_from", "=", new_start_date),
                    ("date_to", "=", new_end_date),
                ],
                limit=1,
            )
        )
        if existing_payslip:
            raise UserError(
                f"Payslip already exists for employee {self.employee_id.name} "
                f"from {new_start_date} to {new_end_date}. Unable to duplicate!"
            )

        # Giá trị sao chép
        copy_values = {
            "date_from": new_start_date,
            "date_to": new_end_date,
            "currency_rate_fallback": currency_rate_fallback,
            "status": "draft",
            "meal_allowance_vnd": 0,
            "kpi_bonus_vnd": 0,
            "other_bonus_vnd": 0,
        }

        if self.include_saturdays:
            copy_values.update(
                {
                    "monthly_wage_vnd": self.monthly_wage_vnd,
                    "rate_lock_field": "monthly_wage_vnd",
                }
            )
        elif self.is_hourly_vnd:
            copy_values.update(
                {
                    "hourly_rate_vnd": self.hourly_rate_vnd,
                    "rate_lock_field": "hourly_rate_vnd",
                }
            )
        elif self.is_hourly_usd:
            copy_values.update(
                {
                    "hourly_rate": self.hourly_rate,
                    "rate_lock_field": "hourly_rate",
                }
            )
        else:
            copy_values.update(
                {
                    "wage": self.wage,
                    "rate_lock_field": "wage",
                }
            )

        # Tạo payslip mới với quyền Superuser
        new_payslip = self.with_user(SUPERUSER_ID).copy(copy_values)

        # Xóa danh sách chấm công cũ
        new_payslip.attendance_line_ids.unlink()

        # Lấy danh sách chấm công phù hợp với tháng mới
        attendances = (
            self.env["hr.attendance"]
            .with_user(SUPERUSER_ID)
            .search(
                [
                    ("employee_id", "=", self.employee_id.id),
                    ("check_in", ">=", new_start_date),
                    ("check_out", "<=", new_end_date),
                ]
            )
        )

        # Thêm chấm công vào phiếu lương mới
        new_payslip.attendance_line_ids = [
            (
                0,
                0,
                {
                    "attendance_id": att.id,
                    "check_in": att.check_in,
                    "check_out": att.check_out,
                    "worked_hours": att.worked_hours,
                    "approved": False,
                },
            )
            for att in attendances
        ]

        # Cập nhật lại thông tin lương và thưởng
        new_payslip._auto_update_attendance_records()
        new_payslip._onchange_salary_fields()
        new_payslip._onchange_bonus_vnd()

        _logger.info(
            f"Payslip successfully duplicated for Employee ID {self.employee_id.id}"
        )
        return new_payslip
