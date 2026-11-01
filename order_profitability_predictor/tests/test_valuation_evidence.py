"""Valuation costs stay fixed; purchase observations remain permission-checked."""

import copy
import unittest
from unittest.mock import Mock, patch

import frappe

from order_profitability_predictor.purchase_evidence import observed_purchase_evidence
from order_profitability_predictor.risks import annotate_risks

MODULE = "order_profitability_predictor.purchase_evidence"


def basis(code="RAW"):
	return dict(
		source="Valuation Rate",
		company="Company",
		item_code=code,
		uom="Nos",
		base_rate=4250,
		modified="2000-01-01",
	)


def purchase(code="RAW", name="PINV-1", rate=6000, date="2026-10-25", time="10:00:00", **extra):
	row = dict(
		name=name,
		company="Company",
		currency="INR",
		posting_date=date,
		posting_time=time,
		row_name=name + "-" + code,
		item_code=code,
		uom="Nos",
		purchase_rate=rate,
		purchase_qty=1,
	)
	row.update(extra)
	return row


def document(rows, deny=False, strip=False):
	doc = Mock()
	doc.company = "Company"
	doc.currency = "INR"
	doc.docstatus = 1
	items = [
		frappe._dict(item_code=r["item_code"], uom=r["uom"], base_net_rate=r["purchase_rate"]) for r in rows
	]
	doc.get.side_effect = lambda key: items if key == "items" else 0
	if deny:
		doc.check_permission.side_effect = frappe.PermissionError
	if strip:
		doc.apply_fieldlevel_read_permissions.side_effect = lambda: items.clear()
	return doc


