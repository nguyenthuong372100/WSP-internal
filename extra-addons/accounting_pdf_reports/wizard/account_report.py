# -*- coding: utf-8 -*-

from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)


class AccountingReport(models.TransientModel):
    _name = "accounting.report"
    _inherit = "account.common.report"
    _description = "Accounting Report"

    @api.model
    def _get_account_report(self):
        _logger.info("Fetching account report based on the active menu ID: %s", self._context.get('active_id'))
        try:
            reports = []
            if self._context.get('active_id'):
                menu = self.env['ir.ui.menu'].browse(self._context.get('active_id')).name
                _logger.debug("Active menu name: %s", menu)
                reports = self.env['account.financial.report'].search([('name', 'ilike', menu)])
                _logger.debug("Matched reports: %s", reports)
            return reports and reports[0] or False
        except Exception as e:
            _logger.error("Error fetching account report: %s", e)
            raise

    enable_filter = fields.Boolean(string='Enable Comparison')
    account_report_id = fields.Many2one('account.financial.report', string='Account Reports',
                                        required=True, default=_get_account_report)
    label_filter = fields.Char(string='Column Label', help="This label will be displayed on report to "
                                                           "show the balance computed for the given comparison filter.")
    filter_cmp = fields.Selection([('filter_no', 'No Filters'), ('filter_date', 'Date')],
                                  string='Filter by', required=True, default='filter_no')
    date_from_cmp = fields.Date(string='Date From')
    date_to_cmp = fields.Date(string='Date To')
    debit_credit = fields.Boolean(string='Display Debit/Credit Columns',
                                  help="This option allows you to get more details about "
                                       "the way your balances are computed."
                                       " Because it is space consuming, we do not allow to"
                                       " use it while doing a comparison.")

    def _build_comparison_context(self, data):
        _logger.info("Building comparison context with data: %s", data)
        try:
            result = {}
            result['journal_ids'] = 'journal_ids' in data['form'] and data['form']['journal_ids'] or False
            result['state'] = 'target_move' in data['form'] and data['form']['target_move'] or ''
            if data['form']['filter_cmp'] == 'filter_date':
                result['date_from'] = data['form']['date_from_cmp']
                result['date_to'] = data['form']['date_to_cmp']
                result['strict_range'] = True
            _logger.debug("Comparison context result: %s", result)
            return result
        except Exception as e:
            _logger.error("Error building comparison context: %s", e)
            raise

    def check_report(self):
        _logger.info("Checking report for user: %s (ID: %s)", self.env.user.name, self.env.user.id)
        try:
            res = super(AccountingReport, self).check_report()
            data = {}
            data['form'] = self.read(['account_report_id', 'date_from_cmp', 'date_to_cmp', 'journal_ids', 'filter_cmp', 'target_move'])[0]
            _logger.debug("Report form data read: %s", data)
            for field in ['account_report_id']:
                if isinstance(data['form'][field], tuple):
                    data['form'][field] = data['form'][field][0]
            comparison_context = self._build_comparison_context(data)
            res['data']['form']['comparison_context'] = comparison_context
            _logger.info("Report check completed successfully with context: %s", comparison_context)
            return res
        except Exception as e:
            _logger.error("Error during report check: %s", e)
            raise

    def _print_report(self, data):
        _logger.info("Printing report with data: %s", data)
        try:
            data['form'].update(self.read(['date_from_cmp', 'debit_credit', 'date_to_cmp', 'filter_cmp', 'account_report_id', 'enable_filter', 'label_filter', 'target_move'])[0])
            _logger.debug("Updated data for printing: %s", data)
            return self.env.ref('accounting_pdf_reports.action_report_financial').report_action(self, data=data, config=False)
        except Exception as e:
            _logger.error("Error during report printing: %s", e)
            raise
