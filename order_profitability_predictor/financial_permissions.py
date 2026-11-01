"""Fail-closed financial visibility, independent of costing and document grants."""

import frappe
from frappe import _

DENIED = "You do not have permission to access profitability information."

# Only inputs read by the engine, not alternative financial totals it never uses.
QUOTATION = ("company", "items")
QUOTATION_ITEM = ("item_code", "stock_qty", "base_net_amount", "is_alternative")
BOM = (
	"item",
	"company",
	"quantity",
	"process_loss_qty",
	"items",
	"base_operating_cost",
	"with_operations",
	"fg_based_operating_cost",
	"track_semi_finished_goods",
	"secondary_items",
	"set_rate_of_sub_assembly_item_based_on_bom",
)
BOM_ITEM = ("item_code", "qty", "bom_no", "do_not_explode", "is_phantom_item")
MATERIAL = ("base_rate", "base_amount", "rate", "uom")
RATE_BASIS = ("rm_cost_as_per", "buying_price_list", "currency", "price_list_currency")
OPERATION = (
	"operation",
	"base_hour_rate",
	"time_in_mins",
	"base_operating_cost",
	"set_cost_based_on_bom_qty",
)
FG_OPERATION = ("operating_cost_per_bom_quantity", "conversion_rate")
SNAPSHOT = (
	"quotation",
	"company",
	"base_currency",
	"analyzed_at",
	"analyzed_by",
	"net_selling_value",
	"estimated_cost",
	"expected_gross_profit",
	"expected_gross_margin_percentage",
	"cost_status",
	"risk_warnings",
	"item_breakdown",
	"snapshot_json",
)
# These controls are optional across supported v16 schemas. Missing core inputs deny.
OPTIONAL = {"is_alternative", "is_phantom_item", "track_semi_finished_goods", "secondary_items"}


def fields_readable(doctype, fields, *, parenttype=None, user=None, optional=()):
	"""Use parent permissions for children, and never regard masked input as readable."""
	user = user or frappe.session.user
	if user == "Guest":
		return False
	meta = frappe.get_meta(doctype)
	fields = set(fields)
	missing = {name for name in fields if not meta.get_field(name)}
	if missing - set(optional):
		return False
	fields -= missing
	if user == "Administrator":
		return True
	allowed = set(meta.get_permitted_fieldnames(parenttype=parenttype, user=user, permission_type="read"))
	# get_permitted_fieldnames intentionally excludes Table containers. Their
	# visibility still follows the parent's standard read permission levels.
	read_levels = set(meta.get_permlevel_access("read", parenttype=parenttype, user=user))
	allowed.update(
		name
		for name in fields
		if meta.get_field(name).fieldtype in ("Table", "Table MultiSelect")
		and meta.get_field(name).permlevel in read_levels
	)
	mask_levels = set(meta.get_permlevel_access("mask", parenttype=parenttype, user=user))
	return fields <= allowed and not any(
		meta.get_field(name).get("mask") and meta.get_field(name).permlevel not in mask_levels
		for name in fields
	)


def require_fields(doctype, fields, *, parenttype=None, user=None, optional=()):
	if not fields_readable(doctype, fields, parenttype=parenttype, user=user, optional=optional):
		frappe.throw(_(DENIED), frappe.PermissionError)


def quotation_fields(user=None):
	require_fields("Quotation", QUOTATION, user=user)
	require_fields("Company", ("default_currency",), user=user)
	require_fields("Quotation Item", QUOTATION_ITEM, parenttype="Quotation", user=user, optional=OPTIONAL)
	# Inspect metadata before reading even the presence of a custom selection.
	links = [
		df.fieldname
		for df in frappe.get_meta("Quotation Item").fields
		if df.fieldtype == "Link" and df.options == "BOM"
	]
	require_fields("Quotation Item", links, parenttype="Quotation", user=user)


def bom_fields(bom):
	"""Branch-specific checks precede access to optional costing inputs."""
	require_fields("BOM", BOM, optional=OPTIONAL)
	require_fields("BOM Item", BOM_ITEM, parenttype="BOM", optional=OPTIONAL)
	for row in bom.get("items") or []:
		if row.get("bom_no") and not row.get("do_not_explode"):
			require_fields("BOM Item", ("stock_qty", "base_amount"), parenttype="BOM")
		else:
			require_fields("BOM Item", MATERIAL, parenttype="BOM")
			require_fields("BOM", RATE_BASIS)
	if bom.get("with_operations"):
		require_fields("BOM", ("operations",))
		require_fields("BOM Operation", OPERATION, parenttype="BOM")
		if any(op.get("set_cost_based_on_bom_qty") for op in bom.get("operations") or []):
			require_fields("BOM Operation", ("base_cost_per_unit",), parenttype="BOM")
	elif bom.get("fg_based_operating_cost"):
		require_fields("BOM", FG_OPERATION)


def historical_fields(user=None):
	"""Old snapshots omit branch provenance: require the union of costing inputs.

	This checks metadata only, never mutable BOM values or historical amounts.
	The same fixed-size gate is suitable for list/count SQL permission hooks.
	"""
	quotation_fields(user=user)
	require_fields("BOM", (*BOM, *RATE_BASIS, *FG_OPERATION, "operations"), user=user, optional=OPTIONAL)
	require_fields(
		"BOM Item", (*BOM_ITEM, *MATERIAL, "stock_qty"), parenttype="BOM", user=user, optional=OPTIONAL
	)
	require_fields("BOM Operation", (*OPERATION, "base_cost_per_unit"), parenttype="BOM", user=user)
	require_fields("Profitability Analysis", SNAPSHOT, user=user)
