"""Source-aware snapshot permissions; never grant roles or change source records."""

import frappe
from frappe import _

from order_profitability_predictor.financial_permissions import historical_fields


def has_analysis_permission(doc, user=None, ptype=None, **kwargs):
	user = user or frappe.session.user
	if user == "Guest":
		return False
	quotation_name = doc.get("quotation")
	if not isinstance(quotation_name, str) or not quotation_name.strip():
		return False
	try:
		quotation = frappe.get_doc("Quotation", quotation_name)
		historical_fields(user=user)
	except (frappe.DoesNotExistError, frappe.PermissionError):
		return False
	return bool(frappe.has_permission("Quotation", "read", doc=quotation, user=user))


def analysis_query_conditions(user=None, **kwargs):
	user = user or frappe.session.user
	if user == "Guest":
		return "1=0"
	try:
		historical_fields(user=user)
		# Build SQL only; reuse standard owner/company/User Permissions and query
		# hooks without enumerating all Quotation names or recursing into snapshots.
		query = frappe.qb.get_query("Quotation", fields=["name"], user=user, ignore_permissions=False)
	except frappe.PermissionError:
		return "1=0"
	return f"`tabProfitability Analysis`.`quotation` IN ({query.get_sql()})"


def prevent_analysis_sharing(doc, method=None):
	# Frappe ORs shares with query conditions. Do not permit snapshot shares,
	# including shares created through the standard share service.
	if doc.get("share_doctype") == "Profitability Analysis":
		frappe.throw(
			_("Profitability analyses cannot be shared. Use role and source Quotation permissions."),
			frappe.PermissionError,
		)
