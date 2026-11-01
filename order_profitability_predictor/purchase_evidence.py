"""Bounded, permission-checked purchase observations for valuation-costed materials.

Read-only and request-local. Observations never replace saved BOM costs.
"""

from math import isfinite

import frappe
from frappe.utils import get_time, getdate, nowdate

MAX_ROWS_PER_TYPE = 500
MAX_DOCUMENT_CHECKS = 30
PURCHASE_TYPES = ("Purchase Receipt", "Purchase Invoice")


def _number(value):
	try:
		value = float(value)
		return value if isfinite(value) and value > 0 else None
	except (TypeError, ValueError):
		return None


def evidence_key(basis):
	return (basis.get("company"), basis.get("item_code"), basis.get("uom"))


def observed_purchase_evidence(bases, base_currency):
	"""Batch both transaction types, then inspect only newest candidate documents.

	Conservative scope: same company, exact UOM, base-currency transactions only.
	Rows with conflicting prices at the newest timestamp have no selected price.
	Foreign-currency transactions and UOM conversions are not inferred here.
	"""
	keys = {evidence_key(b) for b in bases}
	results = {key: {"status": "unavailable"} for key in keys}
	if not keys or not base_currency:
		return results
	today = getdate(nowdate())
	candidates = {key: [] for key in keys}
	for company in {key[0] for key in keys}:
		codes = sorted({key[1] for key in keys if key[0] == company})
		for doctype in PURCHASE_TYPES:
			try:
				rows = frappe.get_list(
					doctype,
					filters={
						"company": company,
						"currency": base_currency,
						"docstatus": 1,
						"is_return": 0,
						"posting_date": ["<=", str(today)],
						"items.item_code": ["in", codes],
						"items.qty": [">", 0],
					},
					fields=[
						"name",
						"company",
						"currency",
						"posting_date",
						"posting_time",
						"items.name as row_name",
						"items.item_code as item_code",
						"items.uom as uom",
						"items.base_net_rate as purchase_rate",
						"items.qty as purchase_qty",
					],
					order_by="posting_date desc, posting_time desc, name desc",
					limit_page_length=MAX_ROWS_PER_TYPE + 1,
				)
			except frappe.PermissionError:
				# Do not claim latest evidence when a whole transaction type is hidden.
				return results
			if len(rows) > MAX_ROWS_PER_TYPE:
				return {key: {"status": "search_limit"} for key in keys}
			seen = set()
			for row in rows:
				identity = (doctype, row.get("name"), row.get("row_name"))
				if identity in seen:
					continue
				seen.add(identity)
				key = (row.get("company"), row.get("item_code"), row.get("uom"))
				if key not in keys or row.get("currency") != base_currency:
					continue
				rate = _number(row.get("purchase_rate"))
				if rate is None or not _number(row.get("purchase_qty")) or not row.get("posting_date"):
					continue
				date = getdate(row["posting_date"])
				if date > today:
					continue
				try:
					time = (
						get_time(str(row["posting_time"])).isoformat()
						if row.get("posting_time") is not None
						else None
					)
				except (ValueError, TypeError):
					time = None
				candidates[key].append(
					dict(
						doctype=doctype,
						document=row["name"],
						date=str(date),
						time=time,
						rate=rate,
						currency=base_currency,
						uom=key[2],
					)
				)

	documents = {}
	for key, rows in candidates.items():
		if not rows:
			continue
		latest_date = max(row["date"] for row in rows)
		newest = [row for row in rows if row["date"] == latest_date]
		# An undated time cannot be assumed earlier than a known time that day.
		if all(row["time"] is not None for row in newest):
			latest_time = max(row["time"] for row in newest)
			newest = [row for row in newest if row["time"] == latest_time]
		readable = True
		for row in newest:
			doc_key = (row["doctype"], row["document"])
			if doc_key not in documents:
				if len(documents) >= MAX_DOCUMENT_CHECKS:
					results[key] = {"status": "search_limit"}
					readable = False
					break
				try:
					doc = frappe.get_doc(*doc_key)
					doc.check_permission("read")
					# Also enforce field-level access on values used for price disclosure.
					doc.apply_fieldlevel_read_permissions()
					allowed = (
						doc.company == key[0]
						and doc.currency == base_currency
						and doc.docstatus == 1
						and not doc.get("is_return")
					)
					documents[doc_key] = (
						frozenset(
							(item.get("item_code"), item.get("uom"), _number(item.get("base_net_rate")))
							for item in doc.get("items") or []
						)
						if allowed
						else frozenset()
					)
				except (frappe.PermissionError, frappe.DoesNotExistError):
					documents[doc_key] = frozenset()
			if (key[1], key[2], row["rate"]) not in documents[doc_key]:
				readable = False
				break
		if not readable:
			continue
		if len({row["rate"] for row in newest}) != 1:
			results[key] = {"status": "conflicting"}
			continue
		# Identical prices in duplicate receipt/invoice evidence are harmless.
		chosen = sorted(newest, key=lambda row: (row["doctype"], row["document"]))[0]
		results[key] = {"status": "observed", **chosen}
	return results
