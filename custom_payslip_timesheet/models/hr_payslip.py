from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    attendance_line_ids = fields.One2many(
        "hr.payslip.attendance", "payslip_id", string="Attendance Records", copy=False
    )
    worked_hours = fields.Float(string="Total Worked Hours", readonly=True)

    def _compute_total_worked_hours(self):
        for payslip in self:
            total_hours = sum(
                line.worked_hours
                for line in payslip.attendance_line_ids
                if line.approved
            )
            payslip.worked_hours = total_hours

    @api.onchange("employee_id", "date_from", "date_to")
    def _onchange_attendance_records(self):
        """
        Lấy các bản ghi attendance phù hợp và tạo bản ghi trong bảng trung gian.
        """
        if self.employee_id and self.date_from and self.date_to:
            # Xóa các bản ghi cũ
            self.attendance_line_ids = [(5, 0, 0)]

            # Tìm các bản ghi attendance phù hợp
            attendances = self.env["hr.attendance"].search(
                [
                    ("employee_id", "=", self.employee_id.id),
                    ("check_in", ">=", self.date_from),
                    ("check_out", "<=", self.date_to),
                ]
            )

            # Tạo bản ghi trong bảng trung gian
            lines = []
            for attendance in attendances:
                lines.append(
                    (
                        0,
                        0,
                        {
                            "attendance_id": attendance.id,
                            "check_in": attendance.check_in,
                            "check_out": attendance.check_out,
                            "worked_hours": attendance.worked_hours,
                            "approved": False,  # Mặc định chưa phê duyệt
                        },
                    )
                )
            self.attendance_line_ids = lines

    def write(self, vals):
        """
        Override phương thức write để đảm bảo dữ liệu attendance không bị mất.
        """
        result = super(HrPayslip, self).write(vals)
        for payslip in self:
            if "employee_id" in vals or "date_from" in vals or "date_to" in vals:
                payslip._onchange_attendance_records()
        return result

    @api.model
    def create(self, vals):
        """
        Override phương thức create để tạo các bản ghi attendance khi tạo payslip.
        """
        payslip = super(HrPayslip, self).create(vals)
        payslip._onchange_attendance_records()
        return payslip


class HrPayslipAttendance(models.Model):
    _name = "hr.payslip.attendance"
    _description = "Payslip Attendance"

    payslip_id = fields.Many2one("hr.payslip", string="Payslip", ondelete="cascade")
    attendance_id = fields.Many2one(
        "hr.attendance", string="Attendance Record", required=True
    )
    check_in = fields.Datetime(
        string="Check In", related="attendance_id.check_in", readonly=True
    )
    check_out = fields.Datetime(
        string="Check Out", related="attendance_id.check_out", readonly=True
    )
    worked_hours = fields.Float(
        string="Worked Hours", related="attendance_id.worked_hours", readonly=True
    )
    approved = fields.Boolean(string="Approved", default=False)

    def toggle_approval(self):
        """
        Toggle trạng thái phê duyệt của bản ghi attendance trong payslip.
        """
        for record in self:
            record.approved = not record.approved
            _logger.info(
                f"Payslip {record.payslip_id.id}: Attendance ID {record.attendance_id.id} approval toggled to {record.approved}"
            )
            # Tính toán lại tổng số giờ làm việc ngay sau khi thay đổi trạng thái
            record.payslip_id._compute_total_worked_hours()

    def action_view_details(self):
        """Opens the popup view showing timesheets related to the selected attendance."""
        self.ensure_one()
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
            },
        }


class HrAttendance(models.Model):
    _inherit = "hr.attendance"
    pass
