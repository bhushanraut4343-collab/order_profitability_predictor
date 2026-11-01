"""API boundary tests without writing business records."""

import unittest
from unittest.mock import Mock, patch

import frappe

from order_profitability_predictor.api import check_quotation_profitability


class ApiTests(unittest.TestCase):
	def setUp(self):
		self.session = patch(
			"order_profitability_predictor.api.frappe.session", frappe._dict(user="test@example.com")
		)
		self.session.start()
		self.addCleanup(self.session.stop)

	def test_read_permission_checked_before_calculation(self):
		doc = Mock(name="Quotation")
		doc.check_permission.side_effect = frappe.PermissionError("Denied")
		with (
			patch("order_profitability_predictor.api.frappe.get_doc", return_value=doc),
			patch("order_profitability_predictor.api.calculate_quotation_profitability") as calculate,
		):
			with self.assertRaises(frappe.PermissionError):
				check_quotation_profitability("Q-DENIED")
			doc.check_permission.assert_called_once_with("read")
			calculate.assert_not_called()

	def test_complete_and_incomplete_responses_are_preserved(self):
		for complete in (True, False):
			response = dict(
				quotation="Q-TEST",
				currency="INR",
				net_selling_value=1200,
				estimated_total_cost=720 if complete else None,
				expected_gross_profit=480 if complete else None,
				expected_gross_margin_percentage=40 if complete else None,
				is_complete=complete,
				items=[],
				warnings=[] if complete else ["Missing BOM"],
			)
			doc = Mock()
			doc.name = "Q-TEST"
			with (
				patch("order_profitability_predictor.api.frappe.get_doc", return_value=doc) as get_doc,
				patch(
					"order_profitability_predictor.api.calculate_quotation_profitability",
					return_value=response,
				) as calculate,
			):
				self.assertEqual(check_quotation_profitability("Q-TEST"), response)
				get_doc.assert_called_once_with("Quotation", "Q-TEST")
				doc.check_permission.assert_called_once_with("read")
				calculate.assert_called_once_with("Q-TEST")

	def test_guest_denied(self):
		with (
			patch("order_profitability_predictor.api.frappe.session", frappe._dict(user="Guest")),
			patch("order_profitability_predictor.api.frappe.get_doc") as get_doc,
		):
			with self.assertRaises(frappe.PermissionError):
				check_quotation_profitability("Q-TEST")
			get_doc.assert_not_called()

	def test_invalid_names_rejected(self):
		for name in (None, "", "  ", {"name": "Q-TEST"}):
			with self.subTest(name=name), self.assertRaises((frappe.ValidationError, TypeError)):
				check_quotation_profitability(name)

	def test_endpoint_requires_authentication_and_post(self):
		self.assertIn(check_quotation_profitability, frappe.whitelisted)
		self.assertNotIn(check_quotation_profitability, frappe.guest_methods)
		self.assertEqual(
			frappe.allowed_http_methods_for_whitelisted_func[check_quotation_profitability], ["POST"]
		)
