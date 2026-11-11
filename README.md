# Order Profitability Predictor 0.2.0

Estimate ERPNext Quotation manufacturing profitability, identify costing risks, and save immutable analyses for historical comparison. Estimates are not a guarantee of actual profit.

## Supported environment

- Tested with Frappe **16.52.0** and ERPNext **16.52.0**, on their `version-16` branches.
- Python **3.14.x** (`>=3.14,<3.15`), matching the tested Frappe runtime.
- An existing working Bench and ERPNext v16 site, with MariaDB and Redis running.
- The tested Bench uses Node.js 24.x and Yarn 1.22.x for standard Frappe assets.
- ERPNext is declared in `hooks.py` as `required_apps = ["erpnext"]`.
  Frappe and ERPNext are managed by Bench, not installed as pip dependencies.
- Flit reads the package version from `order_profitability_predictor/__init__.py`;
  `pyproject.toml` deliberately uses `dynamic = ["version"]`.

Full local lifecycle, security and performance acceptance covers Frappe/ERPNext **16.52.0**. Separate automated validation passed 145 Python tests on Frappe **16.54.0** / ERPNext **16.53.0**; this narrower result does not establish full acceptance on that combination. A historical CI run also passed both configured v16 targets. Moving `version-16` branches do not establish compatibility with future revisions. v15 and other Python versions remain unverified.

## Installation and upgrades

Repository: <https://github.com/bhushanraut4343-collab/order_profitability_predictor>
The URL matches the configured Git origin. Historical CI evidence is recorded below; public repository availability and passing CI for the final release commit must be confirmed before publication.

For a new installation, use an existing initialized ERPNext site and an authorized
Bench administrator. Replace all angle-bracket placeholders before running:

```bash
cd /absolute/path/to/target/frappe-bench
bench --site <site-name> list-apps
bench --site <site-name> backup --with-files
bench get-app --branch version-16 https://github.com/bhushanraut4343-collab/order_profitability_predictor.git
bench --site <site-name> install-app order_profitability_predictor
bench --site <site-name> migrate
bench build --app order_profitability_predictor
bench --site <site-name> clear-cache
bench --site <site-name> list-apps
```

ERPNext must already be installed. Run `get-app` only if this Bench does not
already contain the app checkout. The branch can move: verify the reviewed
revision before installation. Completed acceptance covers `3a24c06`, version
`0.2.0-rc.1`; a published `0.2.0` tag is not available from this documentation.
Migration affects the whole site and may run pending patches from other apps;
review those first and never skip failures. A Bench checkout may serve multiple
sites, so updating its source requires a coordinated deployment plan.

See [lifecycle operations](LIFECYCLE.md) for revision verification, upgrade,
full backup and recovery procedures. See [troubleshooting](TROUBLESHOOTING.md)
for access and browser problems.

**Uninstall deletes the Profitability Analysis DocType/table and saved snapshots.**
Reinstallation creates an empty table and does not recover historical analyses.
Recovery requires a verified pre-uninstall backup, files and securely preserved
site encryption configuration. Restoring a full backup may also restore unrelated
site data to the backup's point in time. Do not uninstall as a troubleshooting step.

## Roles and access

Calculations require read access to the Quotation and every relevant BOM. Saved
analyses grant create/read access to System Manager and Sales Manager, with no
write/delete/share permissions. **Sales Manager alone does not have default BOM
read access**: choose an approved role combination with the necessary Quotation,
BOM, and Company permissions. Temporary-user tests validated Sales Manager +
Manufacturing User for the full app, and Sales User + Manufacturing User for
calculation only. System Manager alone lacks Quotation/BOM access; System Manager
+ Sales User + Manufacturing User was validated for full access.

History/comparison endpoints check both Quotation and analysis read permission.
Direct saved-record viewing and lists require both snapshot permission and current
source Quotation read access and current visibility of the financial inputs. Restricted or
masked source financial fields deny the whole calculation instead of returning partial
figures. Child fields use their parent DocType permissions. Historical records do not
retain full costing-branch provenance, so viewing them requires the combined set of
source costing-field permissions, including operation inputs, plus snapshot payload
permissions. Sales Manager alone cannot read saved costs without BOM field access.
Purchase-price evidence has separate purchase-field checks; unavailable evidence never
changes BOM costs. Revoking source access also blocks historical
snapshots. Snapshot sharing is blocked to prevent standard share overrides.
Guest and ordinary portal users have no default access.

## Use and configuration

Open a saved draft/submitted Quotation and click **Check Profitability**.
**Save Analysis** generates a fresh server-side snapshot; **View History** compares
stored snapshots with a freshly calculated estimate. These actions do not save
unsaved Quotation edits or update saved BOM rates.

The minimum gross margin defaults to 15%. A Bench administrator can configure it:

```bash
bench --site <site-name> set-config order_profitability_minimum_margin 15 --parse
bench --site <site-name> clear-cache
```

