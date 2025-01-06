{
    'name': 'Custom Invoice Template',
    'version': '1.0',
    'author': 'nguyenthuongg',
    'depends': ['web','base'],  # Thêm các module liên quan
    'data': [
        'views/custom_report_layout.xml',  # Đường dẫn tệp XML
    ],
    'installable': True,
    'application': False,
}
