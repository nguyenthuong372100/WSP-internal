{
    'name': 'Custom Sale Timesheet',
    'version': '1.0',
    'summary': 'Custom modifications for Sale Timesheet module',
    'author': 'nguyenthuong',
    'depends': ['sale_timesheet'],  # Phải có module phụ thuộc hợp lệ
    'data': [
        'views/account_analytic_line_views.xml',  # Thêm file XML tại đây
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
