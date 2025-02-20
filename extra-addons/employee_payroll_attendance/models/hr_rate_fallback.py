# import requests
# from odoo import models, fields, api


# class HrRateFallback(models.Model):
#     _name = "hr.rate.fallback"
#     _description = "Rate Fallback for USD to VND"

#     date = fields.Date(string="Date", required=True, default=fields.Date.context_today)
#     rate_usd_vnd = fields.Float(string="USD to VND Rate", required=True, digits=(12, 4))
#     approved = fields.Boolean(string="Approved", default=False)

#     @api.model
#     def update_exchange_rate(self):
#         """Tự động lấy tỷ giá và tạo bản ghi mới"""
#         url = "https://api.exchangerate-api.com/v4/latest/USD"
#         response = requests.get(url)
#         if response.status_code == 200:
#             data = response.json()
#             vnd_rate = data["rates"].get("VND", 0)
#             if vnd_rate:
#                 self.create({"rate_usd_vnd": vnd_rate, "date": fields.Date.today()})

#     def action_approve(self):
#         """Khi click vào Approve, tỷ giá sẽ áp dụng cho tất cả Payslips cùng tháng"""
#         for record in self:
#             month_start = record.date.replace(day=1)
#             month_end = month_start.replace(
#                 month=month_start.month % 12 + 1, day=1
#             ) - fields.Date.timedelta(days=1)

#             payslips = self.env["hr.payslip"].search(
#                 [("date_from", ">=", month_start), ("date_to", "<=", month_end)]
#             )
#             payslips.write({"rate_usd_vnd": record.rate_usd_vnd})

#             # Đánh dấu là đã duyệt
#             record.approved = True
