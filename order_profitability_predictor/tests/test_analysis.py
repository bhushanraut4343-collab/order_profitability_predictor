"""Pre-migration unit tests: controller/API behavior without schema writes."""

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import frappe

from order_profitability_predictor.api import save_quotation_analysis
from order_profitability_predictor.order_profitability_predictor.doctype.profitability_analysis.profitability_analysis import (
	ProfitabilityAnalysis,
	snapshot_values,
)

CONTROLLER = "order_profitability_predictor.order_profitability_predictor.doctype.profitability_analysis.profitability_analysis"


class AnalysisTests(unittest.TestCase):
	def setUp(self):
		self.engine = dict(
			quotation="Q-TEST",
			company="Company",
			currency="INR",
			net_selling_value=1200,
			estimated_total_cost=720,
			expected_gross_profit=480,
			expected_gross_margin_percentage=40,
			is_complete=True,
			risks=[dict(severity="Information", code="assumption", message="Estimate")],
			items=[dict(item_code="FG", estimated_cost=720, components=[dict(estimated_cost=600)])],
		)
		self.session = patch("frappe.session", frappe._dict(user="manager@example.com"))
		self.session.start()
		self.addCleanup(self.session.stop)
		self.clock = patch(CONTROLLER + ".now_datetime", return_value="2026-10-24 18:00:00")
		self.clock.start()
		self.addCleanup(self.clock.stop)

	def values(self):
		with (
			patch(CONTROLLER + ".calculate_quotation_profitability", return_value=self.engine) as calculate,
			patch(CONTROLLER + ".frappe.has_permission", return_value=True) as permission,
		):
			result = snapshot_values("Q-TEST")
			calculate.assert_called_once_with("Q-TEST")
			permission.assert_called_once_with("Profitability Analysis", "create", throw=True)
			return result

	def test_accuracy_and_identity(self):
		values = self.values()
		snapshot = json.loads(values["snapshot_json"])
		self.assertEqual(snapshot["estimated_total_cost"], 720)
		self.assertEqual(snapshot["expected_gross_margin_percentage"], 40)
		self.assertEqual(snapshot["analyzed_by"], "manager@example.com")
		self.assertEqual(values["cost_status"], "Complete")
		self.assertEqual(json.loads(values["risk_warnings"]), self.engine["risks"])
		self.assertEqual(json.loads(values["item_breakdown"]), self.engine["items"])

	def test_incomplete_values_remain_null(self):
		self.engine.update(
			is_complete=False,
			estimated_total_cost=None,
			expected_gross_profit=None,
			expected_gross_margin_percentage=None,
		)
		values = self.values()
		snapshot = json.loads(values["snapshot_json"])
		for key in ["estimated_total_cost", "expected_gross_profit", "expected_gross_margin_percentage"]:
			self.assertIsNone(snapshot[key])
		self.assertEqual(values["estimated_cost"], "Not available")
		self.assertEqual(values["cost_status"], "Incomplete")

	def test_historical_snapshot_detached_from_changed_sources(self):
		values = self.values()
		before = copy.deepcopy(values)
		self.engine["items"][0]["components"][0]["estimated_cost"] = 999
		self.engine.update(estimated_total_cost=999, expected_gross_profit=201)
		self.assertEqual(values, before)
		self.assertEqual(json.loads(values["snapshot_json"])["estimated_total_cost"], 720)

	def test_live_purchase_details_are_never_persisted_in_snapshot(self):
		self.engine["material_rate_evidence"] = [
			dict(purchase_evidence=dict(rate=6000, document="PRIVATE-PINV"))
		]
		self.engine["risks"].append(
			dict(
				code="valuation_purchase_observed",
				message="Purchase evidence observed",
				severity="Information",
			)
		)
		self.engine["warnings"] = ["Purchase evidence observed", "Saved inventory valuation"]
		values = self.values()
		snapshot = json.loads(values["snapshot_json"])
		self.assertNotIn("material_rate_evidence", snapshot)
		self.assertNotIn("PRIVATE-PINV", values["snapshot_json"])
		self.assertFalse(any(r["code"].startswith("valuation_purchase_") for r in snapshot["risks"]))
		self.assertEqual(snapshot["warnings"], ["Saved inventory valuation"])
		self.assertIn("material_rate_evidence", self.engine)
		self.assertEqual(snapshot["estimated_total_cost"], 720)

	def test_create_permission_denied_before_engine(self):
		with (
			patch(CONTROLLER + ".frappe.has_permission", side_effect=frappe.PermissionError),
			patch(CONTROLLER + ".calculate_quotation_profitability") as calculate,
		):
			with self.assertRaises(frappe.PermissionError):
				snapshot_values("Q-TEST")
			calculate.assert_not_called()

	def test_source_permission_denial_propagates(self):
		with (
			patch(CONTROLLER + ".frappe.has_permission", return_value=True),
			patch(CONTROLLER + ".calculate_quotation_profitability", side_effect=frappe.PermissionError),
		):
			with self.assertRaises(frappe.PermissionError):
				snapshot_values("Q-TEST")

	def test_guest_cannot_save(self):
		with patch("frappe.session", frappe._dict(user="Guest")):
			with self.assertRaises(frappe.PermissionError):
				save_quotation_analysis("Q-TEST")
			with self.assertRaises(frappe.PermissionError):
				snapshot_values("Q-TEST")

	def test_existing_document_and_deletion_blocked(self):
		doc = Mock()
		doc.is_new.return_value = False
		with self.assertRaises(frappe.ValidationError):
			ProfitabilityAnalysis.before_validate(doc)
		with self.assertRaises(frappe.ValidationError):
			ProfitabilityAnalysis.on_trash(doc)
		doc.update.assert_not_called()

	def test_browser_values_replaced_by_server_values(self):
		doc = Mock(quotation="Q-TEST")
		doc.is_new.return_value = True
		with patch(CONTROLLER + ".snapshot_values", return_value={"estimated_cost": "720"}) as values:
			ProfitabilityAnalysis.before_validate(doc)
			values.assert_called_once_with("Q-TEST")
			doc.update.assert_called_once_with({"estimated_cost": "720"})

	def test_api_inserts_only_quotation_and_uses_normal_permissions(self):
		doc = Mock()
		doc.name = "SNAPSHOT-1"
		doc.doctype = "Profitability Analysis"
		with (
			patch("frappe.has_permission", return_value=True),
			patch("frappe.get_doc", return_value=doc) as get_doc,
		):
			self.assertEqual(save_quotation_analysis("Q-TEST")["name"], "SNAPSHOT-1")
			get_doc.assert_called_once_with({"doctype": "Profitability Analysis", "quotation": "Q-TEST"})
			doc.insert.assert_called_once_with()

	def test_api_create_denial(self):
		with (
			patch("frappe.has_permission", side_effect=frappe.PermissionError),
			patch("frappe.get_doc") as get_doc,
		):
			with self.assertRaises(frappe.PermissionError):
				save_quotation_analysis("Q-TEST")
			get_doc.assert_not_called()

	def test_schema_permissions_are_restricted_and_summaries_not_numeric(self):
		import importlib

		module = importlib.import_module(CONTROLLER)
		schema = json.loads(Path(module.__file__).with_suffix(".json").read_text())
		self.assertEqual({p["role"] for p in schema["permissions"]}, {"System Manager", "Sales Manager"})
		for permission in schema["permissions"]:
			self.assertEqual(permission["read"], 1)
			self.assertEqual(permission["create"], 1)
			self.assertEqual(permission["write"], 0)
			self.assertEqual(permission["delete"], 0)
			self.assertEqual(permission["share"], 0)
		fields = {f["fieldname"]: f for f in schema["fields"]}
		self.assertEqual(fields["estimated_cost"]["fieldtype"], "Data")
		self.assertEqual(fields["snapshot_json"]["options"], "JSON")

	def test_save_endpoint_post_only_and_no_guest(self):
		self.assertIn(save_quotation_analysis, frappe.whitelisted)
		self.assertNotIn(save_quotation_analysis, frappe.guest_methods)
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[save_quotation_analysis], ["POST"])
