"""Risk annotations only: never alter the underlying profitability numbers."""

from math import isfinite

import frappe
from frappe.utils import getdate, nowdate

from order_profitability_predictor.purchase_evidence import evidence_key, observed_purchase_evidence

STALE_RATE_DAYS = 90
THRESHOLD_KEY = "order_profitability_minimum_margin"


def minimum_margin():
	value = frappe.conf.get(THRESHOLD_KEY, 15)
	try:
		value = float(value)
		if not isfinite(value) or not 0 <= value <= 100:
			raise ValueError
	except (TypeError, ValueError):
		frappe.throw(f"{THRESHOLD_KEY} must be a number between 0 and 100.", frappe.ValidationError)
	return value


def rate_evidence(basis):
	"""Return matching dated evidence, not a claimed purchase date for the BOM.

	BOM rows do not retain source document references. Only records unchanged
	since the BOM snapshot can provide evidence; ambiguity remains unknown.
	All lookups respect the current user's document permissions.
	"""
	source = basis.get("source")
	if source == "Price List":
		filters = {
			"item_code": basis["item_code"],
			"price_list": basis.get("price_list"),
			"currency": basis.get("currency"),
			"uom": basis.get("uom"),
			"supplier": ["is", "not set"],
			"customer": ["is", "not set"],
			"batch_no": ["is", "not set"],
			"modified": ["<=", basis["modified"]],
		}
		try:
			records = frappe.get_list(
				"Item Price",
				filters=filters,
				fields=["price_list_rate", "valid_from", "valid_upto"],
				limit_page_length=0,
			)
		except frappe.PermissionError:
			return None
		# Only same-currency price lists: cross-currency historical conversions
		# cannot be established from a saved BOM row alone.
		if basis.get("price_list_currency") != basis.get("currency"):
			return None
		matches = [
			r
			for r in records
			if r.valid_from
			and getdate(r.valid_from) <= getdate(basis["modified"])
			and abs(float(r.price_list_rate) - basis["rate"]) < 0.000001
			and (not r.valid_upto or getdate(r.valid_upto) >= getdate(basis["modified"]))
		]
		if len(matches) == 1:
			return {
				"date": str(matches[0].valid_from),
				"kind": "price-list effective date",
				"valid_upto": str(matches[0].valid_upto) if matches[0].valid_upto else None,
			}
	elif source == "Last Purchase Rate":
		matches = []
		for doctype, date_field in [
			("Purchase Order", "transaction_date"),
			("Purchase Receipt", "posting_date"),
			("Purchase Invoice", "posting_date"),
		]:
			try:
				parents = frappe.get_list(
					doctype,
					filters={
						"company": basis["company"],
						"docstatus": 1,
						date_field: ["<=", str(getdate(basis["modified"]))],
						"modified": ["<=", basis["modified"]],
						# v16 dot filters traverse the parent's Table field, not
						# a child DocType name (e.g. Purchase Order Item.item_code).
						"items.item_code": basis["item_code"],
					},
					fields=["name", date_field],
					order_by=f"{date_field} desc",
					limit_page_length=20,
				)
				for parent in parents:
					doc = frappe.get_doc(doctype, parent.name)
					doc.check_permission("read")
					if doc.get("is_return"):
						continue
					for row in doc.items:
						if (
							row.item_code == basis["item_code"]
							and row.uom == basis["uom"]
							and abs(float(row.base_net_rate) - basis["base_rate"]) < 0.000001
						):
							matches.append(str(parent[date_field]))
			except frappe.PermissionError:
				# Partial access cannot establish the latest matching evidence.
				return None
		if matches:
			return {"date": max(matches), "kind": "matching purchase document date"}
	return None


