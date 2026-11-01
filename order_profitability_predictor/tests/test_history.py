import copy
import json
import unittest
from unittest.mock import Mock, patch

import frappe

from order_profitability_predictor.history import (
	compare_quotation_analysis,
	comparison_changes,
	get_quotation_history,
)

MODULE = "order_profitability_predictor.history"


class HistoryTests(unittest.TestCase):
	def setUp(self):
		self.saved = dict(
			quotation="Q-1",
			company="Company",
			currency="INR",
			is_complete=True,
			net_selling_value=1200,
			estimated_total_cost=720,
			expected_gross_profit=480,
			expected_gross_margin_percentage=40,
		)
		self.doc = Mock()
		self.doc.name = "SNAP-1"
		self.doc.quotation = "Q-1"
		self.doc.company = "Company"
		self.doc.base_currency = "INR"
		self.doc.analyzed_at = "2026-10-24 10:00:00"
		self.doc.analyzed_by = "Administrator"
		self.doc.snapshot_json = json.dumps(self.saved)

	def test_changes_and_margin_direction(self):
		for cost, profit, margin, direction in [
			(700, 500, 42, "increased"),
			(740, 460, 38, "decreased"),
			(720, 480, 40, "unchanged"),
		]:
			current = dict(
				self.saved,
				estimated_total_cost=cost,
				expected_gross_profit=profit,
				expected_gross_margin_percentage=margin,
			)
			changes = comparison_changes(self.saved, current)
			self.assertEqual(changes["estimated_total_cost"], cost - 720)
			self.assertEqual(changes["expected_gross_profit"], profit - 480)
			self.assertEqual(changes["expected_gross_margin_percentage"], margin - 40)
			self.assertEqual(changes["margin_direction"], direction)

	def test_incomplete_and_null_never_zero(self):
		for side in ("old", "new"):
			old, new = copy.deepcopy(self.saved), copy.deepcopy(self.saved)
			(old if side == "old" else new).update(is_complete=False, estimated_total_cost=None)
			changes = comparison_changes(old, new)
			self.assertIsNone(changes["estimated_total_cost"])
			self.assertIsNone(changes["expected_gross_profit"])
			self.assertEqual(changes["margin_direction"], "not_available")
		changes = comparison_changes(self.saved, dict(self.saved, expected_gross_margin_percentage=None))
		self.assertIsNone(changes["expected_gross_margin_percentage"])

	def test_different_currency_or_company_not_comparable(self):
		for key in ("currency", "company"):
			changes = comparison_changes(self.saved, dict(self.saved, **{key: "Other"}))
			self.assertIsNone(changes["estimated_total_cost"])

	def test_zero_is_known_value(self):
		changes = comparison_changes(dict(self.saved, expected_gross_profit=0), self.saved)
		self.assertEqual(changes["expected_gross_profit"], 480)

	def test_quotation_permission_required_before_history(self):
		quote = Mock()
		quote.check_permission.side_effect = frappe.PermissionError
		with (
			patch("frappe.session", frappe._dict(user="User")),
			patch(MODULE + ".frappe.get_doc", return_value=quote),
			patch(MODULE + ".frappe.get_list") as listing,
		):
			with self.assertRaises(frappe.PermissionError):
				get_quotation_history("Q-1")
			listing.assert_not_called()

	def test_analysis_doctype_permission_required(self):
		with (
			patch("frappe.session", frappe._dict(user="User")),
			patch(MODULE + ".frappe.get_doc", return_value=Mock()),
			patch(MODULE + ".frappe.has_permission", side_effect=frappe.PermissionError),
			patch(MODULE + ".frappe.get_list") as listing,
		):
			with self.assertRaises(frappe.PermissionError):
				get_quotation_history("Q-1")
			listing.assert_not_called()

	def test_guest_denied(self):
		with patch("frappe.session", frappe._dict(user="Guest")):
			with self.assertRaises(frappe.PermissionError):
				get_quotation_history("Q-1")
			with self.assertRaises(frappe.PermissionError):
				compare_quotation_analysis("Q-1", "SNAP-1")

	def test_ordering_and_pagination_query(self):
		with (
			patch(MODULE + "._authorize"),
			patch(
				MODULE + ".frappe.get_list", return_value=[frappe._dict(name=str(i)) for i in range(21)]
			) as listing,
			patch(MODULE + ".frappe.get_doc", return_value=self.doc),
		):
			result = get_quotation_history("Q-1", 20)
			self.assertEqual(len(result["analyses"]), 20)
			self.assertTrue(result["has_more"])
			self.assertEqual(
				listing.call_args.kwargs["order_by"], "analyzed_at desc, creation desc, name desc"
			)
			self.assertEqual(listing.call_args.kwargs["limit_start"], 20)
			self.assertEqual(listing.call_args.kwargs["filters"], {"quotation": "Q-1"})

	def test_no_history(self):
		with patch(MODULE + "._authorize"), patch(MODULE + ".frappe.get_list", return_value=[]):
			result = get_quotation_history("Q-1")
			self.assertEqual(result["analyses"], [])
			self.assertFalse(result["has_more"])

	def test_cross_quotation_reference_denied(self):
		self.doc.quotation = "Q-OTHER"
		with (
			patch(MODULE + "._authorize"),
			patch(MODULE + ".frappe.get_doc", return_value=self.doc),
			patch(MODULE + ".calculate_quotation_profitability") as calculate,
		):
			with self.assertRaises(frappe.PermissionError):
				compare_quotation_analysis("Q-1", "SNAP-1")
			calculate.assert_not_called()

	def test_snapshot_document_permission_denied(self):
		self.doc.check_permission.side_effect = frappe.PermissionError
		with (
			patch(MODULE + "._authorize"),
			patch(MODULE + ".frappe.get_doc", return_value=self.doc),
			patch(MODULE + ".calculate_quotation_profitability") as calculate,
		):
			with self.assertRaises(frappe.PermissionError):
				compare_quotation_analysis("Q-1", "SNAP-1")
			calculate.assert_not_called()

	def test_tampered_snapshot_reference_rejected(self):
		self.doc.snapshot_json = json.dumps(dict(self.saved, quotation="Q-OTHER"))
		with patch(MODULE + "._authorize"), patch(MODULE + ".frappe.get_doc", return_value=self.doc):
			with self.assertRaises(frappe.ValidationError):
				compare_quotation_analysis("Q-1", "SNAP-1")

	def test_current_recalculated_and_snapshot_unchanged(self):
		before = self.doc.snapshot_json
		with (
			patch(MODULE + "._authorize"),
			patch(MODULE + ".frappe.get_doc", return_value=self.doc),
			patch(
				MODULE + ".calculate_quotation_profitability",
				return_value=dict(self.saved, estimated_total_cost=750),
			) as calculate,
			patch(MODULE + ".now_datetime", return_value="2026-10-24 12:00:00"),
		):
			result = compare_quotation_analysis("Q-1", "SNAP-1")
			self.assertEqual(result["changes"]["estimated_total_cost"], 30)
			self.assertEqual(result["historical"]["estimated_total_cost"], 720)
			calculate.assert_called_once_with("Q-1")
			self.assertEqual(self.doc.snapshot_json, before)
			self.doc.save.assert_not_called()

	def test_endpoints_authenticated_post_only(self):
		for function in (get_quotation_history, compare_quotation_analysis):
			self.assertIn(function, frappe.whitelisted)
			self.assertNotIn(function, frappe.guest_methods)
			self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[function], ["POST"])

	def test_invalid_pagination_and_analysis_name(self):
		with patch(MODULE + "._authorize"):
			for start in (-1, "bad"):
				with self.assertRaises(frappe.ValidationError):
					get_quotation_history("Q-1", start)
			with self.assertRaises(frappe.ValidationError):
				compare_quotation_analysis("Q-1", "")
