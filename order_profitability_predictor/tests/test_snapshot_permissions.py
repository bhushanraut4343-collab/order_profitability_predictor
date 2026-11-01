"""Unit coverage for the source-aware permission hooks, including invalid links."""

import unittest
from unittest.mock import Mock, patch

import frappe

from order_profitability_predictor.permissions import (
	analysis_query_conditions,
	has_analysis_permission,
	prevent_analysis_sharing,
)

MODULE = "order_profitability_predictor.permissions"


class SnapshotPermissionTests(unittest.TestCase):
	def test_missing_or_invalid_reference_denied(self):
		for reference in (None, "", "  ", ["Q-1"]):
			with self.subTest(reference=reference):
				self.assertFalse(
					has_analysis_permission(frappe._dict(quotation=reference), user="staff@example.com")
				)
		with patch(MODULE + ".frappe.get_doc", side_effect=frappe.DoesNotExistError):
			self.assertFalse(
				has_analysis_permission(frappe._dict(quotation="MISSING"), user="staff@example.com")
			)

	def test_guest_always_denied(self):
		self.assertFalse(has_analysis_permission(frappe._dict(quotation="Q-1"), user="Guest"))
		self.assertEqual(analysis_query_conditions(user="Guest"), "1=0")

	def test_document_specific_access_uses_requested_user(self):
		quotation = Mock()
		with (
			patch(MODULE + ".frappe.get_doc", return_value=quotation),
			patch(MODULE + ".frappe.has_permission", return_value=False) as check,
		):
			self.assertFalse(
				has_analysis_permission(frappe._dict(quotation="Q-1"), user="restricted@example.com")
			)
			check.assert_called_once_with("Quotation", "read", doc=quotation, user="restricted@example.com")

	def test_query_uses_source_permissions_without_running_or_enumerating(self):
		query = Mock()
		query.get_sql.return_value = "SELECT `name` FROM `tabQuotation` WHERE `owner`='staff'"
		qb = Mock()
		qb.get_query.return_value = query
		with patch(MODULE + ".frappe.qb", qb):
			condition = analysis_query_conditions(user="staff@example.com")
		qb.get_query.assert_called_once_with(
			"Quotation", fields=["name"], user="staff@example.com", ignore_permissions=False
		)
		self.assertIn("`tabProfitability Analysis`.`quotation` IN (SELECT", condition)
		query.run.assert_not_called()

	def test_query_without_source_permission_is_always_false(self):
		qb = Mock()
		qb.get_query.side_effect = frappe.PermissionError
		with patch(MODULE + ".frappe.qb", qb):
			self.assertEqual(analysis_query_conditions(user="staff@example.com"), "1=0")

	def test_only_snapshot_sharing_is_blocked(self):
		with self.assertRaises(frappe.PermissionError):
			prevent_analysis_sharing(frappe._dict(share_doctype="Profitability Analysis"))
		prevent_analysis_sharing(frappe._dict(share_doctype="Quotation"))
