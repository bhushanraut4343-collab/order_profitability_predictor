"""Real database queries and financial invariants using only generated fixtures."""

import json
import os
import unittest
from unittest.mock import patch

import frappe

from order_profitability_predictor.order_profitability_predictor.doctype.profitability_analysis.profitability_analysis import (
	snapshot_values,
)
from order_profitability_predictor.profitability import calculate_quotation_profitability
from order_profitability_predictor.purchase_evidence import observed_purchase_evidence
from order_profitability_predictor.tests.site_fixtures import make_manufacturing_fixture


@unittest.skipUnless(os.environ.get("OPP_RUN_SITE_TESTS") == "1", "Opt-in site integration tests")
class SiteIntegrationTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.user = frappe.session.user
		frappe.set_user("Administrator")
		try:
			cls.fixture = make_manufacturing_fixture(costing_basis="Valuation Rate")
		except Exception:
			frappe.db.rollback()
			frappe.set_user(cls.user)
			raise

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		frappe.set_user(cls.user)

	def test_real_calculation_and_saved_snapshot_values(self):
		result = calculate_quotation_profitability(self.fixture.quotation)
		expected = dict(
			net_selling_value=1200,
			estimated_total_cost=720,
			expected_gross_profit=480,
			expected_gross_margin_percentage=40,
		)
		self.assertEqual({k: result[k] for k in expected}, expected)
		saved = json.loads(frappe.get_doc("Profitability Analysis", self.fixture.analysis).snapshot_json)
		self.assertEqual({k: saved[k] for k in expected}, expected)

	def test_risk_annotation_preserves_every_financial_total(self):
		result = calculate_quotation_profitability(self.fixture.quotation)
		with patch("order_profitability_predictor.profitability.annotate_risks", side_effect=lambda r: r):
			core = calculate_quotation_profitability(self.fixture.quotation)
		for key in (
			"net_selling_value",
			"estimated_total_cost",
			"expected_gross_profit",
			"expected_gross_margin_percentage",
			"is_complete",
		):
			self.assertEqual(core[key], result[key])

	def test_real_purchase_query_missing_company_currency_or_uom(self):
		base = dict(company=self.fixture.company, item_code=self.fixture.raw, uom="Nos")
		for changes, currency in [
			({}, "INR"),
			({"company": "OPP Nonexistent Company"}, "INR"),
			({"uom": "OPP Nonexistent UOM"}, "INR"),
			({}, "USD"),
		]:
			basis = {**base, **changes}
			results = observed_purchase_evidence([basis], currency)
			key = (basis["company"], basis["item_code"], basis["uom"])
			self.assertEqual(results[key], {"status": "unavailable"})

	def test_snapshot_purchase_observation_is_not_persisted(self):
		result = calculate_quotation_profitability(self.fixture.quotation)
		result["material_rate_evidence"] = [{"purchase_evidence": dict(rate=999, document="PRIVATE")}]
		result["risks"].append(
			dict(code="valuation_purchase_observed", message="Private price", severity="Information")
		)
		result["warnings"].append("Private price")
		target = "order_profitability_predictor.order_profitability_predictor.doctype.profitability_analysis.profitability_analysis.calculate_quotation_profitability"
		with patch(target, return_value=result):
			values = snapshot_values(self.fixture.quotation)
		self.assertNotIn("material_rate_evidence", json.loads(values["snapshot_json"]))
		self.assertNotIn("PRIVATE", values["snapshot_json"])
		self.assertNotIn("Private price", values["snapshot_json"])
