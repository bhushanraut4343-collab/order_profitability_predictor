"""Read-only estimates from saved BOM costs; never refresh rates or save documents."""

from math import isfinite

import frappe
from erpnext.manufacturing.doctype.bom.bom import get_good_qty

from order_profitability_predictor.risks import annotate_risks


def _number(value):
	try:
		number = float(value)
		return number if isfinite(number) else None
	except (TypeError, ValueError):
		return None


def _positive(value):
	number = _number(value)
	return number is not None and number > 0


def _bom_cost(name, item_code, company, stock_qty, path=()):
	warnings = []
	result = {
		"bom": name,
		"stock_qty": stock_qty,
		"estimated_cost": None,
		"components": [],
		"warnings": warnings,
		"is_complete": False,
	}
	if name in path:
		warnings.append(f"Circular BOM reference: {name}.")
		return result
	if not frappe.db.exists("BOM", name):
		warnings.append(f"BOM {name} does not exist.")
		return result
	bom = frappe.get_doc("BOM", name)
	bom.check_permission("read")
	if bom.item != item_code or bom.company != company or bom.docstatus != 1 or not bom.is_active:
		warnings.append(f"BOM {name} must match the item/company and be active and submitted.")
		return result
	if (
		not _positive(bom.quantity)
		or _number(bom.process_loss_qty) is None
		or not 0 <= float(bom.process_loss_qty) < float(bom.quantity)
	):
		warnings.append(f"BOM {name} has invalid production or process-loss quantity.")
		return result
	factor = stock_qty / get_good_qty(bom)
	result.update(
		production_qty=bom.quantity,
		good_qty=get_good_qty(bom),
		quantity_factor=factor,
		saved_modified=str(bom.modified),
	)
	# Saved totals already include subassembly costs. Replace each subassembly line
	# with its recursively inspected cost, rather than adding it twice.
	material = 0.0
	if not bom.get("items"):
		warnings.append(f"BOM {name} has no material costing rows.")
	for row in bom.get("items") or []:
		component = {"item_code": row.item_code, "estimated_cost": None}
		if not _positive(row.qty):
			warnings.append(f"{name}: invalid quantity for {row.item_code}.")
		elif row.get("bom_no") and not row.get("do_not_explode"):
			if not (bom.get("set_rate_of_sub_assembly_item_based_on_bom") or row.get("is_phantom_item")):
				warnings.append(
					f"{name}: subassembly {row.item_code} is not costed from its BOM; valuation-based subassembly costing is unsupported."
				)
			if not _positive(row.stock_qty):
				warnings.append(f"{name}: missing stock quantity for {row.item_code}.")
			else:
				component = _bom_cost(
					row.bom_no, row.item_code, company, float(row.stock_qty) * factor, (*path, name)
				)
				component["item_code"] = row.item_code
				warnings.extend(component["warnings"])
				if component["is_complete"]:
					material += component["estimated_cost"]
					saved_amount = _number(row.base_amount)
					if saved_amount is None or saved_amount <= 0:
						warnings.append(f"{name}: missing saved subassembly amount for {row.item_code}.")
					elif abs(saved_amount - component["estimated_cost"] / factor) > 0.02:
						warnings.append(
							f"{name}: saved subassembly amount differs from child BOM cost for {row.item_code}; review saved BOM costs."
						)
		elif not _positive(row.base_rate) or not _positive(row.base_amount):
			warnings.append(f"{name}: missing or zero saved material cost for {row.item_code}.")
		else:
			component["estimated_cost"] = float(row.base_amount) * factor
			component["rate_basis"] = dict(
				source=bom.get("rm_cost_as_per"),
				item_code=row.item_code,
				price_list=bom.get("buying_price_list"),
				currency=bom.get("currency"),
				price_list_currency=bom.get("price_list_currency"),
				company=company,
				uom=row.get("uom"),
				rate=float(row.get("rate") or 0),
				base_rate=float(row.base_rate),
				modified=str(bom.modified),
			)
			material += component["estimated_cost"]
		result["components"].append(component)
	operations = _number(bom.base_operating_cost)
	if bom.get("with_operations"):
		saved_operation_total = 0.0
		if not bom.get("operations"):
			warnings.append(f"{name}: operations enabled but no operations provided.")
		for op in bom.get("operations") or []:
			if (
				not _positive(op.get("base_hour_rate"))
				or not _positive(op.time_in_mins)
				or not _positive(op.base_operating_cost)
			):
				warnings.append(f"{name}: incomplete saved operation cost for {op.operation}.")
			op_cost = _number(
				op.get("base_cost_per_unit")
				if op.get("set_cost_based_on_bom_qty")
				else op.base_operating_cost
			)
			if op_cost is None:
				warnings.append(f"{name}: missing saved operation amount for {op.operation}.")
			else:
				saved_operation_total += (
					op_cost * float(bom.quantity) if op.get("set_cost_based_on_bom_qty") else op_cost
				)
		if operations is not None and abs(saved_operation_total - operations) > 0.01:
			warnings.append(f"{name}: saved operation rows and total disagree.")
	elif not bom.get("fg_based_operating_cost"):
		operations = 0.0
		result["warnings"].append(f"{name}: no operation costing configured; labor/overhead may be omitted.")
	if (bom.get("with_operations") or bom.get("fg_based_operating_cost")) and not _positive(operations):
		warnings.append(f"{name}: missing saved operating cost.")
	if bom.get("fg_based_operating_cost") and not bom.get("with_operations"):
		per_unit = _number(bom.get("operating_cost_per_bom_quantity"))
		conversion = _number(bom.get("conversion_rate"))
		if per_unit is None or per_unit <= 0 or conversion is None or conversion <= 0:
			warnings.append(f"{name}: incomplete finished-good operating cost inputs.")
		elif (
			operations is not None
			and abs(round(per_unit * float(bom.quantity) * conversion, 2) - operations) > 0.01
		):
			warnings.append(f"{name}: saved finished-good operating total disagrees with configured inputs.")
	if bom.get("track_semi_finished_goods"):
		warnings.append(f"{name}: operation-level semi-finished goods costing is unsupported.")
	# Allocation rules need a separate implementation before these can be reliable.
	if bom.get("secondary_items"):
		warnings.append(f"{name}: secondary-product cost allocation is not supported yet.")
	complete = not warnings
	result.update(
		is_complete=complete,
		material_cost=material,
		operation_cost=operations * factor if operations is not None else None,
	)
	if complete:
		result["estimated_cost"] = material + (operations or 0) * factor
	return result


