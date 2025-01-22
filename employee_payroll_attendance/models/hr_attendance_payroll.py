from odoo import api, fields, models
import logging
from datetime import timedelta
from odoo.exceptions import UserError, AccessError

try:
    from forex_python.converter import CurrencyRates
except ImportError:
    CurrencyRates = None
    logging.error(
        "The forex-python library is not installed. Please install it using 'pip install forex-python'."
    )

_logger = logging.getLogger(__name__)


class HrPayslip(models.Model):
    _name = "hr.payslip"
    _description = "Employee Payslip"
    combined_records = fields.One2many(
        "hr.payslip.combined.record",
        "payslip_id",
        string="Attendance and Timesheet Records",
        readonly=True,
    )

    employee_id = fields.Many2one("hr.employee", string="Employee", required=True)
    date_from = fields.Date(string="Start Date", required=True)
    date_to = fields.Date(string="End Date", required=True)
    wage = fields.Float(
        string="Monthly Wage (USD)", help="Base monthly wage for the employee."
    )
    hourly_rate = fields.Float(
        string="Hourly Rate (USD)", help="Hourly wage for the employee."
    )
    hourly_rate_vnd = fields.Float(
        string="Hourly Rate (VND)", help="Hourly rate in VND."
    )
    worked_hours = fields.Float(
        string="Worked Hours", compute="_compute_worked_hours", store=True
    )
    total_salary = fields.Float(
        string="Total Salary", compute="_compute_total_salary", store=True
    )
    converted_salary_vnd = fields.Float(
        string="Salary in VND", compute="_compute_converted_salary_vnd", store=True
    )
    currency_rate_fallback = fields.Float(
        string="Fallback Currency Rate (USD to VND)",
        default=23000,
        help="Fallback rate for currency conversion if live rate is unavailable.",
    )
    include_saturdays = fields.Boolean(string="Include 2 Saturdays?", default=False)
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("generated", "Payslip Generated"),
            ("employee_confirm", "Employee Confirm"),
            ("transfer_payment", "Transfer Payment"),
            ("done", "Done"),
        ],
        default="draft",
        string="Status",
    )
    attendance_ids = fields.One2many(
        "hr.attendance",
        compute="_compute_attendance_ids",
        string="Attendance Records",
        readonly=False,
    )
    attendance_line_ids = fields.One2many(
        "hr.payslip.attendance", "payslip_id", string="Attendance Records", copy=False
    )

    # Additional fields for allowances and bonuses
    insurance = fields.Float(string="Insurance", default=0.0)
    meal_allowance = fields.Float(string="Meal Allowance", default=0.0)
    kpi_bonus = fields.Float(string="KPI Bonus", default=0.0)
    other_bonus = fields.Float(string="Other Bonus", default=0.0)

    # New fields for additional information
    total_working_days = fields.Integer(
        string="Total Working Days", compute="_compute_additional_fields"
    )
    total_working_hours = fields.Float(
        string="Total Working Hours", compute="_compute_additional_fields"
    )
    approved_working_days = fields.Float(
        string="Approved Working Days", compute="_compute_additional_fields"
    )
    approved_working_hours = fields.Float(
        string="Approved Working Hours", compute="_compute_additional_fields"
    )

    vendor_bill_id = fields.Many2one(
        "account.move",
        string="Vendor Bill",
        readonly=True,
        help="The vendor bill generated for this payslip.",
    )

    probation_start_date = fields.Date(string="Probation Start Date")
    probation_end_date = fields.Date(string="Probation End Date")
    probation_percentage = fields.Float(string="Probation Percentage", default=85.0)
    probation_hours = fields.Float(
        string="Approved Hours (Probation)", compute="_compute_total_salary", store=True
    )
    probation_salary = fields.Float(
        string="Salary (Probation)", compute="_compute_total_salary", store=True
    )
    monthly_wage_vnd = fields.Float(string="Monthly Wage (VND)")

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        # Check if the user is an admin
        if not self.env.user.has_group("base.group_system"):
            # Restrict access for regular users to their own records
            args = args or []
            args += [("employee_id.user_id", "=", self.env.user.id)]
        # Call the original search method
        return super(HrPayslip, self).search(args, offset, limit, order, count)

    @api.depends("total_salary", "currency_rate_fallback", "wage", "hourly_rate")
    def _compute_converted_salary_vnd(self):
        """
        Computes the salary in VND based on the total salary in USD using the fallback rate.
        Updates Monthly Wage (VND) if the wage field changes.
        """
        for payslip in self:
            fallback_rate = payslip.currency_rate_fallback

            # Compute converted salary in VND
            payslip.converted_salary_vnd = payslip.total_salary * fallback_rate

            # Compute Monthly Wage (VND) based on wage and fallback rate
            if payslip.wage:
                payslip.monthly_wage_vnd = payslip.wage * fallback_rate
                _logger.info(
                    f"Updated Monthly Wage (VND) based on fallback rate: {payslip.wage} USD × {fallback_rate} = {payslip.monthly_wage_vnd} VND"
                )

            _logger.info(
                f"Converted salary for {payslip.employee_id.name} is {payslip.converted_salary_vnd} VND "
                f"based on total salary {payslip.total_salary} and fallback rate {fallback_rate}."
            )

    @api.depends("employee_id", "date_from", "date_to")
    def _compute_attendance_ids(self):
        for payslip in self:
            if payslip.employee_id and payslip.date_from and payslip.date_to:
                attendances = self.env["hr.attendance"].search(
                    [
                        ("employee_id", "=", payslip.employee_id.id),
                        ("check_in", ">=", payslip.date_from),
                        ("check_out", "<=", payslip.date_to),
                    ]
                )
                payslip.attendance_ids = attendances
            else:
                payslip.attendance_ids = False

    @api.onchange("wage")
    def _onchange_wage(self):
        if self.wage and self.total_working_days:
            self.hourly_rate = self.wage / (self.total_working_days * 8)
        else:
            self.hourly_rate = 0.0

    @api.onchange("hourly_rate")
    def _onchange_hourly_rate(self):
        if self.hourly_rate and self.total_working_days:
            self.wage = self.hourly_rate * (self.total_working_days * 8)
        else:
            self.wage = 0.0

    @api.depends("attendance_line_ids.approved", "attendance_line_ids.worked_hours")
    def _compute_worked_hours(self):
        for payslip in self:
            total_hours = sum(
                attendance.worked_hours
                for attendance in payslip.attendance_line_ids
                if attendance.approved
            )
            payslip.worked_hours = total_hours
            _logger.info(
                f"Total approved worked hours for {payslip.employee_id.name}: {total_hours}"
            )

    # @api.depends(
    #     "worked_hours",
    #     "attendance_line_ids",
    #     "probation_start_date",
    #     "probation_end_date",
    #     "probation_percentage",
    # )
    @api.depends(
        "probation_start_date",
        "probation_end_date",
        "hourly_rate",
        "attendance_line_ids.approved",
        "attendance_line_ids.worked_hours",
        "insurance",
        "meal_allowance",
        "kpi_bonus",
        "other_bonus",
        "monthly_wage_vnd",
    )
    @api.onchange(
        "probation_start_date",
        "probation_end_date",
        "hourly_rate",
        "attendance_line_ids.approved",
        "attendance_line_ids.worked_hours",
        "insurance",
        "meal_allowance",
        "kpi_bonus",
        "other_bonus",
        "monthly_wage_vnd",
    )
    def _compute_total_salary(self):
        for payslip in self:
            probation_hours = 0
            normal_hours = 0
            hourly_rate = payslip.hourly_rate

            _logger.info(
                f"Starting salary computation for payslip: {payslip.id} (Employee: {payslip.employee_id.name})"
            )
            _logger.info(
                f"Hourly rate: {hourly_rate}, Probation percentage: {payslip.probation_percentage}%"
            )

            if payslip.probation_start_date and payslip.probation_end_date:
                # Probation period is defined
                probation_start = fields.Date.from_string(payslip.probation_start_date)
                probation_end = fields.Date.from_string(payslip.probation_end_date)

                _logger.info(f"Probation period: {probation_start} to {probation_end}")

                for attendance in payslip.attendance_line_ids:
                    attendance_date = attendance.check_in.date()
                    if (
                        probation_start <= attendance_date <= probation_end
                        and attendance.approved
                    ):
                        probation_hours += attendance.worked_hours
                        _logger.info(
                            f"Approved hours in probation period on {attendance_date}: {attendance.worked_hours}"
                        )
                    elif attendance.approved:
                        normal_hours += attendance.worked_hours
                        _logger.info(
                            f"Approved hours outside probation period on {attendance_date}: {attendance.worked_hours}"
                        )
            else:
                # If no probation period, all approved hours are treated as normal hours
                normal_hours = sum(
                    attendance.worked_hours
                    for attendance in payslip.attendance_line_ids
                    if attendance.approved
                )
                _logger.info(
                    f"No probation period defined. All approved hours treated as normal: {normal_hours} hours."
                )

            # Calculate probation salary only if probation period is defined
            probation_salary = 0
            if probation_hours > 0:
                probation_salary = (
                    probation_hours
                    * hourly_rate
                    * (payslip.probation_percentage / 100.0)
                )
            _logger.info(
                f"Probation hours: {probation_hours}, Probation salary: {probation_salary}"
            )

            # Calculate normal salary
            normal_salary = normal_hours * hourly_rate
            _logger.info(
                f"Normal hours: {normal_hours}, Normal salary: {normal_salary}"
            )

            # Calculate total salary
            if not payslip.probation_start_date or not payslip.probation_end_date:
                # If no probation date, total salary is normal salary
                total_salary = (
                    normal_salary
                    - payslip.insurance
                    + payslip.meal_allowance
                    + payslip.kpi_bonus
                    + payslip.other_bonus
                )
            else:
                # Include probation salary if probation period is defined
                total_salary = (
                    probation_salary
                    + normal_salary
                    - payslip.insurance
                    + payslip.meal_allowance
                    + payslip.kpi_bonus
                    + payslip.other_bonus
                )

            # Set computed fields
            payslip.probation_hours = probation_hours
            payslip.probation_salary = probation_salary
            payslip.total_salary = total_salary

            # Log final result
            _logger.info(
                f"Total salary: {total_salary} (Probation: {probation_salary}, Normal: {normal_salary})"
            )

    @api.onchange("monthly_wage_vnd")
    def _onchange_monthly_wage_vnd(self):
        """
        Update Monthly Wage (USD) and hourly rates based on Monthly Wage (VND) and fallback rate, then recalculate total salary.
        """
        if self.monthly_wage_vnd and self.currency_rate_fallback:
            self.wage = self.monthly_wage_vnd / self.currency_rate_fallback
            _logger.info(
                f"Converted Monthly Wage from VND to USD: {self.monthly_wage_vnd} VND ÷ {self.currency_rate_fallback} = {self.wage} USD"
            )
        else:
            self.wage = 0.0
            _logger.warning(
                "Monthly Wage (VND) or Fallback Currency Rate is missing. Unable to convert to USD."
            )
        self._update_hourly_rates()
        self._recalculate_total_salary()

    @api.onchange("wage")
    def _onchange_wage(self):
        """
        Update Monthly Wage (VND) and hourly rates based on Monthly Wage (USD) and fallback rate, then recalculate total salary.
        """
        if self.wage and self.currency_rate_fallback:
            self.monthly_wage_vnd = self.wage * self.currency_rate_fallback
            _logger.info(
                f"Converted Monthly Wage from USD to VND: {self.wage} USD x {self.currency_rate_fallback} = {self.monthly_wage_vnd} VND"
            )
        else:
            self.monthly_wage_vnd = 0.0
            _logger.warning(
                "Monthly Wage (USD) or Fallback Currency Rate is missing. Unable to convert to VND."
            )
        self._update_hourly_rates()
        self._recalculate_total_salary()

    @api.onchange("hourly_rate_vnd")
    def _onchange_hourly_rate_vnd(self):
        """
        Update Hourly Rate (USD), Monthly Wage (USD), and Monthly Wage (VND) based on Hourly Rate (VND).
        """
        if self.hourly_rate_vnd and self.currency_rate_fallback:
            self.hourly_rate = self.hourly_rate_vnd / self.currency_rate_fallback
            self.wage = self.hourly_rate * self.total_working_hours
            self.monthly_wage_vnd = self.wage * self.currency_rate_fallback
            _logger.info(
                f"Converted Hourly Rate (VND) to USD: {self.hourly_rate_vnd} VND ÷ {self.currency_rate_fallback} = {self.hourly_rate} USD. "
                f"Updated Monthly Wage (USD) = {self.wage}, Monthly Wage (VND) = {self.monthly_wage_vnd}"
            )
        else:
            self.hourly_rate = 0.0
            _logger.warning(
                "Hourly Rate (VND) or Fallback Currency Rate is missing. Unable to convert to USD."
            )
        self._recalculate_total_salary()

    @api.onchange("hourly_rate")
    def _onchange_hourly_rate(self):
        """
        Update Hourly Rate (VND), Monthly Wage (USD), and Monthly Wage (VND) based on Hourly Rate (USD).
        """
        if self.hourly_rate and self.currency_rate_fallback:
            self.hourly_rate_vnd = self.hourly_rate * self.currency_rate_fallback
            self.wage = (
                self.hourly_rate * self.total_working_hours
            )  # Assuming 160 working hours per month
            self.monthly_wage_vnd = self.wage * self.currency_rate_fallback
            _logger.info(
                f"Converted Hourly Rate (USD) to VND: {self.hourly_rate} USD × {self.currency_rate_fallback} = {self.hourly_rate_vnd} VND. "
                f"Updated Monthly Wage (USD) = {self.wage}, Monthly Wage (VND) = {self.monthly_wage_vnd}"
            )
        else:
            self.hourly_rate_vnd = 0.0
            _logger.warning(
                "Hourly Rate (USD) or Fallback Currency Rate is missing. Unable to convert to VND."
            )
        self._recalculate_total_salary()

    def _update_hourly_rates(self):
        """
        Helper method to update hourly rates in both USD and VND based on the current monthly wage and fallback rate.
        """
        if self.wage and self.currency_rate_fallback:
            self.hourly_rate = (
                self.wage / self.total_working_hours
            )  # Assuming 160 working hours per month
            self.hourly_rate_vnd = self.hourly_rate * self.currency_rate_fallback
            _logger.info(
                f"Updated Hourly Rates: Hourly Rate (USD) = {self.hourly_rate}, Hourly Rate (VND) = {self.hourly_rate_vnd}"
            )
        else:
            self.hourly_rate = 0.0
            self.hourly_rate_vnd = 0.0
            _logger.warning(
                "Unable to update hourly rates. Either Monthly Wage or Fallback Currency Rate is missing."
            )

    def _recalculate_total_salary(self):
        """
        Helper method to trigger recalculation of total salary when wage or hourly rate fields change.
        """
        self._compute_total_salary()

    @api.onchange("date_from", "date_to", "include_saturdays", "attendance_line_ids")
    def _compute_additional_fields(self):
        for payslip in self:
            if payslip.date_from and payslip.date_to:
                _logger.info(
                    f"Starting computation for payslip {payslip.id} (Employee: {payslip.employee_id.name})"
                )
                # Counter for weekdays (Monday-Friday)
                weekdays_count = 0
                # Counter for Saturday
                saturday_count = 0

                # Iterate through all days in the range date_from -> date_to
                date_diff = (payslip.date_to - payslip.date_from).days + 1
                for n in range(date_diff):
                    current_date = payslip.date_from + timedelta(days=n)
                    weekday_index = current_date.weekday()
                    # Monday to Friday corresponds to weekday_index = 0..4
                    if 0 <= weekday_index < 5:
                        weekdays_count += 1
                    # Saturday is weekday_index = 5
                    elif weekday_index == 5:
                        saturday_count += 1

                # Calculate hours for weekdays (8 hours/day)
                weekday_hours = weekdays_count * 8

                # If checkbox include_saturdays = True, calculate up to 2 Saturdays (6.5 hours/day)
                if payslip.include_saturdays:
                    saturdays_to_count = min(saturday_count, 2)
                    saturday_hours = saturdays_to_count * 8
                else:
                    saturdays_to_count = 0
                    saturday_hours = 0

                # Total working days
                working_days = weekdays_count + saturdays_to_count
                # Total working hours
                total_working_hours = weekday_hours + saturday_hours

                # Calculate Approved Days/Hours (unchanged from previous logic)
                # approved_days = len(
                #     {
                #         att.attendance_id.check_in.date()
                #         for att in payslip.attendance_line_ids
                #         if att.approved
                #     }
                # )
                approved_hours = sum(
                    att.worked_hours
                    for att in payslip.attendance_line_ids
                    if att.approved
                )

                approved_days = approved_hours / 8

                # Assign results to fields
                payslip.total_working_days = working_days
                payslip.total_working_hours = total_working_hours
                payslip.approved_working_days = approved_days
                payslip.approved_working_hours = approved_hours

                _logger.info(
                    f"Payslip {payslip.id}: Total Working Days = {working_days}, "
                    f"Total Working Hours = {total_working_hours}, Approved Days = {approved_days}, "
                    f"Approved Hours = {approved_hours}"
                )
            else:
                # If date_from or date_to is missing
                payslip.total_working_days = 0
                payslip.total_working_hours = 0.0
                payslip.approved_working_days = 0
                payslip.approved_working_hours = 0.0

                _logger.warning(
                    f"Payslip {payslip.id} is missing date_from or date_to. Default values applied."
                )

    def _update_report_status(self):
        for payslip in self:
            report = self.env["hr.payslip.report"].search(
                [
                    ("employee_id", "=", payslip.employee_id.id),
                    ("date_from", "=", payslip.date_from),
                    ("date_to", "=", payslip.date_to),
                ],
                limit=1,
            )
            if report:
                report.status = payslip.status
                _logger.info(
                    f"Updated report status for {payslip.employee_id.name} to {payslip.status}"
                )

    def generate_payslip(self):
        for payslip in self:
            payslip.status = "generated"
            payslip._update_report_status()

            # Retrieve data from hr.payslip.attendance table based on payslip_id
            attendance_records = self.env["hr.payslip.attendance"].search(
                [("payslip_id", "=", payslip.id)]
            )

            # Convert attendance data to the required format
            attendance_data = [
                (
                    0,
                    0,
                    {
                        "check_in": attendance.check_in,
                        "check_out": attendance.check_out,
                        "worked_hours": attendance.worked_hours,
                        "approved": attendance.approved,
                    },
                )
                for attendance in attendance_records
            ]

            # Create payslip report
            self.env["hr.payslip.report"].create(
                {
                    "employee_id": payslip.employee_id.id,
                    "date_from": payslip.date_from,
                    "date_to": payslip.date_to,
                    "worked_hours": payslip.worked_hours,
                    "total_working_days": payslip.total_working_days,
                    "total_working_hours": payslip.total_working_hours,
                    "approved_working_hours": payslip.approved_working_hours,
                    "total_salary": payslip.total_salary,
                    "insurance": payslip.insurance,
                    "meal_allowance": payslip.meal_allowance,
                    "kpi_bonus": payslip.kpi_bonus,
                    "other_bonus": payslip.other_bonus,
                    "attendance_ids": attendance_data,
                    "status": "generated",
                    "converted_salary_vnd": payslip.converted_salary_vnd,
                }
            )

            _logger.info(
                f"Payslip for {payslip.employee_id.name} has been generated and data moved to report."
            )

    def action_set_draft(self):
        for payslip in self:
            if payslip.status == "generated":
                payslip.status = "draft"
                payslip._update_report_status()

    def action_employee_confirm(self):
        """
        Set the payslip status to 'employee_confirm' and create a vendor bill.
        """
        for payslip in self:
            if payslip.status == "generated":
                payslip.status = "employee_confirm"
                payslip._update_report_status()

                # Automatically create a vendor bill after confirmation
                payslip.action_create_vendor_bill()
                _logger.info(
                    f"Payslip for {payslip.employee_id.name} confirmed and vendor bill created."
                )

    def action_transfer_payment(self):
        """
        Logic for transferring payment. Restrict access for non-admin users.
        """
        for payslip in self:
            # Kiểm tra nếu user không thuộc nhóm admin
            if not self.env.user.has_group("base.group_system"):
                raise AccessError("You do not have permission to perform this action.")
            # Thực hiện logic chuyển khoản
            payslip.status = "transfer_payment"

    def action_done(self):
        """
        Set the status to 'done' from 'transfer_payment'.
        """
        for payslip in self:
            if payslip.status == "transfer_payment":
                payslip.status = "done"
                _logger.info(
                    f"Payslip {payslip.id} marked as Done by {self.env.user.name}"
                )

    def action_revert_generated(self):
        """
        Revert the status from 'employee_confirm' to 'generated'.
        """
        for payslip in self:
            if payslip.status == "employee_confirm":
                payslip.status = "generated"
                _logger.info(
                    f"Payslip {payslip.id} reverted to Generated by {self.env.user.name}"
                )

    def action_revert_employee_confirm(self):
        for payslip in self:
            if payslip.status == "transfer_payment":
                # Delete the existing vendor bill if it exists
                if payslip.vendor_bill_id:
                    try:
                        payslip.vendor_bill_id.button_cancel()  # Cancel the vendor bill
                        payslip.vendor_bill_id.unlink()  # Delete the vendor bill
                        _logger.info(
                            f"Deleted vendor bill for {payslip.employee_id.name}."
                        )
                    except Exception as e:
                        _logger.error(
                            f"Error deleting vendor bill for {payslip.employee_id.name}: {e}"
                        )
                        raise UserError(f"Error deleting vendor bill: {e}")

                # Reset status to `employee_confirm`
                payslip.status = "employee_confirm"
                payslip.vendor_bill_id = False  # Reset the link to the vendor bill
                _logger.info(
                    f"Reverted {payslip.employee_id.name}'s status to Employee Confirm."
                )

    def action_revert_transfer_payment(self):
        """
        Revert the status from 'transfer_payment' to 'employee_confirm'.
        """
        for payslip in self:
            if payslip.status == "transfer_payment":
                payslip.status = "employee_confirm"
                _logger.info(
                    f"Payslip {payslip.id} reverted to Employee Confirm by {self.env.user.name}"
                )

    @api.depends("attendance_ids", "date_from", "date_to")
    def _compute_combined_records(self):
        for payslip in self:
            combined_lines = []
            # Fetch attendance records
            for attendance in payslip.attendance_ids:
                timesheet_lines = self.env["account.analytic.line"].search(
                    [
                        ("employee_id", "=", payslip.employee_id.id),
                        ("date", "=", attendance.check_in.date()),
                    ]
                )
                # Add attendance record
                combined_lines.append(
                    (
                        0,
                        0,
                        {
                            "type": "attendance",
                            "date": attendance.check_in.date(),
                            "check_in": attendance.check_in,
                            "check_out": attendance.check_out,
                            "worked_hours": attendance.worked_hours,
                            "approved": attendance.approved,
                        },
                    )
                )
                # Add related timesheet records
                for timesheet in timesheet_lines:
                    combined_lines.append(
                        (
                            0,
                            0,
                            {
                                "type": "timesheet",
                                "date": timesheet.date,
                                "project": timesheet.project_id.name,
                                "task": timesheet.task_id.name,
                                "worked_hours": timesheet.unit_amount,
                            },
                        )
                    )
            payslip.combined_records = combined_lines

    def action_create_vendor_bill(self):
        for payslip in self:
            _logger.info(
                f"Starting vendor bill creation for {payslip.employee_id.name}..."
            )

            # Ensure the payslip is in the correct status
            if payslip.status != "employee_confirm":
                _logger.warning(
                    f"Cannot create vendor bill for {payslip.employee_id.name}: Payslip is not in 'employee_confirm' status."
                )
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Error",
                        "message": "You can only create a vendor bill after the Employee Confirm stage.",
                        "type": "danger",
                        "sticky": False,
                    },
                }

            # Ensure the employee has a home address
            if not payslip.employee_id.sudo().address_home_id:
                _logger.error(
                    f"No home address found for employee {payslip.employee_id.name}."
                )
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Error",
                        "message": f"The employee '{payslip.employee_id.name}' does not have a home address set. Please configure it before creating a vendor bill.",
                        "type": "danger",
                        "sticky": False,
                    },
                }

            try:
                # Find the salary expense account
                _logger.info("Searching for salary expense account (code: 630000)...")
                salary_expense_account = self.env["account.account"].search(
                    [("code", "=", "630000")], limit=1
                )
                if not salary_expense_account:
                    _logger.error("Salary expense account (code: 630000) not found.")
                    raise UserError(
                        "The Salary Expenses account (code: 630000) is not found in the system. Please configure it before proceeding."
                    )
                _logger.info(
                    f"Found salary expense account: {salary_expense_account.name} (ID: {salary_expense_account.id})."
                )

                # Find the accounts payable account
                _logger.info("Searching for accounts payable account (code: 211000)...")
                accounts_payable_account = self.env["account.account"].search(
                    [("code", "=", "211000")], limit=1
                )
                if not accounts_payable_account:
                    _logger.error("Accounts payable account (code: 211000) not found.")
                    raise UserError(
                        "The Accounts Payable account (code: 211000) is not found in the system. Please configure it before proceeding."
                    )
                _logger.info(
                    f"Found accounts payable account: {accounts_payable_account.name} (ID: {accounts_payable_account.id})."
                )

                # Generate a unique reference for the bill
                employee_firstname = payslip.employee_id.name.split(" ")[0]
                bill_ref = f"SALARY/{fields.Date.today()}/{employee_firstname}"
                _logger.info(f"Generated bill reference: {bill_ref}")

                # Vendor Bill Creation
                vendor_bill_vals = {
                    "move_type": "in_invoice",
                    "partner_id": payslip.employee_id.address_home_id.id,
                    "invoice_date": fields.Date.today(),
                    "ref": bill_ref,  # Use ref instead of name to avoid sequence conflicts
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "name": f"Salary for {payslip.date_from} to {payslip.date_to}",
                                "quantity": 1,
                                "price_unit": payslip.total_salary,
                                "account_id": salary_expense_account.id,
                                "debit": payslip.total_salary,
                                "credit": 0.0,  # Debit entry for salary expense
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "name": f"Payable for {payslip.date_from} to {payslip.date_to}",
                                "quantity": 1,
                                "price_unit": -payslip.total_salary,
                                "account_id": accounts_payable_account.id,
                                "debit": 0.0,
                                "credit": payslip.total_salary,  # Credit entry for accounts payable
                            },
                        ),
                    ],
                }
                _logger.info(f"Vendor bill values prepared: {vendor_bill_vals}")

                # Create the vendor bill
                vendor_bill = self.env["account.move"].create(vendor_bill_vals)
                _logger.info(f"Vendor bill created with ID: {vendor_bill.id}")

                # Always link the latest created bill
                payslip.vendor_bill_id = vendor_bill.id
                _logger.info(
                    f"Linked new vendor bill {vendor_bill.id} to payslip for {payslip.employee_id.name}."
                )

                # Show success notification
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Vendor Bill Created",
                        "message": f"Vendor bill created for {payslip.employee_id.name} with reference {bill_ref}.",
                        "type": "success",
                        "sticky": False,
                    },
                }

            except Exception as e:
                _logger.error(
                    f"Error creating vendor bill for {payslip.employee_id.name}: {e}",
                    exc_info=True,
                )
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Error",
                        "message": f"An error occurred while creating the vendor bill: {str(e)}",
                        "type": "danger",
                        "sticky": False,
                    },
                }

    @api.model
    def create(self, vals):
        # Create the payslip
        payslip = super(HrPayslip, self).create(vals)

        # Retrieve attendance data for the employee
        employee_id = vals.get("employee_id")
        if employee_id:
            attendance_data = self._get_employee_attendance_data(employee_id)

            # Save attendance records into the payslip.attendance model
            self.env["payslip.attendance"].create_attendance_records(
                payslip_id=payslip.id,
                employee_id=employee_id,
                attendance_data=attendance_data,
            )

        return payslip

    def _get_employee_attendance_data(self, employee_id):
        """
        Retrieve attendance data for the given employee.

        This is a placeholder method. Replace it with actual logic to fetch attendance records.

        :param employee_id: ID of the employee.
        :return: List of dictionaries with attendance data.
        """
        # Example data - replace with actual attendance fetching logic
        return [
            {
                "date": "2023-12-01",
                "check_in": "2023-12-01 08:30:00",
                "check_out": "2023-12-01 17:30:00",
                "approval_status": "yes",
            },
            {
                "date": "2023-12-02",
                "check_in": "2023-12-02 09:00:00",
                "check_out": "2023-12-02 18:00:00",
                "approval_status": "no",
            },
        ]


class HrPayslipCombinedRecord(models.Model):
    _name = "hr.payslip.combined.record"
    _description = "Payslip Combined Record"

    payslip_id = fields.Many2one(
        "hr.payslip", string="Payslip", ondelete="cascade", required=True
    )
    type = fields.Selection(
        [("attendance", "Attendance"), ("timesheet", "Timesheet")],
        string="Type",
        required=True,
    )
    date = fields.Date(string="Date", required=True)
    check_in = fields.Datetime(string="Check In")
    check_out = fields.Datetime(string="Check Out")
    worked_hours = fields.Float(string="Worked Hours")
    approved = fields.Boolean(string="Approved")
    project = fields.Char(string="Project")
    task = fields.Char(string="Task")
