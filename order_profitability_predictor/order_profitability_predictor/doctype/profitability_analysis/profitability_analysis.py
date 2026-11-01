"""Immutable server-generated history; no dependency on mutable source values."""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from order_profitability_predictor.profitability import calculate_quotation_profitability


def snapshot_values(quotation_name):
	"""Compute afresh; never accept caller-supplied monetary values or identities."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in to save an analysis."), frappe.PermissionError)
	frappe.has_permission("Profitability Analysis", "create", throw=True)
	result = calculate_quotation_profitability(quotation_name)
	timestamp = now_datetime()
	# A serialization round trip detaches nested lists/dictionaries from the engine.
	snapshot = json.loads(frappe.as_json(result))
	# Live purchase observations require current purchase-document permissions.
	# Never persist them in a snapshot readable under Quotation-only permissions.
	snapshot.pop("material_rate_evidence", None)
	purchase_messages = {
		r["message"] for r in snapshot.get("risks", []) if r.get("code", "").startswith("valuation_purchase_")
	}
	snapshot["risks"] = [
		r for r in snapshot.get("risks", []) if not r.get("code", "").startswith("valuation_purchase_")
	]
	if "warnings" in snapshot:
		snapshot["warnings"] = [w for w in snapshot["warnings"] if w not in purchase_messages]
	snapshot.update(analyzed_at=str(timestamp), analyzed_by=frappe.session.user, snapshot_version=1)

	def summary(key):
		value = snapshot.get(key)
		return str(value) if value is not None else _("Not available")

	return dict(
		quotation=snapshot["quotation"],
		company=snapshot["company"],
		base_currency=snapshot["currency"],
		analyzed_at=timestamp,
		analyzed_by=frappe.session.user,
		net_selling_value=summary("net_selling_value"),
		estimated_cost=summary("estimated_total_cost"),
		expected_gross_profit=summary("expected_gross_profit"),
		expected_gross_margin_percentage=summary("expected_gross_margin_percentage"),
		cost_status="Complete" if snapshot["is_complete"] else "Incomplete",
		risk_warnings=frappe.as_json(snapshot.get("risks", [])),
		item_breakdown=frappe.as_json(snapshot["items"]),
		snapshot_json=frappe.as_json(snapshot),
	)


class ProfitabilityAnalysis(Document):
	def before_validate(self):
		if not self.is_new():
			frappe.throw(_("Saved analyses are immutable. Save a new analysis instead."))
		if not isinstance(self.quotation, str) or not self.quotation.strip():
			frappe.throw(_("A saved Quotation name is required."))
		self.update(snapshot_values(self.quotation))

	def on_trash(self):
		frappe.throw(_("Saved profitability analyses cannot be deleted."))