Valid values are 0–100. There is no public settings-write endpoint. Rate review
uses a fixed 90-day age rule. A matching purchase transaction date is evidence,
not proof of which rate the BOM used. Item Price validity dates are explicitly
identified as price-list dates, never purchase dates; unknown dates stay unknown.

### Inventory valuation and purchase evidence

Valuation-based material costs are labeled **Inventory Valuation**. Profitability
continues to use saved BOM rates. The dialog separately shows the latest observed
purchase price and evidence date from relevant accessible submitted, non-return
Purchase Receipts and Purchase Invoices. These prices are observations, not
supplier quotations or guaranteed future purchasing costs.

Evidence requires the same company, a transaction in the company's base currency,
and the exact BOM material UOM. No currency or UOM conversion is inferred. Queries
respect document access and price disclosure also checks field permissions. Users
without the necessary purchase access receive an informational message without
purchase prices, document references or dates. Newest conflicting prices, missing
or inaccessible evidence and search limits are handled conservatively.

The 90-day rule applies to the purchase evidence date, not to the saved valuation
rate. BOM modification dates and Update Cost do not prove supplier-price
freshness. Evidence review is bounded to 500 matching rows per purchase document
type/company and 30 document checks per calculation. It may withhold observations
for larger histories. Purchase observations are live-only and are excluded from
newly saved analysis snapshots; existing snapshots are never rewritten.

## Manufacturing scope and limitations

Supported validation covers ordinary single/multilevel BOMs, stock-UOM conversion,
multiple Quotation items, configured manufacturing operations, and process loss.
BOM-priced subassembly amounts must agree with the saved parent costs.

Unsupported cases return incomplete estimates and withhold cost/profit/margin:

- Scrap valuation/recovery credits and secondary/by-product/co-product allocation.
- Valuation-priced manufactured subassemblies.
- Operation-level semi-finished goods routing.
- Variant-template default BOM substitution.

Missing/zero material or operation costs are conservatively incomplete, including
intentional free inputs. Saved BOM costs are estimates: changing Item Price does
not refresh a BOM. Price List and Last Purchase Rate retain their existing date
warnings; missing valuation purchase evidence produces information rather than a
claim about the saved rate's age. These are base-currency,
tax-exclusive gross manufacturing estimates, not full actual-cost accounting.

Details: [calculation/configuration](PROFITABILITY.md),
[analysis/history](ANALYSIS_HISTORY.md), and
[manufacturing validation](MANUFACTURING_VALIDATION.md).

## Tests and CI

See [TESTING.md](TESTING.md) for reproducible unit, disposable-only integration,
JavaScript, lint and security checks. Tests generate their own unique records and
require no local demo company or record IDs. GitHub Actions provisions fresh
Frappe/ERPNext v16 sites for both v16.52.0 and the current `version-16` branches.
Historical CI for commit `3a24c06` completed 145 Python tests in each integration job. Final-release CI must pass on the exact release commit with no skipped tests.

## Release status

An earlier isolated local run passed 125 Python tests without failures or skips. Subsequent local validation passed 145 tests without failures or skips. Saved results for [GitHub Actions run 41340177899](https://github.com/bhushanraut4343-collab/order_profitability_predictor/actions/runs/41340177899), dated 1 November 2026 and linked to commit `3a24c06`, record successful static checks and both integration jobs, with 145 tests per integration job. These historical results do not cover subsequent uncommitted changes or the planned final `0.2.0` release. See [TESTING.md](TESTING.md) for evidence scope.

Local acceptance completed fresh installation, upgrade, backup/restore,
uninstall/reinstallation, authenticated cross-company security and bounded
performance testing. These local automated/API results are separate from hosted CI evidence and do not establish comprehensive manual browser acceptance. Genuine screenshot captures provide narrower UI evidence. See [validation scope](TESTING.md),
[lifecycle results](LIFECYCLE.md) and [performance findings](PERFORMANCE.md).
Phase 5 is conditionally signed off: the earlier mixed-workload 2× concurrency
failure remains documented, and History uses 215 SQL queries per measured page.
No production-capacity guarantee is made.

Draft changes for the planned release are in [0.2.0 release notes](RELEASE_NOTES.md).
The source version is `0.2.0`. Preparing this source does not establish a published release, Marketplace listing, completed publisher onboarding, configured subscription price or verified public policy URLs. Historical validation remains attributed to its tested revisions; final-release validation must identify the exact release commit.

Installed-site version records may still show an earlier version until
a separately approved deployment/migration. No existing site update is needed
merely to prepare these source files.

## Publisher and support

Publisher: **Bhushan Raut**. The copyright notice names Bhushan Raut; ownership
and permission to release all included contributions remain to be verified before
publication. Public support/contact: [bhushanraut4343@gmail.com](mailto:bhushanraut4343@gmail.com).
This support address is intentionally public; Git commit email privacy is a
separate setting.

## License

MIT; see [license.txt](license.txt). Paid distribution does not remove the rights
granted by this license.
