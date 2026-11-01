"""Unique, transaction-local manufacturing masters built through document APIs.

Call only inside a rollback-protected test transaction. No ERPNext test-record
loader, existing company, global defaults, direct cost writes or commits are used.
"""

from uuid import uuid4

import frappe
from frappe.utils import nowdate


def make_manufacturing_fixture(costing_basis="Price List"):
	token = uuid4().hex[:10]
	prefix = f"OPP Test {token}"
	company = frappe.get_doc(
		dict(
			doctype="Company",
			company_name=prefix,
			abbr=token[:5].upper(),
			default_currency="INR",
			country="India",
			create_chart_of_accounts_based_on="Standard Template",
			chart_of_accounts="Standard",
		)
	).insert()
	group = frappe.get_doc(
		dict(doctype="Item Group", item_group_name=prefix, parent_item_group="All Item Groups")
	).insert()
	price_list = frappe.get_doc(
		dict(doctype="Price List", price_list_name=prefix, currency="INR", buying=1, selling=1, enabled=1)
	).insert()
	items = {}
	for kind in ("Raw", "Finished"):
		items[kind] = frappe.get_doc(
			dict(
				doctype="Item",
				item_code=f"{prefix} {kind}",
				item_name=f"{prefix} {kind}",
				item_group=group.name,
				stock_uom="Nos",
				is_stock_item=1,
				valuation_rate=100 if kind == "Raw" else 0,
				is_purchase_item=int(kind == "Raw"),
				is_sales_item=1,
			)
		).insert()
	frappe.get_doc(
		dict(
			doctype="Item Price",
			item_code=items["Raw"].name,
			price_list=price_list.name,
			uom="Nos",
			currency="INR",
			price_list_rate=100,
			valid_from=nowdate(),
		)
	).insert()
	bom = frappe.get_doc(
		dict(
			doctype="BOM",
			item=items["Finished"].name,
			company=company.name,
			currency="INR",
			quantity=2,
			is_active=1,
			is_default=1,
			rm_cost_as_per=costing_basis,
			buying_price_list=price_list.name,
			fg_based_operating_cost=1,
			operating_cost_per_bom_quantity=20,
			items=[dict(item_code=items["Raw"].name, qty=2, uom="Nos")],
		)
	).insert()
	bom.submit()
	assert (bom.base_raw_material_cost, bom.base_operating_cost, bom.base_total_cost) == (200, 40, 240)
	customer_group = frappe.get_doc(
		dict(
			doctype="Customer Group",
			customer_group_name=prefix,
			parent_customer_group="All Customer Groups",
			is_group=0,
		)
	).insert()
	territory = frappe.get_doc(
		dict(doctype="Territory", territory_name=prefix, parent_territory="All Territories", is_group=0)
	).insert()
	customer = frappe.get_doc(
		dict(
			doctype="Customer",
			customer_name=f"{prefix} Customer",
			customer_type="Company",
			customer_group=customer_group.name,
			territory=territory.name,
		)
	).insert()
	quotations = []
	for _ in range(2):
		quotation = frappe.get_doc(
			dict(
				doctype="Quotation",
				quotation_to="Customer",
				party_name=customer.name,
				company=company.name,
				currency="INR",
				conversion_rate=1,
				selling_price_list=price_list.name,
				price_list_currency="INR",
				plc_conversion_rate=1,
				transaction_date=nowdate(),
				items=[
					dict(item_code=items["Finished"].name, qty=6, uom="Nos", conversion_factor=1, rate=200)
				],
			)
		).insert()
		assert quotation.items[0].base_net_amount == 1200
		quotations.append(quotation.name)
	from order_profitability_predictor.api import save_quotation_analysis

	analysis = save_quotation_analysis(quotations[0])["name"]
	return frappe._dict(
		company=company.name,
		raw=items["Raw"].name,
		finished=items["Finished"].name,
		bom=bom.name,
		quotation=quotations[0],
		other_quotation=quotations[1],
		analysis=analysis,
	)
