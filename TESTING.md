# Developer checks for 0.2.0-rc.1

Supported runtime: Frappe/ERPNext v16, Python 3.14 and Node 24. CI targets both
v16.52.0 and the current `version-16` branches, using MariaDB 11.8 and Redis 7.
A passing local target does not establish a passing GitHub matrix.

## Static and JavaScript checks

From the app repository:

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

Check new files explicitly with `pre-commit run --files <new-files>` before staging.
Hooks may normalize whitespace but never stage or commit. ESLint uses
`eslint.config.mjs`; the original scaffold `.eslintrc` is not used by ESLint 10.
The development lockfile overrides minimatch to patched 11.0.3 for
GHSA-g3hv-75wg-m249. Recheck lint/glob compatibility when updating ESLint. There
are no JavaScript production dependencies. Bandit and dependency audits
supplement, rather than prove, application security.

## Disposable integration environments only

Do not run fixture-generating tests against shared development, pilot or production
sites. SQL rollback cannot restore Frappe's MyISAM `__global_search` table, and
Redis search queues/caches can outlive a rolled-back fixture transaction.

Use a newly provisioned, disposable Bench, site/database and private Redis endpoints.
CI is the reproducible automated provisioning path. Local operators must provision
a separate Bench and record ownership of all new resources before running tests.
Do not copy either a permanent site's configuration or its database. A private,
unprivileged MariaDB instance with its own data directory/Unix socket avoids
requiring changes to existing database users, permissions or services. Private
Redis instances can use unused loopback ports, unique directories, `save ""` and
`appendonly no`. Do not reuse or flush a shared Redis instance.

Install ERPNext then this app through standard Bench/Frappe APIs on the new site.
Configure `redis_cache`, `redis_queue` and `redis_socketio` only in that disposable
Bench/site. One private Redis process per role is suitable locally; CI uses a
job-isolated container with distinct logical databases. Verify PING for all roles.
Do not start existing Bench services or change their configuration for these tests.

After provisioning, replace every placeholder below; the site must start with
`opp-it-` (local) or `opp-ci` (CI). From the disposable Bench, use its Python:

```bash
# Explicit acknowledgement that the new environment can be discarded.
# Verifies Redis connectivity, records database identity and endpoints,
# and refuses to overwrite an existing marker.
env/bin/python apps/order_profitability_predictor/scripts/test_environment.py --bench <disposable-bench> --site <opp-it-unique.localhost>

# Full suite: any skipped integration/security test makes the run fail.
env/bin/python -B apps/order_profitability_predictor/scripts/run_tests.py --bench <disposable-bench> --site <opp-it-unique.localhost> --integration

# Unit-only mode: opt-in database tests are explicitly skipped.
env/bin/python -B apps/order_profitability_predictor/scripts/run_tests.py --bench <disposable-bench> --site <opp-it-unique.localhost>
```

The marker is an accident-prevention guard, not a security boundary against
arbitrary code or an operator who deliberately marks shared data disposable.
Never mark a shared environment. The runner requires an explicit Bench path and
matching marker before database tests. It refuses the known permanent development
and pilot sites and rejects changed database identities or Redis endpoints.

Readiness checks fail before fixtures if any Redis role is unavailable. The runner
activates Frappe's test context, so cache failure cannot silently trigger direct
SQL search indexing. Search indexing is not disabled; it remains contained within
the disposable database/Redis resources. No permissions or security assertions
are bypassed. All application calculations use the unchanged production engine.

## Fixtures and side-effect verification

Fixtures use unique companies, accounts/warehouses, groups, items, price lists,
customers, BOMs, company-scoped Fiscal Years, quotations, users and snapshots.
Missing standard Transit Warehouse Type, tree roots and stock UOM are created
through normal document APIs, only when absent. Existing masters are not changed.
No setup-complete flag is bypassed and the full setup wizard is not invoked.

BOMs have output quantity 2, material cost 200 and configured finished-good
operation cost 40; quotations sell 6 units for 1200. No calculated BOM cost totals
are forced and no purchasing, stock or accounting transactions are created.
Purchase-evidence edge cases use isolated mocks and actual permission-aware
queries against the generated materials.

Commits are blocked during fixture tests. Per-test savepoints and final rollback
remain in place. Before/after fingerprints check business, child, authentication
and configuration tables, excluding operational logs. Business-table changes fail
the suite. The derived MyISAM search table is reported separately: it may change
only inside the explicitly disposable database, and rollback is never claimed to
restore it. Its exclusion from business-table equality is not permission to run
these tests on shared sites. Test Redis queues can retain pending search entries;
discarding the entire owned environment provides isolation.

Frappe's IntegrationTestCase class setup commits automatically. These suites use
unittest with Frappe document APIs and explicit transactions instead. The supplied
runner is the supported entry point. Run sequentially on a quiet environment.

Cleanup must validate the run identifier, resource paths, ownership and process
identities/start times. Stop only processes started by that run. Remove only its
private directories/database, never an existing site or global search table.
Leave uncertain resources untouched. The test runner does not delete resources;
CI runners discard their own fresh services, and local provisioning owns cleanup.

## Validation status and remaining coverage

The isolated local run passed **125 Python tests, zero failures and zero skips**,
including staff permissions, revoked source access through REST handlers, lists,
reports/count/value queries, sharing denial, cross-quotation references and
historical immutability. No persistent database/search-index changes were detected
in that run. Seven additional environment guards cover protected sites, markers,
configuration changes, readiness and refusal of direct search SQL fallback.

JavaScript suites, syntax, lint and configured security checks supplement the
Python suite. Genuine two-company authenticated HTTP tests, browser sessions,
production-scale load testing and both updated GitHub CI matrix runs remain
separate checks. Local validation used the available v16.52.0 sources; support for
the moving `version-16` target still requires its GitHub job to pass.

The CI workflow grants read-only repository access, uses no publishing credentials
or pull_request_target event, and creates a fresh Bench/site for each matrix entry.
It verifies host Redis binaries before Bench initialization, then verifies all
three configured Redis endpoints before running fixtures. CI service passwords
are disposable runner credentials, not production secrets.
