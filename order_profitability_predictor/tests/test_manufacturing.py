"""Manufacturing edge cases against ERPNext formulas and saved-cost semantics."""

import copy
import unittest
from decimal import Decimal
from unittest.mock import patch

from erpnext.manufacturing.doctype.bom.bom import BOM

from order_profitability_predictor.history import comparison_changes
from order_profitability_predictor.tests import test_profitability as fixtures
from order_profitability_predictor.tests.test_profitability import Doc, bom, item


class ManufacturingTests(unittest.TestCase):
	def calculate(self, rows, boms=None, defaults=None):
		return fixtures.ProfitabilityTests().run_engine(rows, boms, defaults)

	def test_multiple_raw_materials(self):
		b = bom()
		b.items.append(Doc(item_code="RAW-2", qty=3, stock_qty=3, base_rate=4, base_amount=12))
		result = self.calculate([item(qty=6)], {"BOM-A": b})
		self.assertEqual(result["estimated_total_cost"], float((Decimal(20) + 12 + 10) * 6 / 2))

	def test_material_and_selling_uom_conversion(self):
		b = bom(cost=120)
		b.items[0].update(qty=1, stock_qty=12, conversion_factor=12, base_rate=120, base_amount=120)
		q = item(qty=24, net=2400)
		q.update(qty=2, conversion_factor=12, uom="Box")
		result = self.calculate([q], {"BOM-A": b})
		self.assertEqual(result["estimated_total_cost"], 1560)
		self.assertEqual(result["net_selling_value"], 2400)

	def test_different_finished_items(self):
		result = self.calculate(
			[item(qty=4), item(code="B", qty=3, net=90)],
			{"BOM-A": bom(), "BOM-B": bom("BOM-B", "B", quantity=3, cost=8)},
			{"A": "BOM-A", "B": "BOM-B"},
		)
		self.assertEqual(result["estimated_total_cost"], 78)
		self.assertEqual(result["net_selling_value"], 190)

	def test_batch_operation_uses_erpnext_formula(self):
		b = bom(quantity=10)
		b.operations[0].update(
			set_cost_based_on_bom_qty=1, base_cost_per_unit=2, cost_per_unit=2, operating_cost=10
		)
		BOM.calculate_op_cost(b, update_hour_rate=False, save=False)
		self.assertEqual(b.base_operating_cost, 20)
		self.assertEqual(self.calculate([item(qty=5)], {"BOM-A": b})["estimated_total_cost"], 20)

	def test_operation_totals_disagree(self):
		b = bom()
		b.base_operating_cost = 999
		self.assertFalse(self.calculate([item()], {"BOM-A": b})["is_complete"])

	def test_finished_good_operations_follow_erpnext(self):
		b = bom(quantity=4)
		b.update(
			with_operations=0, fg_based_operating_cost=1, operating_cost_per_bom_quantity=3, conversion_rate=1
		)
		with patch("frappe.get_system_settings", return_value="Banker's Rounding (legacy)"):
			BOM.calculate_op_cost(b, update_hour_rate=False, save=False)
		self.assertEqual(b.base_operating_cost, 12)
		self.assertEqual(self.calculate([item(qty=8)], {"BOM-A": b})["estimated_total_cost"], 64)

	def test_missing_finished_good_operation_inputs(self):
		b = bom()
		b.update(with_operations=0, fg_based_operating_cost=1, operating_cost_per_bom_quantity=None)
		result = self.calculate([item()], {"BOM-A": b})
		self.assertIsNone(result["expected_gross_profit"])

	def test_child_bom_drift_does_not_invent_parent_cost(self):
		b = bom()
		b.items = [Doc(item_code="SUB", qty=1, stock_qty=1, bom_no="SUB-BOM", base_amount=15)]
		child = bom("SUB-BOM", "SUB", quantity=1, cost=20)
		result = self.calculate([item()], {"BOM-A": b, "SUB-BOM": child})
		self.assertFalse(result["is_complete"])
		self.assertIsNone(result["estimated_total_cost"])
		self.assertTrue(any("differs from child" in w for w in result["warnings"]))

	def test_valuation_subassembly_is_explicitly_unsupported(self):
		b = bom()
		b.set_rate_of_sub_assembly_item_based_on_bom = 0
		b.items = [Doc(item_code="SUB", qty=1, stock_qty=1, bom_no="SUB-BOM", base_amount=15)]
		result = self.calculate([item()], {"BOM-A": b, "SUB-BOM": bom("SUB-BOM", "SUB", quantity=1, cost=5)})
		self.assertIsNone(result["expected_gross_margin_percentage"])
		self.assertTrue(any("valuation-based" in w for w in result["warnings"]))

	def test_process_loss_matches_good_output_unit_cost(self):
		b = bom(quantity=10, cost=200)
		b.process_loss_qty = 2
		result = self.calculate([item(qty=16)], {"BOM-A": b})
		self.assertEqual(result["estimated_total_cost"], float(Decimal(210) / 8 * 16))

	def test_total_process_loss_cannot_produce_profit(self):
		b = bom()
		b.process_loss_qty = 2
		self.assertIsNone(self.calculate([item()], {"BOM-A": b})["expected_gross_profit"])

	def test_scrap_and_byproducts_safely_unsupported(self):
		for kind in ["Scrap", "By-Product", "Co-Product"]:
			b = bom()
			b.secondary_items = [Doc(item_code="SECONDARY", secondary_item_type=kind)]
			result = self.calculate([item()], {"BOM-A": b})
			self.assertFalse(result["is_complete"])
			self.assertIsNone(result["expected_gross_profit"])

	def test_changed_material_snapshot_and_price_comparison(self):
		old = self.calculate([item(qty=2, net=100)])
		snapshot = copy.deepcopy(old)
		changed = self.calculate([item(qty=2, net=100)], {"BOM-A": bom(cost=30)})
		delta = comparison_changes(snapshot, changed)
		self.assertEqual(delta["estimated_total_cost"], 10)
		self.assertEqual(delta["expected_gross_profit"], -10)
		self.assertEqual(snapshot, old)

	def test_selling_price_change_comparison(self):
		old = self.calculate([item(qty=2, net=100)])
		changed = self.calculate([item(qty=2, net=120)])
		self.assertEqual(comparison_changes(old, changed)["estimated_total_cost"], 0)
		self.assertEqual(comparison_changes(old, changed)["expected_gross_profit"], 20)
		self.assertEqual(old["net_selling_value"], 100)

	def test_rate_evidence_changes_do_not_refresh_saved_cost_or_history(self):
		with patch("order_profitability_predictor.risks.rate_evidence", return_value=None):
			saved = self.calculate([item(qty=2, net=100)])
		frozen = copy.deepcopy(saved)
		# Date evidence changes after a snapshot; no new rate is fetched into BOMs.
		with (
			patch(
				"order_profitability_predictor.risks.rate_evidence",
				return_value={"date": "2026-01-01", "kind": "matching purchase document date"},
			),
			patch("order_profitability_predictor.risks.nowdate", return_value="2026-10-24"),
		):
			current = self.calculate([item(qty=2, net=100)])
		self.assertEqual(current["estimated_total_cost"], saved["estimated_total_cost"])
		self.assertEqual(saved, frozen)
		self.assertEqual(comparison_changes(saved, current)["estimated_total_cost"], 0)

	def test_semi_finished_operation_routing_is_unsupported(self):
		b = bom()
		b.track_semi_finished_goods = 1
		self.assertIsNone(self.calculate([item()], {"BOM-A": b})["estimated_total_cost"])
