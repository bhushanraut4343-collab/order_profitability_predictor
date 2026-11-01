"""Authenticated, permission-checked access to saved quotation estimates."""

import frappe
from frappe import _

from order_profitability_predictor.profitability import calculate_quotation_profitability


@frappe.whitelist(methods=["POST"])
def check_quotation_profitability(quotation_name: str):
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in to check profitability."), frappe.PermissionError)
	if not isinstance(quotation_name, str) or not quotation_name.strip():
		frappe.throw(_("A saved Quotation name is required."), frappe.ValidationError)
	quotation = frappe.get_doc("Quotation", quotation_name)
	quotation.check_permission("read")
	return calculate_quotation_profitability(quotation.name)


@frappe.whitelist(methods=["POST"])
def save_quotation_analysis(quotation_name: str):
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in to save an analysis."), frappe.PermissionError)
	if not isinstance(quotation_name, str) or not quotation_name.strip():
		frappe.throw(_("A saved Quotation name is required."), frappe.ValidationError)
	frappe.has_permission("Profitability Analysis", "create", throw=True)
	# The controller checks Quotation/BOM read access and computes every value.
	analysis = frappe.get_doc({"doctype": "Profitability Analysis", "quotation": quotation_name})
	analysis.insert()
	return {"name": analysis.name, "doctype": analysis.doctype}
