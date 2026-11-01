# Developer checks for 0.2.0-rc.1

Supported runtime: Frappe/ERPNext v16 (CI targets v16.52.0 and the current
`version-16` branches; GitHub runs remain pending), Python 3.14, Node 24, Yarn 1.22, MariaDB 11.8 and Redis 7.
The moving branch deliberately detects upstream compatibility failures.

## Local tools

From this app repository, install development-only tools into an isolated Python
environment, then install the locked JavaScript dependencies:

```bash
python3.14 -m venv .venv-ci
. .venv-ci/bin/activate
pip install -r requirements-dev.txt
npm ci --ignore-scripts
ruff check .
ruff format --check .
npm run lint
npm audit --audit-level=moderate
npm run check:syntax
npm test
bandit -r order_profitability_predictor -x order_profitability_predictor/tests
pre-commit run --all-files --show-diff-on-failure
```

Pre-commit checks tracked files; before staging new files, check them explicitly
with `pre-commit run --files <new-files>`. It may normalize whitespace. Install
Git hooks with `pre-commit install` only when desired. No hook commits or stages.
The development lockfile overrides minimatch to patched 11.0.3 for
GHSA-g3hv-75wg-m249; recheck lint/glob compatibility when updating ESLint.
There are no JavaScript production dependencies.

ESLint uses the flat `eslint.config.mjs` configuration; the original scaffold
`.eslintrc` is not used by ESLint 10. Bandit scans production Python; security tests themselves are run by unittest.
These tools supplement, rather than prove, application security.

## Python tests

Use a dedicated test site with ERPNext and this app already installed. From the
**Bench** directory, using Bench's Python environment:

```bash
# Fast mocked unit tests; opt-in database test classes are explicitly skipped.
env/bin/python -B apps/order_profitability_predictor/scripts/run_tests.py --site your-test-site.localhost

# Complete unit + database + staff security suite; any skip fails this run.
env/bin/python -B apps/order_profitability_predictor/scripts/run_tests.py --site your-test-site.localhost --integration
```

Replace `your-test-site.localhost` with your own disposable site. Never use a
production site. The runner rejects sites without `test` or `ci` in their name
and includes an additional development-site denylist. Naming alone does not establish safety:
choose an actual disposable development site. The runner performs no installation,
migration, configuration change or setup wizard, and does not switch default sites.

Integration fixtures create unique companies (and their standard accounts and
warehouses), item/customer groups, items, price lists, BOMs, customers, quotations,
users, permissions and snapshots using normal document APIs. No existing demo
records or local IDs are required. The valuation fixture uses the Item valuation
rate; the price-list fixture uses Item Price. Both BOMs have output quantity 2,
material cost 200 and finished-good operation cost 40; quotations sell 6 for 1200.
No saved calculated BOM totals are assigned and no purchasing/stock/accounting
transactions are created. Purchase evidence edge cases use isolated mocks and
real read-only query regressions against the generated materials.

The runner forbids database commits, rolls back fixtures on success/failure and
compares all non-log table contents, including authentication and child tables,
before/after. Staff tests use per-test savepoints and clear temporary-user caches.
Run sequentially on a quiet test site: concurrent business activity would correctly
fail the preservation check. Framework operational logs/caches can change.
Avoid killing the test process; connection closure still rolls back uncommitted
SQL, but final verification then cannot run.

Frappe's `IntegrationTestCase.setUpClass` commits automatically. These suites
instead use unittest with standard Frappe document APIs, savepoints and explicit
rollback so they are safe on an existing test site and need no global test-record
loader. The provided runner is the supported entry point for this safety contract.

Current complete suite: **116 Python tests**, including role access, revoked
Quotation access through REST handlers/lists/reports/count/value queries, sharing,
cross-quotation references, snapshot immutability and purchase-evidence disclosure.
Company restrictions include in-memory denial checks; genuine two-company HTTP
and browser-session integration remains a separate validation task.

## GitHub Actions

`.github/workflows/ci.yml` runs static checks and a two-entry integration matrix.
Each entry provisions a fresh disposable Bench/site, installs ERPNext followed by
this app, migrates **that CI site only**, builds the app, and runs all Python tests
without skips. It never connects to local development sites. CI database/admin
passwords are disposable service credentials, not production secrets.

The workflow uses read-only repository permissions, no publishing/deployment
credentials and no `pull_request_target`. Pull requests run as untrusted code
without privileged secrets. Review external dependencies and framework updates.
A successful local test run does not establish a passing GitHub run: inspect both
matrix entries and the static job before release. Browser tests, Marketplace
review, cross-company HTTP coverage and performance/load testing are separate.

## Recorded validation status

The latest local complete run passed **116 tests, zero failures and zero skips**.
The fast unit-only run passed 95 tests and explicitly skipped 21 opt-in database
checks; use `--integration` for the release gate. Both JavaScript suites and
syntax checks, Ruff lint/format, ESLint, Bandit and all configured pre-commit
checks passed. The development npm audit found no known vulnerabilities at that
time. Before/after table checks found no persistent fixture changes.

An earlier app build passed fresh local installation and basic functional tests.
That is separate from validation of this candidate's GitHub workflow, which has
not been executed on GitHub. Browser testing of the latest purchase observations,
real two-company HTTP access checks and load testing remain pending. The tests
exercise server-side REST handlers and permission queries, not authenticated
browser sessions or a complete network/API penetration test.
