{
    'name': 'Payslip Timesheet Integration',
    'version': '1.0',
    'summary': 'Display Timesheets in Payslip Attendance Records',
    'description': 'Automatically fetch and display timesheets in the attendance section of payslips.',
    'author': 'nguyenthuongg',
    'depends': ['employee_payroll_attendance', 'hr_timesheet','hr_attendance'],
    'data': [
        'views/hr_payslip_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
