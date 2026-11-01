# Order Profitability Predictor 0.2.0-rc.1

Estimate ERPNext Quotation manufacturing profitability, identify costing risks,
and save immutable analyses for historical comparison. This is a limited-pilot
candidate, not a guarantee of actual profit.

## Supported environment

- Tested with Frappe **16.52.0** and ERPNext **16.52.0**, on their `version-16` branches.
- Python **3.14.x** (`>=3.14,<3.15`), matching the tested Frappe runtime.
- An existing working Bench and ERPNext v16 site, with MariaDB and Redis running.
- The tested Bench uses Node.js 24.x and Yarn 1.22.x for standard Frappe assets.
- ERPNext is declared in `hooks.py` as `required_apps = ["erpnext"]`.
  Frappe and ERPNext are managed by Bench, not installed as pip dependencies.
- Flit reads the package version from `order_profitability_predictor/__init__.py`;
  `pyproject.toml` deliberately uses `dynamic = ["version"]`.

An earlier 0.1.0 build was installed and functionally checked on a fresh local
Frappe/ERPNext 16.52.0 test site. The latest release candidate has passed local
automated testing; its fresh-install GitHub Actions matrix has not run yet.
Other v16 releases are CI targets, not confirmed compatibility results.

## Installation on another ERPNext site

Use a reviewed source repository/checkout containing all implementation files;
no public repository or release URL has been created yet. Replace the placeholders
below. These are installation instructions, not commands to rerun on an already
installed site. Back up the target site before installation or migration.

```bash
cd /absolute/path/to/target/frappe-bench
bench --site <site-name> list-apps  # ERPNext must already be installed
bench get-app <reviewed-app-source>
bench --site <site-name> backup
bench --site <site-name> install-app order_profitability_predictor
bench build --app order_profitability_predictor
bench --site <site-name> clear-cache
bench --site <site-name> list-apps
```

Fresh installation syncs the app's standard Profitability Analysis DocType. For
an approved update of an existing installation, back up first and run:

```bash
bench --site <site-name> migrate
bench build --app order_profitability_predictor
bench --site <site-name> clear-cache
```

A normal migration may also run pending patches from other installed apps. Review
those first; do not skip failed patches. Reload Desk after assets or roles change.
No application migration is required merely to update this release's version or
required-app declaration. Existing installed-app version metadata can remain at
its previous value until a later approved migration.

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
source Quotation read access. Revoking source access also blocks historical
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
The complete Python suite contains 125 tests; CI must finish with no skipped tests.

## Release status

Latest local validation: **125 Python tests passed with no failures or skips**;
both JavaScript suites, syntax checks, Ruff, ESLint, Bandit and configured
pre-commit checks passed. The development npm audit reported no known
vulnerabilities at validation time. Integration fixtures rolled back with no
persistent table changes. See [TESTING.md](TESTING.md) for scope and limitations.

Before publication, complete the first GitHub CI runs (including both clean-site
matrix entries), latest purchase-evidence browser testing, genuine two-company
HTTP validation and a broader performance review. No public repository, release
package or Marketplace listing is implied by this source version.

The source version is `0.2.0-rc.1`; Python packaging normalizes this prerelease to
`0.2.0rc1`. Installed-site version records may still show an earlier version until
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
