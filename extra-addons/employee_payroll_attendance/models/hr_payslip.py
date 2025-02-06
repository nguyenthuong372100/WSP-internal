from odoo import models, fields, api
import logging
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    worked_hours = fields.Float(string="Total Worked Hours", readonly=True)
    attendance_line_ids = fields.One2many(
        "hr.payslip.attendance", "payslip_id", string="Attendance Records", copy=False
    )
    approved_by = fields.Many2one("res.users", string="Approved By", readonly=True)

    def _compute_total_worked_hours(self):
        """
        Calculate total worked hours from approved attendance records.
        """
        for payslip in self:
            total_hours = sum(
                line.worked_hours
                for line in payslip.attendance_line_ids
                if line.approved
            )
            payslip.worked_hours = total_hours

    @api.onchange("employee_id", "date_from", "date_to")
    def _onchange_attendance_records(self):
        if not self.employee_id or not self.date_from or not self.date_to:
            return  # Do nothing if any of the fields are missing

        # Get attendance records that match the employee and date range
        attendances = self.env["hr.attendance"].search(
            [
                ("employee_id", "=", self.employee_id.id),
                ("check_in", ">=", self.date_from),
                ("check_out", "<=", self.date_to),
            ]
        )

        # Find the IDs of attendance records that already exist
        existing_attendance_ids = set(
            self.attendance_line_ids.mapped("attendance_id.id")
        )

        # Remove any records that are no longer in the date range
        self.attendance_line_ids = self.attendance_line_ids.filtered(
            lambda line: line.attendance_id.id in attendances.mapped("id")
        )

        # Add new records
        for attendance in attendances:
            if attendance.id not in existing_attendance_ids:
                self.attendance_line_ids = [
                    (
                        0,
                        0,
                        {
                            "attendance_id": attendance.id,
                            "check_in": attendance.check_in,
                            "check_out": attendance.check_out,
                            "worked_hours": attendance.worked_hours,
                            "approved": False,
                        },
                    )
                ]

    def _sync_attendance_records(self):
        """
        Sync attendance records with payslip without creating duplicates.
        Avoid syncing 'approved' status from other payslips.
        """
        for payslip in self:
            if not payslip.employee_id or not payslip.date_from or not payslip.date_to:
                continue  # Skip if any required fields are missing

            # Get attendance records that match the employee and date range
            attendances = self.env["hr.attendance"].search(
                [
                    ("employee_id", "=", payslip.employee_id.id),
                    ("check_in", ">=", payslip.date_from),
                    ("check_out", "<=", payslip.date_to),
                ]
            )

            # Remove any records that are no longer in the date range
            payslip.attendance_line_ids.filtered(
                lambda line: line.attendance_id.id not in attendances.mapped("id")
            ).unlink()

            # Add new attendance records without syncing 'approved' status
            existing_attendance_ids = set(
                payslip.attendance_line_ids.mapped("attendance_id.id")
            )
            for attendance in attendances:
                if attendance.id not in existing_attendance_ids:
                    payslip.attendance_line_ids = [
                        (
                            0,
                            0,
                            {
                                "attendance_id": attendance.id,
                                "check_in": attendance.check_in,
                                "check_out": attendance.check_out,
                                "worked_hours": attendance.worked_hours,
                                "approved": False,  # Do not sync approved status
                                "last_approver_payslip_id": False,  # Reset last approver
                            },
                        )
                    ]

    def write(self, vals):
        res = super(HrPayslip, self).write(vals)
        if any(key in vals for key in ["employee_id", "date_from", "date_to"]):
            self._sync_attendance_records()
        return res

    @api.model
    def create(self, vals):
        record = super(HrPayslip, self).create(vals)
        record._sync_attendance_records()

        # Don't sync state browser from other payslips
        for line in record.attendance_line_ids:
            # By default, not approved when creating a new one
            line.approved = False
            line.last_approver_payslip_id = False
            line.approved_by = False

        return record

    # def action_duplicate_payslips(self):
    #     """
    #     Duplicate payslips with new start and end dates one month after the current payslip.
    #     """
    #     for payslip in self:
    #         # Calculate new start and end dates
    #         new_start_date = payslip.date_from + relativedelta(months=1)
    #         new_end_date = payslip.date_to + relativedelta(months=1)

    #         # Check if a payslip already exists for the employee and date range
    #         existing_payslip = self.env["hr.payslip"].search(
    #             [
    #                 ("employee_id", "=", payslip.employee_id.id),
    #                 ("date_from", "=", new_start_date),
    #                 ("date_to", "=", new_end_date),
    #             ],
    #             limit=1,
    #         )

    #         if existing_payslip:
    #             raise UserError(
    #                 (
    #                     f"Payslip already exists for employee {payslip.employee_id.name} "
    #                     f"from {new_start_date} to {new_end_date}. Unable to duplicate!"
    #                 )
    #             )

    #         # Copy current payslip with new start and end dates
    #         new_payslip = payslip.copy(
    #             {
    #                 "date_from": new_start_date,
    #                 "date_to": new_end_date,
    #             }
    #         )

    #         # Remove existing attendance records (if any) for the new payslip
    #         if new_payslip.attendance_line_ids:
    #             new_payslip.attendance_line_ids.unlink()

    #         # Filter attendance records according to new date range
    #         attendances = self.env["hr.attendance"].search(
    #             [
    #                 ("employee_id", "=", payslip.employee_id.id),
    #                 ("check_in", ">=", new_start_date),
    #                 ("check_out", "<=", new_end_date),
    #             ]
    #         )

    #         # Create new attendance records linked to the new payslip
    #         new_payslip.attendance_line_ids = [
    #             (
    #                 0,
    #                 0,
    #                 {
    #                     "attendance_id": attendance.id,
    #                     "check_in": attendance.check_in,
    #                     "check_out": attendance.check_out,
    #                     "worked_hours": attendance.worked_hours,
    #                     "approved": False,
    #                 },
    #             )
    #             for attendance in attendances
    #         ]

    #         # Kích hoạt cơ chế tự động cập nhật Attendance mới
    #         new_payslip._auto_update_attendance_records()

    def _auto_update_attendance_records(self):
        """
        Tự động cập nhật các Attendance Records mới vào Payslip nếu chúng nằm trong khoảng thời gian date_from và date_to.
        """
        for payslip in self:
            # Lấy tất cả Attendance Records thuộc khoảng thời gian của Payslip
            attendances = self.env["hr.attendance"].search(
                [
                    ("employee_id", "=", payslip.employee_id.id),
                    ("check_in", ">=", payslip.date_from),
                    ("check_out", "<=", payslip.date_to),
                ]
            )

            # Tìm các Attendance mới chưa được thêm vào Payslip
            existing_attendance_ids = payslip.attendance_line_ids.mapped(
                "attendance_id.id"
            )
            new_attendances = attendances.filtered(
                lambda a: a.id not in existing_attendance_ids
            )

            # Thêm các Attendance mới vào Payslip
            payslip.attendance_line_ids = [
                (
                    0,
                    0,
                    {
                        "attendance_id": attendance.id,
                        "check_in": attendance.check_in,
                        "check_out": attendance.check_out,
                        "worked_hours": attendance.worked_hours,
                        "approved": False,
                    },
                )
                for attendance in new_attendances
            ]

    def action_approve_attendance(self):
        """
        Approve all attendance records in the selected payslip.
        """
        _logger.info("Action Approve Attendance started for Payslip IDs: %s", self.ids)
        for payslip in self:
            for line in payslip.attendance_line_ids:
                if not line.approved:
                    line.approved = True  # Update approved status
                    _logger.info(
                        "Approved Attendance ID: %s for Payslip ID: %s",
                        line.attendance_id.id,
                        payslip.id,
                    )

                    # Find other payslip lines that contain the same attendance
                    other_payslip_lines = self.env["hr.payslip.attendance"].search(
                        [
                            ("attendance_id", "=", line.attendance_id.id),
                            ("payslip_id", "!=", payslip.id),
                        ]
                    )

                    # Disable editing for this attendance record in other payslips
                    other_payslip_lines.write({"approved": True})

            # Recompute total worked hours after approval
            payslip._compute_total_worked_hours()
            _logger.info("Recomputed total worked hours for Payslip ID: %s", payslip.id)
        _logger.info(
            "Action Approve Attendance completed for Payslip IDs: %s", self.ids
        )


