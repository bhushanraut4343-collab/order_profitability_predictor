import unittest
from unittest.mock import patch

import frappe

from order_profitability_predictor.risks import annotate_risks, minimum_margin, rate_evidence


class RiskTests(unittest.TestCase):
	def setUp(self):
		# These unit fixtures mock source documents; real permission coverage is separate.
		guard = patch("order_profitability_predictor.risks.fields_readable", return_value=True)
		guard.start()
		self.addCleanup(guard.stop)

	def result(self, complete=True, margin=40):
		return dict(
			is_complete=complete,
			expected_gross_margin_percentage=margin,
			warnings=["Saved BOM costs are estimates."] if complete else ["Row 1: Missing BOM."],
			items=[dict(components=[dict(rate_basis=dict(item_code="RAW"))])],
		)

	def annotate(self, result, evidence=None, threshold=15):
		with (
			patch("order_profitability_predictor.risks.rate_evidence", return_value=evidence),
			patch(
				"order_profitability_predictor.risks.frappe.conf",
				{"order_profitability_minimum_margin": threshold},
			),
			patch("order_profitability_predictor.risks.nowdate", return_value="2026-10-24"),
		):
			return annotate_risks(result)

	def test_classifications(self):
		result = self.annotate(self.result(False, None))
		self.assertEqual(result["risks"][0]["severity"], "Critical")
		result = self.annotate(self.result())
		self.assertEqual(result["risks"][0]["severity"], "Information")
		self.assertTrue(
			any(r["code"] == "unknown_rate_date" and r["severity"] == "Warning" for r in result["risks"])
		)

	def test_stale_and_recent_evidence(self):
		for date, expected in [("2026-01-01", "outdated_rate"), ("2026-10-01", "dated_rate_evidence")]:
			result = self.annotate(self.result(), dict(date=date, kind="price-list effective date"))
			self.assertIn(expected, [r["code"] for r in result["risks"]])

	def test_expired_rate(self):
		result = self.annotate(
			self.result(), dict(date="2026-10-01", kind="price-list effective date", valid_upto="2026-10-20")
		)
		self.assertIn("outdated_rate", [r["code"] for r in result["risks"]])

	def test_threshold_boundary_and_configuration(self):
		for margin, threshold, low in [(14.99, 15, True), (15, 15, False), (40, 45, True), (0, 0, False)]:
			result = self.annotate(self.result(margin=margin), threshold=threshold)
			self.assertEqual(any(r["code"] == "low_margin" for r in result["risks"]), low)

	def test_incomplete_never_has_low_margin(self):
		self.assertFalse(
			any(r["code"] == "low_margin" for r in self.annotate(self.result(False, 0))["risks"])
		)

	def test_default_and_invalid_configuration(self):
		with patch("order_profitability_predictor.risks.frappe.conf", {}):
			self.assertEqual(minimum_margin(), 15)
		for value in ("bad", float("nan"), -1, 101):
			with patch(
				"order_profitability_predictor.risks.frappe.conf",
				{"order_profitability_minimum_margin": value},
			):
				with self.assertRaises(frappe.ValidationError):
					minimum_margin()

	def test_price_list_matching_and_ambiguity(self):
		basis = dict(
			source="Price List",
			item_code="RAW",
			price_list="Buying",
			currency="INR",
			price_list_currency="INR",
			uom="Nos",
			rate=100,
			modified="2026-10-24 10:00:00",
		)
		record = frappe._dict(price_list_rate=100, valid_from="2026-01-01", valid_upto=None)
		for rows, known in [
			([record], True),
			([], False),
			([record, record], False),
			([frappe._dict(record, valid_from=None)], False),
			([frappe._dict(record, valid_from="2027-01-01")], False),
			([frappe._dict(record, price_list_rate=200)], False),
		]:
			with patch("order_profitability_predictor.risks.frappe.get_list", return_value=rows):
				self.assertEqual(rate_evidence(basis) is not None, known)

	def test_permission_denied_dates_remain_unknown(self):
		basis = dict(
			source="Price List",
			item_code="RAW",
			price_list="Buying",
			currency="INR",
			uom="Nos",
			modified="2026-10-24",
		)
		with patch("order_profitability_predictor.risks.frappe.get_list", side_effect=frappe.PermissionError):
			self.assertIsNone(rate_evidence(basis))

	def test_last_purchase_matching_date(self):
		basis = dict(
			source="Last Purchase Rate",
			item_code="RAW",
			company="Company",
			uom="Nos",
			base_rate=100,
			modified="2026-10-24",
		)
		doc = unittest.mock.Mock()
		doc.get.return_value = False
		doc.items = [frappe._dict(item_code="RAW", uom="Nos", base_net_rate=100)]
		parent = frappe._dict(name="PUR-1", transaction_date="2026-01-01", posting_date="2026-01-01")
		with (
			patch("order_profitability_predictor.risks.frappe.get_list", return_value=[parent]),
			patch("order_profitability_predictor.risks.frappe.get_doc", return_value=doc),
		):
			self.assertEqual(rate_evidence(basis)["date"], "2026-01-01")
