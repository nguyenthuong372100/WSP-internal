from datetime import timedelta
import logging
from odoo import models, fields, api
from odoo import SUPERUSER_ID
from dateutil.relativedelta import relativedelta

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

            _logger.info(
                f"Checking existing payslip for Employee ID {employee.id} "
                f"from {first_day_current_month} to {last_day_current_month}"
            )

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
                f"Payslip exists for Employee ID {employee.id}: {bool(existing_payslip)}"
            )

            if existing_payslip or employee.id in employees_to_process:
                _logger.info(
                    f"Skipping Employee ID {employee.id} as payslip already exists or already processed."
                )
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

            _logger.info(
                f"Searching for previous payslip of Employee ID {employee.id} "
                f"from {first_day_last_month} to {last_day_last_month}"
            )

            # Truy vấn payslip tháng trước bằng quyền Superuser
            payslip_last = (
                self.env["hr.payslip"]
                .with_user(SUPERUSER_ID)
                .search(
                    [
                        ("employee_id", "=", employee.id),
                        ("date_from", "=", first_day_last_month),
                        ("date_to", "=", last_day_last_month),
                    ],
                    limit=1,
                )
            )

            _logger.info(
                f"Previous payslip found for Employee ID {employee.id}: {payslip_last.ids if payslip_last else 'None'}"
            )

            if payslip_last:
                _logger.info(
                    f"Attempting to duplicate payslip for Employee ID {employee.id}"
                )

                try:
                    # Kiểm tra nếu wizard duplicate tồn tại
                    wizard_model = self.env["hr.payslip.duplicate.wizard"].with_user(
                        SUPERUSER_ID
                    )
                    if not wizard_model:
                        _logger.error("Payslip duplicate wizard model not found!")
                        continue

                    _logger.info(
                        f"Creating duplicate wizard for Employee ID {employee.id}"
                    )

                    # Tạo wizard duplicate payslip
                    wizard = wizard_model.create(
                        {
                            "currency_rate_fallback": payslip_last.sudo().currency_rate_fallback
                        }
                    )

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
                    _logger.info(
                        f"Executing payslip duplication for Employee ID {employee.id}"
                    )

                    wizard.with_context(**context).sudo().action_duplicate_payslips()
                    _logger.info(
                        f"Payslip successfully duplicated for Employee ID {employee.id}"
                    )

                except Exception as e:
                    _logger.error(
                        f"Error duplicating payslip for Employee ID {employee.id}: {str(e)}"
                    )
            else:
                _logger.info(
                    f"No previous payslip found for Employee ID {employee.id}, creating new payslip."
                )

                # Tạo mới payslip với quyền sudo
                new_payslip = (
                    self.env["hr.payslip"]
                    .sudo()
                    .create(
                        {
                            "employee_id": employee.id,
                            "date_from": first_day_current_month,
                            "date_to": last_day_current_month,
                        }
                    )
                )
                if new_payslip:
                    _logger.info(
                        f"Successfully created new payslip for Employee ID {employee.id}"
                    )
                else:
                    _logger.error(
                        f"Failed to create new payslip for Employee ID {employee.id}"
                    )

        return records


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    def duplicate_payslip(self, currency_rate_fallback):
        """
        Duplicate the payslip while:
        - Updating currency_rate_fallback.
        - Setting new dates for the next month.
        - Avoiding duplicate payslips for the same employee and period.
        - Attaching attendance records.
        """
        self.ensure_one()  # Chỉ thực hiện trên một payslip

        # Tính ngày mới (tháng tiếp theo)
        new_start_date = self.date_from + relativedelta(months=1)
        new_end_date = self.date_to + relativedelta(months=1)

        # Kiểm tra nếu đã có phiếu lương cho tháng kế tiếp
        existing_payslip = self.env["hr.payslip"].search(
            [
                ("employee_id", "=", self.employee_id.id),
                ("date_from", "=", new_start_date),
                ("date_to", "=", new_end_date),
            ],
            limit=1,
        )
        if existing_payslip:
            raise UserError(
                f"Payslip already exists for employee {self.employee_id.name} "
                f"from {new_start_date} to {new_end_date}. Unable to duplicate!"
            )

        # Sao chép phiếu lương với dữ liệu thích hợp
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

        # Tạo payslip mới
        new_payslip = self.sudo().copy(copy_values)

        # Xóa danh sách chấm công cũ
        new_payslip.attendance_line_ids.unlink()

        # Lấy danh sách chấm công phù hợp với tháng mới
        attendances = self.env["hr.attendance"].search(
            [
                ("employee_id", "=", self.employee_id.id),
                ("check_in", ">=", new_start_date),
                ("check_out", "<=", new_end_date),
            ]
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

        return new_payslip