class HrPayslipAttendance(models.Model):
    _name = "hr.payslip.attendance"
    _description = "Payslip Attendance"

    _logger = logging.getLogger(__name__)

    payslip_id = fields.Many2one(
        "hr.payslip", string="Payslip", ondelete="cascade", required=True
    )
    attendance_id = fields.Many2one(
        "hr.attendance", string="Attendance Record", required=True
    )
    check_in = fields.Datetime(
        string="Check In", related="attendance_id.check_in", readonly=True, store=True
    )
    check_out = fields.Datetime(
        string="Check Out", related="attendance_id.check_out", readonly=True
    )
    worked_hours = fields.Float(
        string="Worked Hours", related="attendance_id.worked_hours", readonly=True
    )
    approved_by = fields.Many2one("res.users", string="Approved By", readonly=True)
    approved = fields.Boolean(string="Approved", default=False)
    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        related="attendance_id.employee_id",
        store=True,
    )
    last_approver_payslip_id = fields.Many2one(
        "hr.payslip",
        string="Last Approver Payslip",
        help="The last payslip that approved this attendance record.",
    )

    def toggle_approval(self):
        """
        Toggle the approval status of the attendance record in the payslip.
        When the record is approved in one payslip, it cannot be approved or unapproved in any other payslip.
        """
        for record in self:
            # Check if the attendance has already been approved in another payslip
            if not record.approved:
                existing_approved_lines = self.env["hr.payslip.attendance"].search(
                    [
                        ("attendance_id", "=", record.attendance_id.id),
                        ("approved", "=", True),
                        ("payslip_id", "!=", record.payslip_id.id),
                    ],
                    limit=1,
                )
                if existing_approved_lines:
                    raise UserError(
                        "This attendance record has already been approved in payslip hr.payslip,%s and cannot be approved again."
                        % existing_approved_lines.payslip_id.id
                    )

            if record.approved:
                # If the record is already approved but missing `last_approver_payslip_id`, assign the current payslip
                if not record.last_approver_payslip_id:
                    record.last_approver_payslip_id = record.payslip_id

                # Check if the record does not belong to the current payslip
                if record.last_approver_payslip_id != record.payslip_id:
                    raise UserError(
                        "Only payslip hr.payslip,%s has the authority to unapprove this record."
                        % (
                            record.last_approver_payslip_id.id
                            if record.last_approver_payslip_id
                            else "Unknown"
                        )
                    )

                # Unapprove the record
                record.approved = False
                record.approved_by = False
                record.last_approver_payslip_id = False
            else:
                # Approve the record
                record.approved = True
                record.last_approver_payslip_id = record.payslip_id
                record.approved_by = self.env.user.id

            # Synchronize the status within the current payslip
            self._sync_approval_status_within_payslip(record)

            # Recompute the total worked hours for related payslips
            self._recompute_related_payslips(record)

    def _sync_approval_status_within_payslip(self, record):
        """
        Synchronize the approval status across all related payslip lines
        for the attendance record within the same payslip.
        """
        related_lines = self.env["hr.payslip.attendance"].search(
            [
                ("attendance_id", "=", record.attendance_id.id),
                (
                    "payslip_id",
                    "=",
                    record.payslip_id.id,
                ),  # Only sync within the same payslip
            ]
        )
        for line in related_lines:
            line.approved = record.approved
            line.last_approver_payslip_id = record.last_approver_payslip_id
            line.approved_by = record.approved_by

    def _recompute_related_payslips(self, record):
        """
        Recompute the total worked hours for all payslips related to the attendance record.
        """
        related_payslips = self.env["hr.payslip"].search(
            [("attendance_line_ids.attendance_id", "=", record.attendance_id.id)]
        )
        for payslip in related_payslips:
            payslip._compute_total_worked_hours()

    def action_view_details(self):
        """
        Open a popup to show the timesheet details related to the selected attendance.
        """
        self.ensure_one()

        # Refresh the current record to ensure the latest status
        self.refresh()

        return {
            "type": "ir.actions.act_window",
            "name": "Attendance and Timesheet Details",
            "view_mode": "form",
            "res_model": "attendance.timesheet.details",
            "target": "new",
            "context": {
                "default_employee_id": self.attendance_id.employee_id.id,
                "default_date": self.attendance_id.check_in.date(),
                "default_check_in": self.attendance_id.check_in,
                "default_check_out": self.attendance_id.check_out,
                "default_worked_hours": self.attendance_id.worked_hours,
                "default_approved": self.approved,  # Ensure the approved status is updated
            },
        }


