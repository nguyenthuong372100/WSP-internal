from odoo import models, fields, api
import logging
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError


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
        """
        for payslip in self:
            if not payslip.employee_id or not payslip.date_from or not payslip.date_to:
                continue  # Skip if any of the fields are missing

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

            # Find the IDs of attendance records that already exist
            existing_attendance_ids = set(
                payslip.attendance_line_ids.mapped("attendance_id.id")
            )

            # Add new records (only those that don't already exist)
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
                                "approved": False,
                                "last_approver_payslip_id": payslip.id,
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

        # Đồng bộ trạng thái phê duyệt từ các payslip khác
        for line in record.attendance_line_ids:
            existing_lines = self.env["hr.payslip.attendance"].search(
                [
                    ("attendance_id", "=", line.attendance_id.id),
                    ("approved", "=", True),
                ],
                limit=1,
            )
            if existing_lines:
                line.approved = True
                line.last_approver_payslip_id = existing_lines.payslip_id
                line.approved_by = existing_lines.approved_by

        return record

    def action_duplicate_payslips(self):
        """
        Duplicate payslips with new start and end dates one month after the current payslip.
        """
        for payslip in self:
            # Calculate new start and end dates
            new_start_date = payslip.date_from + relativedelta(months=1)
            new_end_date = payslip.date_to + relativedelta(months=1)

            # Check if a payslip already exists for the employee and date range
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

            # Copy current payslip with new start and end dates
            new_payslip = payslip.copy(
                {
                    "date_from": new_start_date,
                    "date_to": new_end_date,
                }
            )

            # Remove existing attendance records (if any) for the new payslip
            if new_payslip.attendance_line_ids:
                new_payslip.attendance_line_ids.unlink()

            # Filter attendance records according to new date range
            attendances = self.env["hr.attendance"].search(
                [
                    ("employee_id", "=", payslip.employee_id.id),
                    ("check_in", ">=", new_start_date),
                    ("check_out", "<=", new_end_date),
                ]
            )

            # Create new attendance records linked to the new payslip
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

            # Remove readonly status for date_from and date_to fields
            # new_payslip.write({
            #     'state': 'draft'
            # })

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
        Toggle the approval status of the attendance record in payslip.
        When the record is approved in one payslip, other payslips will sync the status,
        and only the last payslip that approved has the right to unapprove.
        """
        for record in self:
            # Check unapproval rules
            if record.approved:
                if not record.last_approver_payslip_id:
                    raise UserError(
                        "Unable to unapprove because this record is not yet associated with any payslip."
                    )
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

            # Synchronize approval status across related payslip lines
            self._sync_approval_status(record)

            # Recompute related payslips' total worked hours
            self._recompute_related_payslips(record)

    def _sync_approval_status(self, record):
        """
        Synchronize the approval status across all related payslip lines for the attendance record.
        """
        related_lines = self.env["hr.payslip.attendance"].search(
            [("attendance_id", "=", record.attendance_id.id)]
        )
        for line in related_lines:
            line.approved = record.approved
            line.last_approver_payslip_id = record.payslip_id
            line.approved_by = record.approved_by

    def _recompute_related_payslips(self, record):
        """
        Recompute total worked hours for all payslips related to the attendance record.
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


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    def toggle_approval(self):
        """Toggle approval status for attendance."""
        for record in self:
            record.approved = not record.approved
