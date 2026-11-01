"""Read-only history access and comparisons; snapshots are never updated."""

import json
from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import now_datetime

from order_profitability_predictor.financial_permissions import historical_fields
from order_profitability_predictor.profitability import calculate_quotation_profitability


def _authorize(quotation_name):
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in to view profitability history."), frappe.PermissionError)
	if not isinstance(quotation_name, str) or not quotation_name.strip():
		frappe.throw(_("A saved Quotation name is required."), frappe.ValidationError)
	frappe.get_doc("Quotation", quotation_name).check_permission("read")
	frappe.has_permission("Profitability Analysis", "read", throw=True)
	historical_fields()


def _snapshot(doc, quotation_name):
	doc.check_permission("read")
	if doc.quotation != quotation_name:
		frappe.throw(_("The analysis does not belong to this Quotation."), frappe.PermissionError)
	snapshot = json.loads(doc.snapshot_json)
	if (
		snapshot.get("quotation") != quotation_name
		or snapshot.get("company") != doc.company
		or snapshot.get("currency") != doc.base_currency
	):
		frappe.throw(_("The saved snapshot references are inconsistent."), frappe.ValidationError)
	return {
		"name": doc.name,
		"analyzed_at": str(doc.analyzed_at),
		"analyzed_by": doc.analyzed_by,
		**{
			key: snapshot.get(key)
			for key in (
				"quotation",
				"company",
				"currency",
				"net_selling_value",
				"estimated_total_cost",
				"expected_gross_profit",
				"expected_gross_margin_percentage",
				"is_complete",
			)
		},
	}


def comparison_changes(historical, current):
	comparable = (
		historical.get("is_complete")
		and current.get("is_complete")
		and historical.get("currency") == current.get("currency")
		and historical.get("company") == current.get("company")
	)
	changes = {}
	for key in ("estimated_total_cost", "expected_gross_profit", "expected_gross_margin_percentage"):
		old, new = historical.get(key), current.get(key)
		changes[key] = None
		if comparable and old is not None and new is not None:
			changes[key] = float(Decimal(str(new)) - Decimal(str(old)))
	margin = changes["expected_gross_margin_percentage"]
	changes["margin_direction"] = (
		"not_available"
		if margin is None
		else "increased"
		if margin > 0
		else "decreased"
		if margin < 0
		else "unchanged"
	)
	return changes


@frappe.whitelist(methods=["POST"])
def get_quotation_history(quotation_name: str, start=0):
	_authorize(quotation_name)
	try:
		start = int(start)
		if start < 0:
			raise ValueError
	except (ValueError, TypeError):
		frappe.throw(_("Invalid history page."), frappe.ValidationError)
	# get_list applies role, User Permission, sharing and query constraints.
	rows = frappe.get_list(
		"Profitability Analysis",
		filters={"quotation": quotation_name},
		fields=["name"],
		order_by="analyzed_at desc, creation desc, name desc",
		limit_start=start,
		limit_page_length=21,
	)
	analyses = [
		_snapshot(frappe.get_doc("Profitability Analysis", row.name), quotation_name) for row in rows[:20]
	]
	return {"quotation": quotation_name, "analyses": analyses, "start": start, "has_more": len(rows) > 20}


@frappe.whitelist(methods=["POST"])
def compare_quotation_analysis(quotation_name: str, analysis_name: str):
	_authorize(quotation_name)
	if not isinstance(analysis_name, str) or not analysis_name.strip():
		frappe.throw(_("Select a saved analysis."), frappe.ValidationError)
	historical = _snapshot(frappe.get_doc("Profitability Analysis", analysis_name), quotation_name)
	current = calculate_quotation_profitability(quotation_name)
	return {
		"historical": historical,
		"current": current,
		"calculated_at": str(now_datetime()),
		"changes": comparison_changes(historical, current),
		"comparison_note": _(
			"Changes are current minus historical. Margin changes are percentage points. Changes are unavailable for incomplete estimates or different companies/currencies."
		),
	}