_logger = logging.getLogger(__name__)


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    def toggle_approval(self):
        """Toggle approval status for attendance."""
        for record in self:
            record.approved = not record.approved

    @api.model
    def _round_time(self, time):
        """Làm tròn thời gian tới phút gần nhất"""
        return (time + timedelta(seconds=30)).replace(second=0, microsecond=0)

    @api.model_create_multi
    def create(self, vals_list):
        """Làm tròn thời gian khi tạo mới và tự động đồng bộ với Payslip"""
        # Làm tròn thời gian cho tất cả records
        for vals in vals_list:
            if "check_in" in vals and vals["check_in"]:
                vals["check_in"] = self._round_time(
                    fields.Datetime.from_string(vals["check_in"])
                )
            if "check_out" in vals and vals["check_out"]:
                vals["check_out"] = self._round_time(
                    fields.Datetime.from_string(vals["check_out"])
                )

        # Tạo attendance records
        attendances = super().create(vals_list)

        # Cập nhật payslip cho mỗi attendance
        for attendance in attendances:
            if attendance.check_out:  # Chỉ cập nhật khi đã check out
                payslips = self.env["hr.payslip"].search(
                    [
                        ("employee_id", "=", attendance.employee_id.id),
                        ("date_from", "<=", attendance.check_in),
                        ("date_to", ">=", attendance.check_out),
                    ]
                )
                if payslips:
                    payslips._auto_update_attendance_records()

        return attendances

    def write(self, vals):
        """Làm tròn thời gian khi cập nhật và đồng bộ với Payslip"""
        # Làm tròn thời gian
        if "check_in" in vals and vals["check_in"]:
            vals["check_in"] = self._round_time(
                fields.Datetime.from_string(vals["check_in"])
            )
        if "check_out" in vals and vals["check_out"]:
            vals["check_out"] = self._round_time(
                fields.Datetime.from_string(vals["check_out"])
            )

        # Thực hiện cập nhật
        result = super().write(vals)

        # Cập nhật payslip nếu có thay đổi check_in hoặc check_out
        if "check_in" in vals or "check_out" in vals:
            for attendance in self:
                if attendance.check_out:  # Chỉ cập nhật khi đã check out
                    payslips = self.env["hr.payslip"].search(
                        [
                            ("employee_id", "=", attendance.employee_id.id),
                            ("date_from", "<=", attendance.check_in),
                            ("date_to", ">=", attendance.check_out),
                        ]
                    )
                    if payslips:
                        payslips._auto_update_attendance_records()

        return result


