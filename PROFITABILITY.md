# Calculation and risk warnings

From an initialized Frappe Python context:

```python
from order_profitability_predictor.profitability import calculate_quotation_profitability
result = calculate_quotation_profitability("YOUR-QUOTATION-NAME")
```

The engine checks source Quotation and BOM read permissions. Selling value uses
`base_net_amount`, excluding taxes, and manufacturing quantities use `stock_qty`.
Default BOMs must match the item/company and be active and submitted. Populated
custom Quotation Item Link fields pointing to BOM are honored. Conflicting
explicit BOM selections produce incomplete results. Alternative quotation rows
are excluded to match ERPNext totals.

## Cost calculations

Saved BOM material amounts and configured operation costs are scaled using
ERPNext's `get_good_qty`: production quantity less process loss. BOM-priced
subassemblies are inspected recursively; their costs replace the parent material
line rather than being added twice. Saved parent and child costs must agree.
The app never updates BOM rates, saved costs, quotations or material prices.

Missing/zero material or operation costs, invalid quantities, circular references,
inconsistent saved amounts and unsupported manufacturing configurations produce
incomplete estimates. Total cost, profit and margin remain `None`; the UI shows
**Not available**. `known_items_cost` is a partial subtotal, not a reliable complete
manufacturing cost. Completeness describes configured BOM data, not assurance
that every real overhead or manufacturing expense has been recorded.

## Risk classifications and configuration

Responses include `risks` with `severity`, `code` and `message`; the string
`warnings` list is retained for Python callers.

- **Critical:** missing, inconsistent or unsupported costing data.
- **Warning:** low estimated margin or potentially outdated/unknown rate evidence
  where the applicable costing basis calls for that warning.
- **Information:** assumptions, inventory valuation basis and unavailable or
  recent comparable purchase observations.

Risks never alter financial totals or cost completeness. Incomplete estimates do
not receive a low-margin warning. The minimum gross margin defaults to 15%; an
authorized Bench administrator can change it using standard site configuration.
Replace the site placeholder before running these administration commands:

```bash
bench --site <site-name> set-config order_profitability_minimum_margin 15 --parse
bench --site <site-name> clear-cache
```

Only finite values from 0 to 100 are valid. There is no settings-write HTTP
endpoint. Rate review uses a fixed 90-day rule: evidence older than 90 days is
stale; evidence exactly 90 days old is not. Dates use the site's current date.

## Evidence by costing basis

**Price List:** matching Item Price records must agree on price list, item, UOM,
currency and rate, be valid for the saved BOM date, and have remained unchanged
since that snapshot. A uniquely matching `valid_from` is a price-list effective
date, never a purchase transaction date. Inaccessible, ambiguous or otherwise
unreliable evidence remains unknown. Foreign-currency price-list evidence is
not inferred.

**Last Purchase Rate:** permission-filtered submitted Purchase Orders, Purchase
Receipts and Purchase Invoices provide matching company/UOM/base-net-rate date
evidence; returns are excluded. At most 20 recent documents per type are
inspected, constrained by the saved BOM timestamp. Matching evidence does not
prove which document established the saved BOM rate. This path retains its
existing behavior and is distinct from the valuation observations below.

**Inventory Valuation:** saved valuation-based BOM rates remain the calculation
inputs. The dialog separately lists observed purchase price, UOM, document and
evidence date from accessible submitted, non-return Purchase Receipts and
Purchase Invoices. These observations never replace valuation rates and do not
establish the age of the saved valuation. They are not guaranteed future costs.

Valuation observations require the same company, the exact BOM material UOM and
a transaction in the company's base currency. No FX or UOM conversions are
inferred. Document and field permissions protect disclosure. Missing,
inaccessible or non-comparable evidence produces an informational message without
private purchase details. Conflicting newest prices suppress a selected price;
identical duplicate evidence is handled without adding costs twice. Unknown times
are not assumed to precede known times on the same date. Future-dated and invalid
rate/quantity evidence is excluded.

Queries batch material codes by company and transaction type rather than issue
one list query per BOM material. Review is capped at 500 matching rows per type
and company and 30 purchase document checks per calculation. Limits withhold
uncertain observations; this is not an exhaustive purchase-history report. If a
whole transaction type is inaccessible, the app does not claim complete latest
price evidence. Neither `BOM.modified` nor Update Cost proves supplier freshness.

Purchase observations are live-only. New snapshots omit the valuation purchase
observations and their related live messages; previously saved records are never
rewritten. See [analysis history](ANALYSIS_HISTORY.md), [manufacturing scope](MANUFACTURING_VALIDATION.md)
and [developer checks and validation status](TESTING.md).
