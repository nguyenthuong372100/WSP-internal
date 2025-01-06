# -*- coding: utf-8 -*-

from odoo import fields, models, api
import logging

_logger = logging.getLogger(__name__)


class AccountBalanceReport(models.TransientModel):
    _name = 'account.balance.report'
    _inherit = "account.common.account.report"
    _description = 'Trial Balance Report'

    journal_ids = fields.Many2many(
        'account.journal', 'account_balance_report_journal_rel',
        'account_id', 'journal_id',
        string='Journals', required=True, default=[]
    )
    analytic_account_ids = fields.Many2many(
        'account.analytic.account',
        'account_trial_balance_analytic_rel',
        string='Analytic Accounts'
    )

    def _get_report_data(self, data):
        _logger.info("Fetching report data for model: %s with IDs: %s", data['model'], data.get('ids', []))
        _logger.info("User: %s (ID: %s), Groups: %s", self.env.user.name, self.env.user.id, self.env.user.groups_id.mapped('name'))
        _logger.info("Context: %s", self._context)

        try:
            data = self.pre_print_report(data)
            records = self.env[data['model']].browse(data.get('ids', []))
            _logger.info("Successfully fetched records: %s", records)
            return records, data
        except Exception as e:
            _logger.error("Permission issue or error fetching report data: %s", e)
            raise

    def _print_report(self, data):
        _logger.info("Initiating report print for data: %s", data)

        try:
            records, data = self._get_report_data(data)
            _logger.info("Records for report generation: %s", records)
            return self.env.ref('accounting_pdf_reports.action_report_trial_balance').report_action(records, data=data)
        except Exception as e:
            _logger.error("Error during report generation: %s", e)
            raise
