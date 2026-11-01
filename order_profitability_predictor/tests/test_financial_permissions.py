"""Field-policy units complement real Property Setter/API tests on disposable sites."""

import unittest
from unittest.mock import Mock, patch

import frappe

from order_profitability_predictor.financial_permissions import (
	DENIED,
	bom_fields,
	fields_readable,
	require_fields,
)

MODULE = "order_profitability_predictor.financial_permissions"


class FinancialPermissionTests(unittest.TestCase):
	def meta(self, allowed=("base_rate",), mask=False, levels=()):
		meta = Mock()
		df = frappe._dict(fieldname="base_rate", permlevel=1, mask=mask, fieldtype="Currency")
		meta.get_field.side_effect = lambda name: df if name == "base_rate" else None
		meta.get_permitted_fieldnames.return_value = list(allowed)
		meta.get_permlevel_access.return_value = list(levels)
		return meta

	def test_parent_and_requested_user_are_passed_to_standard_api(self):
		meta = self.meta()
		with patch(MODULE + ".frappe.get_meta", return_value=meta):
			self.assertTrue(fields_readable("BOM Item", ["base_rate"], parenttype="BOM", user="staff"))
		meta.get_permitted_fieldnames.assert_called_once_with(
			parenttype="BOM", user="staff", permission_type="read"
		)
		meta.get_permlevel_access.assert_any_call("read", parenttype="BOM", user="staff")
		meta.get_permlevel_access.assert_any_call("mask", parenttype="BOM", user="staff")

	def test_read_permission_without_mask_permission_denies(self):
		with patch(MODULE + ".frappe.get_meta", return_value=self.meta(mask=True)):
			self.assertFalse(fields_readable("BOM Item", ["base_rate"], parenttype="BOM", user="staff"))

	def test_mask_permission_does_not_replace_read_permission(self):
		with patch(MODULE + ".frappe.get_meta", return_value=self.meta(allowed=(), mask=True, levels=(1,))):
			self.assertFalse(fields_readable("BOM Item", ["base_rate"], parenttype="BOM", user="staff"))

	def test_both_read_and_mask_permission_allow(self):
		with patch(MODULE + ".frappe.get_meta", return_value=self.meta(mask=True, levels=(1,))):
			self.assertTrue(fields_readable("BOM Item", ["base_rate"], parenttype="BOM", user="staff"))

	def test_absent_required_field_denies_but_explicit_optional_is_supported(self):
		with patch(MODULE + ".frappe.get_meta", return_value=self.meta()):
			self.assertFalse(fields_readable("BOM", ["missing"], user="staff"))
			self.assertTrue(fields_readable("BOM", ["missing"], user="staff", optional=("missing",)))

	def test_denial_is_generic(self):
		with (
			patch(MODULE + ".fields_readable", return_value=False),
			self.assertRaises(frappe.PermissionError) as error,
		):
			require_fields("BOM Item", ["base_rate"], user="staff")
		self.assertEqual(str(error.exception), DENIED)

	def test_guest_denied_even_for_empty_fields(self):
		self.assertFalse(fields_readable("BOM", (), user="Guest"))

	def test_unused_operation_branch_is_not_required(self):
		bom = frappe._dict(with_operations=0, fg_based_operating_cost=1)
		bom["items"] = []
		with patch(MODULE + ".require_fields") as guard:
			bom_fields(bom)
		self.assertNotIn("BOM Operation", [call.args[0] for call in guard.call_args_list])

	def test_operation_row_branch_checks_child_fields(self):
		bom = frappe._dict(with_operations=1, operations=[frappe._dict(set_cost_based_on_bom_qty=1)])
		bom["items"] = []
		with patch(MODULE + ".require_fields") as guard:
			bom_fields(bom)
		self.assertTrue(
			any(
				call.args[0] == "BOM Operation" and "base_cost_per_unit" in call.args[1]
				for call in guard.call_args_list
			)
		)

	def test_table_container_uses_standard_read_levels(self):
		meta = self.meta(allowed=(), levels=(1,))
		meta.get_field.side_effect = None
		meta.get_field.return_value = frappe._dict(fieldtype="Table", permlevel=1, mask=0)
		with patch(MODULE + ".frappe.get_meta", return_value=meta):
			self.assertTrue(fields_readable("BOM", ["items"], user="staff"))
		meta.get_permlevel_access.return_value = [0]
		with patch(MODULE + ".frappe.get_meta", return_value=meta):
			self.assertFalse(fields_readable("BOM", ["items"], user="staff"))