def annotate_risks(result):
	threshold = minimum_margin()
	risks = []
	valuation_components = []

	def collect(component):
		if "components" in component:
			for child in component["components"]:
				collect(child)
		elif component.get("rate_basis", {}).get("source") == "Valuation Rate":
			valuation_components.append(component)

	for item in result["items"]:
		collect(item)
	purchase_observations = (
		observed_purchase_evidence([c["rate_basis"] for c in valuation_components], result.get("currency"))
		if valuation_components
		else {}
	)
	material_evidence = []

	def add(severity, code, message):
		risks.append(dict(severity=severity, code=code, message=message))

	for message in result["warnings"]:
		severity = "Information" if message.startswith(("Saved BOM", "Alternative row")) else "Critical"
		add(severity, "cost_assumption" if severity == "Information" else "incomplete_cost", message)

	def inspect(component):
		if "components" in component:
			for child in component["components"]:
				inspect(child)
			return
		basis = component.get("rate_basis")
		if not basis:
			return
		evidence = rate_evidence(basis)
		component["rate_date_evidence"] = evidence
		label = basis["item_code"]
		if basis.get("source") == "Valuation Rate":
			# Supplier price observations are independent of the saved inventory
			# valuation and BOM.modified; neither changes cost/completeness.
			observation = purchase_observations.get(evidence_key(basis), {"status": "unavailable"})
			component["costing_basis"] = "Inventory Valuation"
			material_evidence.append(
				dict(
					item_code=label,
					costing_basis="Inventory Valuation",
					saved_bom_rate=basis.get("base_rate"),
					currency=result.get("currency"),
					uom=basis.get("uom"),
					purchase_evidence=observation,
				)
			)
			add(
				"Information",
				"inventory_valuation_basis",
				f"{label}: cost uses saved inventory valuation, not the latest supplier price.",
			)
			status = observation["status"]
			if status == "observed":
				age = (getdate(nowdate()) - getdate(observation["date"])).days
				observation["age_days"] = age
				observation["stale"] = age > STALE_RATE_DAYS
				add(
					"Warning" if age > STALE_RATE_DAYS else "Information",
					"valuation_purchase_stale" if age > STALE_RATE_DAYS else "valuation_purchase_observed",
					f"{label}: accessible purchase-price evidence is older than {STALE_RATE_DAYS} days."
					if age > STALE_RATE_DAYS
					else f"{label}: recent accessible purchase-price evidence observed; it is not a guaranteed future purchasing cost.",
				)
			else:
				reason = {
					"conflicting": "conflicting newest purchase prices",
					"search_limit": "purchase-evidence review limit reached",
				}.get(status, "no comparable, accessible submitted purchase evidence")
				add(
					"Information",
					"valuation_purchase_unavailable",
					f"{label}: {reason}; purchase-price freshness cannot be established.",
				)
			return
		if not evidence:
			add(
				"Warning",
				"unknown_rate_date",
				f"{label}: saved material rate date is unknown; freshness cannot be verified.",
			)
			return
		date = getdate(evidence["date"])
		age = (getdate(nowdate()) - date).days
		expired = evidence.get("valid_upto") and getdate(evidence["valid_upto"]) < getdate(nowdate())
		if age > STALE_RATE_DAYS or expired:
			add(
				"Warning",
				"outdated_rate",
				f"{label}: potentially outdated rate; {evidence['kind']} {date} (review limit {STALE_RATE_DAYS} days).",
			)
		else:
			add(
				"Information",
				"dated_rate_evidence",
				f"{label}: {evidence['kind']} {date}; matching evidence does not prove the saved BOM rate was refreshed.",
			)

	for item in result["items"]:
		inspect(item)
	margin = result["expected_gross_margin_percentage"]
	if result["is_complete"] and margin is not None and margin < threshold:
		add(
			"Warning",
			"low_margin",
			f"Estimated gross margin {margin:.2f}% is below the configured minimum {threshold:g}%.",
		)
	result["minimum_gross_margin_percentage"] = threshold
	result["stale_rate_days"] = STALE_RATE_DAYS
	result["risks"] = risks
	if material_evidence:
		result["material_rate_evidence"] = material_evidence
	# Retain the existing string warnings interface for Python callers.
	result["warnings"] = list(dict.fromkeys([*result["warnings"], *(r["message"] for r in risks)]))
	return result
