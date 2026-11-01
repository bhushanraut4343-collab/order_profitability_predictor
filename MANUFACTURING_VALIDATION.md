Manufacturing scenario validation
=================================

Historical manufacturing validation used Frappe/ERPNext 16.52.0 on an isolated
local development environment on 2026-10-24. No migration or configuration
change was needed. Temporary records were created using standard APIs and rolled
back. Existing quotation, BOM, analysis and price-record hashes were unchanged.
No local site, company or document identifiers are required to reproduce the
current isolated tests.

Independent live oracle: ERPNext's saved base_total_cost divided by its
get_good_qty, multiplied by each Quotation Item's stock_qty. BOM material prices
were obtained by ERPNext from new temporary Item Prices, not assigned calculated
totals. The new isolated tests additionally call ERPNext's calculate_op_cost
with save=False to verify batch and finished-good operation formulas.

| Scenario | Result and evidence |
| --- | --- |
| Multiple raw materials | PASS live: 2 at 50 + 4 at 25 = 200 materials; 40 operations; 2 FG output; quotation 6 costs 720. |
| Manufactured subassembly | PASS live: child 2 output costs 120; parent consumes 2 child units (120), plus 100 other material and 20 operations = 240 per 2 FG; 6 FG cost 720. |
| UOM conversion | PASS live: one selling pack = 12 stock units costs 1440; material packs of 2 correctly convert two packs to 4 stock units, preserving a 720 quotation cost. |
| Multiple quotation items | PASS live: two different FG rows total 1440 cost on 2400 selling, profit 960 and margin 40%. |
| Missing BOM/material rate | PASS live and isolated: costs/profit/margin remain null with Critical risks. |
| Rates change after snapshot | PASS isolated: changed date evidence never refreshes saved BOM costs; a new modeled BOM snapshot changes current cost while the historical object remains detached. No existing Item Price was overwritten. |
| Selling price changes | PASS isolated: increasing selling from 100 to 120 increases profit by 20 with unchanged cost and history. No existing Quotation was edited. |
| Operation costs | PASS live for FG-based costing; isolated ERPNext-method checks for batch scaling and tests for missing rates/time, missing FG inputs, and inconsistent saved totals. |
| Process loss/scrap | Process loss PASS live: 10 nominal units, 20% loss, 8 good units, total saved BOM cost 220, quote 8 costs 220. Scrap valuation/allocation UNSUPPORTED: live estimate safely incomplete. |
| Secondary/by-products | UNSUPPORTED: live By-Product and isolated Scrap/By-Product/Co-Product cases safely return incomplete estimates. |

Confirmed bugs fixed in profitability.py
---------------------------------------

Previously the engine could substitute recursively calculated child costs even
when the parent used valuation-based subassembly rates, or when the saved parent
amount no longer matched the child BOM. It now withholds profitability and
explains the unsupported valuation basis or stale/inconsistent parent amount.
Saved parent amounts are compared to recursively calculated child amounts within
0.02 company-currency units per parent BOM. This tolerance handles minor saved
rounding; it is not a configurable financial materiality threshold.

FG-based operating totals are now checked against required per-unit and currency
conversion inputs. Missing/inconsistent inputs cannot retain a reliable-looking
saved aggregate. Operation-level semi-finished-goods routing is explicitly
unsupported rather than silently treated as ordinary BOM costing.

Pilot scope and limits
----------------------

Use only ordinary BOMs with complete configured operation costs, correct stock
UOM conversions, and BOM-priced subassemblies whose saved costs agree with the
parent. By-products, scrap recovery credits, co-products, valuation-priced
manufactured subassemblies, variant-template BOM substitution and operation-level
semi-finished goods need further implementation before inclusion in a pilot.
Zero-cost material/operations are conservatively incomplete even if intentional.

Material rates are saved estimates. Changing Item Price alone never refreshes
saved BOM costs. Date evidence can be unknown or ambiguous (including material
UOM conversions); this does not establish actual rate freshness. Estimates are
gross manufacturing estimates, not guaranteed actual profit or full overhead.

The original manufacturing validation stage passed 70 Python tests. The latest
release-candidate validation passed 116 Python tests with no failures/skips, both
JavaScript suites and syntax, lint and configured security checks. These results
have different scopes: the historical live scenario checks above were not all
rerun by the current self-contained integration suite. No permanent business
records were changed to exercise price changes.

Latest valuation observations are separate from saved costing and require
accessible comparable purchase evidence. A recent purchase does not refresh a
BOM valuation rate or guarantee a future purchase price. Missing evidence is
informational for valuation costing; financial incompleteness is determined by
BOM costing inputs. See [PROFITABILITY.md](PROFITABILITY.md).

Fresh-install GitHub CI, latest purchase-evidence browser checks, genuine
two-company HTTP access validation and production-scale performance review remain
pending. See [TESTING.md](TESTING.md) for the current commands and coverage.
