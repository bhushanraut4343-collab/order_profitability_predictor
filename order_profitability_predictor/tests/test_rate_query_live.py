"""Opt-in read-only database regression; no fixtures, inserts or migrations.

Run the existing site-initialized unittest command with OPP_RUN_SITE_TESTS=1.
The selected site must already have ERPNext installed. Database reads run in a
READ ONLY transaction; this suite never needs a real purchase transaction.
"""

import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import frappe

from order_profitability_predictor.risks import annotate_risks, rate_evidence


@unittest.skipUnless(os.environ.get("OPP_RUN_SITE_TESTS") == "1", "Opt-in live database test")
class PurchaseRateQueryLiveTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.original_user = frappe.session.user
		frappe.connect()
		frappe.set_user("Administrator")
		frappe.db.sql("START TRANSACTION READ ONLY")

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		frappe.set_user(cls.original_user)

	def basis(self):
		return dict(
			source="Last Purchase Rate",
			item_code="OPP-QUERY-NO-ITEM-" + uuid4().hex,
			company="OPP-NONEXISTENT-COMPANY-" + uuid4().hex,
			uom="Nos",
			base_rate=100,
			modified="2026-10-24 23:59:59",
		)

	def test_real_queries_execute_for_all_three_purchase_doctypes(self):
		# wraps observes calls but executes the real permission-aware DB query.
		with patch("frappe.get_list", wraps=frappe.get_list) as actual_query:
			self.assertIsNone(rate_evidence(self.basis()))
		calls = [
			call
			for call in actual_query.call_args_list
			if call.args and call.args[0] in ("Purchase Order", "Purchase Receipt", "Purchase Invoice")
		]
		self.assertEqual(
			[call.args[0] for call in calls], ["Purchase Order", "Purchase Receipt", "Purchase Invoice"]
		)
		for call in calls:
			self.assertIn("items.item_code", call.kwargs["filters"])

	def test_real_no_evidence_produces_unknown_date_warning(self):
		result = dict(
			warnings=[],
			items=[dict(rate_basis=self.basis())],
			is_complete=False,
			expected_gross_margin_percentage=None,
		)
		result = annotate_risks(result)
		self.assertIsNone(result["items"][0]["rate_date_evidence"])
		self.assertTrue(
			any(r["code"] == "unknown_rate_date" and r["severity"] == "Warning" for r in result["risks"])
		)
