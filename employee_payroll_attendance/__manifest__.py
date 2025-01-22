{
    "name": "Employee Payroll Based on Attendance Approval",
    "version": "1.0",
    "category": "Human Resources",
    "summary": "Calculate payroll based on approved attendance records",
    "description": "This module integrates attendance approval into payroll calculation in Odoo.",
    "author": "Your Name",
    "depends": [
        "hr_attendance",
        "sale_timesheet",
        "web",
        "base",
        "hr_timesheet",
    ],
    "assets": {
        "web.assets_backend": [
            "employee_payroll_attendance/static/src/css/custom_style.css",
            "employee_payroll_attendance/static/src/css/tree_view_sticky.css",
        ],
    },
    "data": [
        "security/ir.model.access.csv",
        "views/hr_attendance_payroll_views.xml",
        "views/hr_payslip_views.xml",
        "views/hr_employee_payslip_views.xml",
        "views/generate_salary_wizard_views.xml",
        "views/account_analytic_line_views.xml",
        "views/custom_report_layout.xml",
        "views/hr_payslip_views_update.xml",
        "views/menu_reporting.xml",
    ],
    "installable": True,
    "application": False,
}