class HrPayslipDuplicateWizard(models.TransientModel):
    _name = "hr.payslip.duplicate.wizard"
    _description = "Wizard for duplicating payslip"

    currency_rate_fallback = fields.Float(
        string="Currency Rate Fallback", required=True
    )

    def action_duplicate_payslips(self):
        """
        Duplicate multiple payslips with:
        - Updated `currency_rate_fallback` applied to all new payslips.
        - New start and end dates set to one month after the original payslip.
        - Validation to prevent duplicate payslips for the same employee and date range.
        - Attendance records updated accordingly.
        """
        active_ids = self.env.context.get("active_ids", [])
        if not active_ids:
            raise UserError("No payslips selected to duplicate.")

        for payslip in self.env["hr.payslip"].browse(active_ids):
            # Tính toán ngày mới (tháng kế tiếp)
            new_start_date = payslip.date_from + relativedelta(months=1)
            new_end_date = payslip.date_to + relativedelta(months=1)

            # Kiểm tra xem đã tồn tại phiếu lương cho tháng tiếp theo chưa
            existing_payslip = self.env["hr.payslip"].search(
                [
                    ("employee_id", "=", payslip.employee_id.id),
                    ("date_from", "=", new_start_date),
                    ("date_to", "=", new_end_date),
                ],
                limit=1,
            )
            if existing_payslip:
                raise UserError(
                    (
                        f"Payslip already exists for employee {payslip.employee_id.name} "
                        f"from {new_start_date} to {new_end_date}. Unable to duplicate!"
                    )
                )

            # Sao chép Payslip với giá trị mới
            new_payslip = payslip.copy(
                {
                    "date_from": new_start_date,
                    "date_to": new_end_date,
                    "currency_rate_fallback": self.currency_rate_fallback,  # Cập nhật giá trị mới
                }
            )

            # Xóa danh sách chấm công cũ (nếu có)
            if new_payslip.attendance_line_ids:
                new_payslip.attendance_line_ids.unlink()

            # Lấy danh sách chấm công phù hợp với khoảng thời gian mới
            attendances = self.env["hr.attendance"].search(
                [
                    ("employee_id", "=", payslip.employee_id.id),
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
                        "attendance_id": attendance.id,
                        "check_in": attendance.check_in,
                        "check_out": attendance.check_out,
                        "worked_hours": attendance.worked_hours,
                        "approved": False,
                    },
                )
                for attendance in attendances
            ]

            # Kích hoạt cơ chế tự động cập nhật Attendance mới
            new_payslip._auto_update_attendance_records()

        # return {"type": "ir.actions.client", "tag": "reload"}
        return {
            "effect": {
                "fadeout": "slow",
                "message": "Payslip(s) duplicated successfully!",
                "type": "rainbow_man",
            }
        }
