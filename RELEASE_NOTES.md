# Release notes: 0.2.0

**Unpublished release preparation.** Source version: `0.2.0`. Historical acceptance tested revision `3a24c06` (`0.2.0-rc.1`). Final-release validation remains required. These notes do not establish a published tag, GitHub release, Marketplace submission, subscription plan or support commitment.

Publisher onboarding and an attempted US$9/site/month plan are approved next steps, not completed or verified Marketplace configuration. Billing, cancellation and refunds must follow verified applicable rules. No seven-day refund guarantee or subscriber-notification capability is advertised. MIT software rights remain separate from paid services. Publisher tax obligations require separate verification.

## Features and behavior

- Estimate saved Quotation manufacturing cost, gross profit and gross margin from
  saved BOM material and operation costs, including supported nested BOMs and process loss.
- Explain incomplete costing and rate-evidence risks without assuming unknown values are zero.
- Show permitted comparable purchase observations separately from saved valuation costs.
- Save server-generated immutable analyses and compare historical JSON with current estimates.
- Enforce current source, company and financial-field permissions across calculations,
  snapshots, History and Compare; block snapshot sharing.

## Compatibility and validation

Full local acceptance covers Frappe/ERPNext 16.52.0 with Python 3.14.x, Node 24.x, MariaDB and Redis. ERPNext is required. Separate local automated validation passed 145 Python tests on Frappe 16.54.0 / ERPNext 16.53.0. Historical CI for commit `3a24c06` passed static checks and both configured integration targets, with 145 tests per integration job. These narrower automated results do not extend full acceptance to other versions. Final-release CI is still required; comprehensive manual browser acceptance is not claimed. See [TESTING.md](TESTING.md).

Fresh installation, upgrade from `6a157c2`, backup/restore, uninstall/reinstallation
and separate backup recovery passed. See [LIFECYCLE.md](LIFECYCLE.md).

## Data-loss warning

**Uninstall deletes Profitability Analysis snapshots. Reinstallation starts empty.**
Recover only from a verified pre-uninstall backup with files and preserved encryption
configuration. Full restoration may also return unrelated data to the backup's
point in time. See the lifecycle guide before planning any uninstall or recovery.

## Known limitations

No scrap-recovery/secondary-product allocation, valuation-priced manufactured
subassemblies, operation-level semi-finished routing or variant-template BOM
substitution. Missing/zero rates and inconsistent saved costing remain incomplete.
Saved BOM costs are estimates, not guaranteed actual profit; purchase evidence
never automatically refreshes them. Evidence has exact company/currency/UOM and
permission requirements and bounded searches. See [README.md](README.md) and
[PROFITABILITY.md](PROFITABILITY.md) for scope.

Performance acceptance is conditional: absolute targets and targeted small-only
concurrency gates passed, while the earlier mixed-workload 2× failure remains.
History used 215 queries per measured page and needs future optimization review.
No production-capacity guarantee is made. See [PERFORMANCE.md](PERFORMANCE.md).