class ValuationEvidenceTests(unittest.TestCase):
	def evidence(self, rows, bases=None, doc=None):
		bases = bases or [basis()]
		with (
			patch(MODULE + ".nowdate", return_value="2026-10-25"),
			patch(
				MODULE + ".frappe.get_list",
				side_effect=lambda dt, **kwargs: rows if dt == "Purchase Invoice" else [],
			) as query,
			patch(MODULE + ".frappe.get_doc", return_value=doc or document(rows)) as get_doc,
		):
			output = observed_purchase_evidence(bases, "INR")
			return output, query, get_doc

	def test_observed_purchase_separate_from_saved_valuation(self):
		result, query, _ = self.evidence([purchase()])
		value = result[("Company", "RAW", "Nos")]
		self.assertEqual(value["rate"], 6000)
		self.assertEqual(value["date"], "2026-10-25")
		self.assertEqual(basis()["base_rate"], 4250)
		self.assertNotIn("modified", query.call_args.kwargs["filters"])

	def test_missing_evidence(self):
		self.assertEqual(self.evidence([])[0][("Company", "RAW", "Nos")], {"status": "unavailable"})

	def test_company_currency_and_uom_mismatches(self):
		for overrides in [dict(company="Other"), dict(currency="USD"), dict(uom="Box")]:
			result, _, _ = self.evidence([purchase(**overrides)])
			self.assertEqual(result[("Company", "RAW", "Nos")]["status"], "unavailable")

	def test_document_and_field_permissions_hide_details(self):
		rows = [purchase()]
		for doc in (document(rows, deny=True), document(rows, strip=True)):
			result, _, _ = self.evidence(rows, doc=doc)
			self.assertEqual(result[("Company", "RAW", "Nos")], {"status": "unavailable"})

	def test_doctype_permission_failure_hides_details(self):
		with (
			patch(MODULE + ".nowdate", return_value="2026-10-25"),
			patch(MODULE + ".frappe.get_list", side_effect=frappe.PermissionError),
		):
			self.assertEqual(
				observed_purchase_evidence([basis()], "INR")[("Company", "RAW", "Nos")],
				{"status": "unavailable"},
			)

	def test_return_or_unsubmitted_document_not_disclosed(self):
		for returned, status in [(True, 1), (False, 0), (False, 2)]:
			rows = [purchase()]
			doc = document(rows)
			doc.docstatus = status
			doc.get.side_effect = (
				lambda key: [frappe._dict(item_code="RAW", uom="Nos", base_net_rate=6000)]
				if key == "items"
				else returned
			)
			result, _, _ = self.evidence(rows, doc=doc)
			self.assertEqual(result[("Company", "RAW", "Nos")]["status"], "unavailable")

	def test_latest_timestamp_selected_without_bom_modified_cutoff(self):
		rows = [
			purchase(name="OLD", rate=2500, time="09:00:00"),
			purchase(name="NEW", rate=6000, time="10:00:00"),
		]
		self.assertEqual(self.evidence(rows)[0][("Company", "RAW", "Nos")]["document"], "NEW")

	def test_conflicting_latest_prices_have_no_selected_price(self):
		rows = [purchase(name="A", rate=6000), purchase(name="B", rate=6200)]
		self.assertEqual(self.evidence(rows)[0][("Company", "RAW", "Nos")], {"status": "conflicting"})

	def test_missing_time_does_not_assume_earlier(self):
		rows = [purchase(name="A", rate=6000, time=None), purchase(name="B", rate=6200)]
		self.assertEqual(self.evidence(rows)[0][("Company", "RAW", "Nos")], {"status": "conflicting"})

	def test_identical_duplicate_rows_are_harmless(self):
		row = purchase()
		self.assertEqual(self.evidence([row, row])[0][("Company", "RAW", "Nos")]["rate"], 6000)

	def test_invalid_or_future_or_zero_rows_not_evidence(self):
		for changes in [
			dict(purchase_rate=None),
			dict(purchase_rate=float("nan")),
			dict(purchase_rate=0),
			dict(posting_date="2026-10-26"),
			dict(purchase_qty=-1),
		]:
			result, _, _ = self.evidence([purchase(**changes)])
			self.assertEqual(result[("Company", "RAW", "Nos")]["status"], "unavailable")

	def test_row_limit_fails_conservatively(self):
		with patch(MODULE + ".MAX_ROWS_PER_TYPE", 0):
			self.assertEqual(
				self.evidence([purchase()])[0][("Company", "RAW", "Nos")]["status"], "search_limit"
			)

	def test_document_check_limit_fails_conservatively(self):
		with patch(MODULE + ".MAX_DOCUMENT_CHECKS", 0):
			self.assertEqual(
				self.evidence([purchase()])[0][("Company", "RAW", "Nos")]["status"], "search_limit"
			)

	def test_batch_queries_and_one_document_check_for_many_materials(self):
		bases = [basis(str(i)) for i in range(100)]
		rows = [purchase(code=str(i)) for i in range(100)]
		result, query, docs = self.evidence(rows, bases=bases)
		self.assertTrue(all(r["status"] == "observed" for r in result.values()))
		self.assertEqual(query.call_count, 2)
		self.assertEqual(docs.call_count, 1)
		for call in query.call_args_list:
			filters = call.kwargs["filters"]
			self.assertEqual(filters["docstatus"], 1)
			self.assertEqual(filters["is_return"], 0)
			self.assertEqual(filters["company"], "Company")
			self.assertEqual(filters["currency"], "INR")

	def annotated(self, status="observed", date="2026-10-25"):
		result = dict(
			company="Company",
			currency="INR",
			net_selling_value=1200,
			estimated_total_cost=720,
			expected_gross_profit=480,
			expected_gross_margin_percentage=40,
			is_complete=True,
			items=[dict(components=[dict(rate_basis=basis(), estimated_cost=600)])],
			warnings=[],
		)
		original = copy.deepcopy(result)
		observation = dict(
			status=status, date=date, rate=6000, document="PINV-1", doctype="Purchase Invoice", currency="INR"
		)
		with (
			patch(
				"order_profitability_predictor.risks.observed_purchase_evidence",
				return_value={("Company", "RAW", "Nos"): observation},
			),
			patch("order_profitability_predictor.risks.minimum_margin", return_value=15),
			patch("order_profitability_predictor.risks.nowdate", return_value="2026-10-25"),
		):
			result = annotate_risks(result)
		for key in [
			"net_selling_value",
			"estimated_total_cost",
			"expected_gross_profit",
			"expected_gross_margin_percentage",
			"is_complete",
		]:
			self.assertEqual(result[key], original[key])
		self.assertFalse(any(r["code"] == "unknown_rate_date" for r in result["risks"]))
		return result

	def test_stale_purchase_warning_preserves_financial_results(self):
		result = self.annotated(date="2026-01-01")
		self.assertTrue(
			any(
				r["code"] == "valuation_purchase_stale" and r["severity"] == "Warning"
				for r in result["risks"]
			)
		)

	def test_recent_purchase_information_and_basis(self):
		result = self.annotated()
		self.assertEqual(result["material_rate_evidence"][0]["costing_basis"], "Inventory Valuation")
		self.assertEqual(result["material_rate_evidence"][0]["saved_bom_rate"], 4250)
		self.assertTrue(
			any(
				r["code"] == "valuation_purchase_observed" and r["severity"] == "Information"
				for r in result["risks"]
			)
		)

	def test_missing_purchase_information(self):
		result = self.annotated(status="unavailable")
		self.assertTrue(
			any(
				r["code"] == "valuation_purchase_unavailable" and r["severity"] == "Information"
				for r in result["risks"]
			)
		)

	def test_exactly_ninety_days_is_not_stale(self):
		result = self.annotated(date="2026-07-27")
		self.assertFalse(result["material_rate_evidence"][0]["purchase_evidence"]["stale"])
