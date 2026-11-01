"""Isolated read-only engine tests; no site fixtures or database writes."""

import unittest
from unittest.mock import Mock, patch

import frappe

from order_profitability_predictor.profitability import calculate_quotation_profitability


class Doc(frappe._dict):
	def __getattribute__(self, key):
		if key == "items" and "items" in self:
			return self["items"]
		return super().__getattribute__(key)

	def check_permission(self, permission):
		assert permission == "read"


def bom(name="BOM-A", item="A", quantity=2, cost=20):
	return Doc(
		name=name,
		item=item,
		company="Company",
		docstatus=1,
		is_active=1,
		set_rate_of_sub_assembly_item_based_on_bom=1,
		quantity=quantity,
		process_loss_qty=0,
		modified="2026-01-01",
		items=[Doc(item_code="RAW", qty=2, stock_qty=2, base_rate=cost / 2, base_amount=cost)],
		base_operating_cost=10,
		with_operations=1,
		operations=[Doc(operation="Assembly", base_hour_rate=10, time_in_mins=60, base_operating_cost=10)],
	)


def item(code="A", qty=4, net=100, fields=(), **kwargs):
	return Doc(idx=1, item_code=code, stock_qty=qty, base_net_amount=net, meta=Doc(fields=fields), **kwargs)


class ProfitabilityTests(unittest.TestCase):
	def run_engine(self, items, boms=None, defaults=None):
		boms = boms if boms is not None else {"BOM-A": bom()}
		defaults = defaults if defaults is not None else {"A": "BOM-A"}
		quotation = Doc(name="Q-TEST", company="Company", items=items)

		def get_doc(doctype, name):
			return quotation if doctype == "Quotation" else boms[name]

		with (
			patch("order_profitability_predictor.profitability.frappe.get_doc", side_effect=get_doc),
			patch(
				"order_profitability_predictor.profitability.frappe.db",
				Mock(exists=lambda dt, n: n in boms, get_value=lambda dt, f, field: defaults.get(f["item"])),
			),
			patch("order_profitability_predictor.profitability.frappe.get_cached_value", return_value="INR"),
		):
			return calculate_quotation_profitability("Q-TEST")

	def test_multiple_items_and_quantity_scaling(self):
		result = self.run_engine([item(), item(qty=2, net=50)])
		self.assertTrue(result["is_complete"])
		self.assertEqual(result["net_selling_value"], 150)
		self.assertEqual(result["estimated_total_cost"], 90)
		self.assertEqual(result["expected_gross_profit"], 60)
		self.assertEqual(result["expected_gross_margin_percentage"], 40)

	def test_missing_bom_suppresses_profit(self):
		result = self.run_engine([item(), item(code="UNKNOWN")])
		self.assertFalse(result["is_complete"])
		self.assertIsNone(result["estimated_total_cost"])
		self.assertIsNone(result["expected_gross_profit"])
		self.assertEqual(result["known_items_cost"], 60)

	def test_missing_material_rate(self):
		b = bom(cost=0)
		result = self.run_engine([item()], {"BOM-A": b})
		self.assertFalse(result["is_complete"])
		self.assertIsNone(result["expected_gross_margin_percentage"])

	def test_missing_operation_data(self):
		b = bom()
		b.operations[0].time_in_mins = None
		self.assertFalse(self.run_engine([item()], {"BOM-A": b})["is_complete"])

	def test_subassembly_includes_operations_without_double_counting(self):
		parent = bom()
		parent.items = [Doc(item_code="SUB", qty=1, stock_qty=1, bom_no="BOM-SUB", base_amount=15)]
		child = bom("BOM-SUB", "SUB", quantity=1, cost=5)
		result = self.run_engine([item(qty=2)], {"BOM-A": parent, "BOM-SUB": child})
		self.assertEqual(result["estimated_total_cost"], 25)

	def test_cycle_is_incomplete(self):
		b = bom()
		b.items = [Doc(item_code="A", qty=1, stock_qty=1, bom_no="BOM-A")]
		self.assertFalse(self.run_engine([item()], {"BOM-A": b})["is_complete"])

	def test_explicit_bom_and_stock_quantity(self):
		fields = [Doc(fieldname="custom_bom", fieldtype="Link", options="BOM")]
		result = self.run_engine(
			[item(qty=6, fields=fields, custom_bom="BOM-X")], {"BOM-X": bom("BOM-X")}, defaults={}
		)
		self.assertEqual(result["estimated_total_cost"], 90)

	def test_process_loss(self):
		b = bom(quantity=3)
		b.process_loss_qty = 1
		self.assertEqual(self.run_engine([item(qty=2)], {"BOM-A": b})["estimated_total_cost"], 30)

	def test_invalid_bom_company(self):
		b = bom()
		b.company = "Other"
		self.assertFalse(self.run_engine([item()], {"BOM-A": b})["is_complete"])

	def test_alternatives_excluded_and_zero_selling_margin(self):
		result = self.run_engine([item(net=0), item(is_alternative=1)])
		self.assertEqual(len(result["items"]), 1)
		self.assertEqual(result["net_selling_value"], 0)
		self.assertIsNone(result["expected_gross_margin_percentage"])

	def test_secondary_allocation_flagged(self):
		b = bom()
		b.secondary_items = [Doc(item_code="BYPRODUCT")]
		self.assertFalse(self.run_engine([item()], {"BOM-A": b})["is_complete"])

	def test_unconfigured_operations_suppress_profit(self):
		b = bom()
		b.with_operations = 0
		result = self.run_engine([item()], {"BOM-A": b})
		self.assertFalse(result["is_complete"])
		self.assertIsNone(result["estimated_total_cost"])
		self.assertIsNone(result["expected_gross_profit"])
		self.assertIsNone(result["expected_gross_margin_percentage"])
		self.assertTrue(any("no operation costing configured" in w for w in result["warnings"]))

	def test_empty_quotation_has_clear_warning(self):
		result = self.run_engine([])
		self.assertFalse(result["is_complete"])
		self.assertIsNone(result["expected_gross_profit"])
		self.assertTrue(any("No non-alternative" in w for w in result["warnings"]))


if __name__ == "__main__":
	unittest.main()