def calculate_quotation_profitability(quotation_name):
	"""Return base-currency, tax-exclusive estimates. Unknown totals remain None.

	No whitelist endpoint: intended for trusted Python callers with read permission.
	Zero material/operation rates are conservatively treated as missing data.
	"""
	quotation = frappe.get_doc("Quotation", quotation_name)
	quotation.check_permission("read")
	currency = frappe.get_cached_value("Company", quotation.company, "default_currency")
	warnings = [
		"Saved BOM costs are estimates. Underlying rates may be outdated; BOM modified dates do not prove rate freshness."
	]
	results = []
	selling = 0.0
	selling_complete = True
	for row in quotation.items:
		if row.get("is_alternative"):
			warnings.append(f"Alternative row {row.idx} excluded, matching ERPNext quotation totals.")
			continue
		net = _number(row.base_net_amount)
		selling_complete = selling_complete and net is not None
		selling += net or 0
		item = {
			"row": row.idx,
			"item_code": row.item_code,
			"net_selling_value": net,
			"estimated_cost": None,
			"is_complete": False,
			"warnings": [],
		}
		# Standard v16 Quotation Item has no BOM field; honor custom Link-to-BOM fields.
		selected = [
			row.get(f.fieldname)
			for f in row.meta.fields
			if f.fieldtype == "Link" and f.options == "BOM" and row.get(f.fieldname)
		]
		if len(set(selected)) > 1:
			item["warnings"].append("Conflicting explicitly selected BOMs.")
		else:
			bom_name = (
				selected[0]
				if selected
				else frappe.db.get_value(
					"BOM",
					{
						"item": row.item_code,
						"company": quotation.company,
						"is_default": 1,
						"is_active": 1,
						"docstatus": 1,
					},
					"name",
				)
			)
			if not bom_name:
				item["warnings"].append("No applicable default or explicitly selected BOM.")
			elif not _positive(row.stock_qty):
				item["warnings"].append("Missing or invalid quotation stock quantity.")
			else:
				item.update(_bom_cost(bom_name, row.item_code, quotation.company, float(row.stock_qty)))
		if net is None:
			item["is_complete"] = False
			item["warnings"].append("Missing base net selling amount.")
		results.append(item)
		warnings.extend(f"Row {row.idx}: {w}" for w in item["warnings"])
	complete = bool(results) and selling_complete and all(i["is_complete"] for i in results)
	if not results:
		warnings.append("No non-alternative quotation items available to estimate.")
	known = sum(i["estimated_cost"] for i in results if i["is_complete"])
	total = known if complete else None
	profit = selling - total if complete else None
	return annotate_risks(
		{
			"quotation": quotation.name,
			"company": quotation.company,
			"currency": currency,
			"net_selling_value": selling if selling_complete else None,
			"estimated_total_cost": total,
			"known_items_cost": known,
			"expected_gross_profit": profit,
			"expected_gross_margin_percentage": profit / selling * 100 if complete and selling > 0 else None,
			"is_complete": complete,
			"items": results,
			"warnings": warnings,
		}
	)
