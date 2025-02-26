import requests
import xml.etree.ElementTree as ET
import logging
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HrPayslipUpdateRateWizard(
    models.TransientModel
):  # Phải là TransientModel để không lưu trữ dữ liệu vĩnh viễn
    _name = "hr.payslip.update.rate.wizard"
    _description = "Update Rate Fallback Wizard"

    currency_rate_fallback = fields.Float(string="USD Buy Transfer Rate")

    def fetch_usd_exchange_rate(self):
        """Fetch USD exchange rate from Vietcombank XML API and return value"""
        url = "https://portal.vietcombank.com.vn/UserControls/TVPortal.TyGia/pXML.aspx"
        headers = {"User-Agent": "Mozilla/5.0"}

        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                _logger.error(
                    f"Failed to fetch exchange rate, status code: {response.status_code}"
                )
                return 0.0

            # Parse XML response
            root = ET.fromstring(response.content)
            for item in root.findall("Exrate"):
                if item.get("CurrencyCode") == "USD":
                    return float(item.get("Transfer").replace(",", ""))

            _logger.warning("USD exchange rate not found in XML response.")
            return 0.0

        except Exception as e:
            _logger.error(f"Error fetching exchange rate: {e}")
            return 0.0

    def action_update_rate(self):
        """Fetch latest exchange rate and update the wizard"""
        new_rate = self.fetch_usd_exchange_rate()

        if new_rate <= 0:
            raise UserError("Failed to fetch a valid exchange rate.")

        # Cập nhật giá trị vào wizard
        self.write({"currency_rate_fallback": new_rate})
        _logger.info(f"Updated exchange rate in wizard: {new_rate}")

        # Không đóng wizard
        return {
            "type": "ir.actions.act_window",
            "res_model": "hr.payslip.update.rate.wizard",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
            "context": dict(self.env.context),
        }

    def action_apply_to_payslips(self):
        """Lấy giá trị currency_rate_fallback từ wizard và áp dụng cho các payslip đã chọn"""
        self.ensure_one()

        # Kiểm tra `active_ids` có dữ liệu không
        active_ids = self.env.context.get("active_ids", [])
        if not active_ids:
            raise UserError("No payslips selected to update.")

        if self.currency_rate_fallback <= 0:
            raise UserError("No valid exchange rate value found in wizard.")

        # Lấy danh sách payslips dựa trên `active_ids`
        payslips = self.env["hr.payslip"].browse(active_ids)

        if not payslips:
            raise UserError("No Payslip records found.")

        # Cập nhật `currency_rate_fallback` cho payslip
        payslips.sudo().write({"currency_rate_fallback": self.currency_rate_fallback})

        _logger.info(
            f"Applied exchange rate {self.currency_rate_fallback} to Payslips: {active_ids}"
        )

        # Gọi các phương thức cần cập nhật lại dữ liệu
        payslips._recalculate_total_salary()
        payslips._auto_update_attendance_records()
        payslips._onchange_salary_fields()
        payslips._onchange_bonus_vnd()

        return {"type": "ir.actions.act_window_close"}
