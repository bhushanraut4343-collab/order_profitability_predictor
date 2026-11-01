# Saved analyses and historical comparison

Profitability Analysis is a standard app DocType installed with the app. An
approved update that changes schema uses the standard site migration after a
backup. Replace the placeholder and review other pending app patches first:

```bash
bench --site <site-name> backup
bench --site <site-name> migrate
```

These commands are deployment examples, not steps to repeat merely because this
release candidate's source metadata changed. Fresh installation syncs the DocType.

## Save and view

Open a saved Quotation, click **Check Profitability**, then **Save Analysis**.
Every save computes a fresh server-side result and creates a separate snapshot;
the browser does not supply trusted financial values, timestamps or user identity.
Saving can therefore differ from an earlier preview if saved source data changed.
The app does not save unsaved form edits or update the Quotation/BOM.

Snapshots retain quotation, company/base currency, analysis time/user, financial
values, completeness, risks and item breakdown. New snapshots exclude live
valuation purchase-price observations and their related messages to prevent
purchase data from becoming accessible under snapshot-only permissions. Existing
snapshots remain unchanged.

Stored JSON preserves numeric values and `null`. Summary fields deliberately use
read-only Data fields to avoid coercing missing financial values to numeric zero.
Missing costs, profit and margin display **Not available**. Ordinary document
updates and deletion are rejected, including normal Administrator API attempts.
Source quotation, BOM or price changes never recalculate earlier snapshots.

## Permissions

Sales Manager and System Manager receive create/read snapshot permissions, with
no write/delete/share/export/print/email grants. Creating a snapshot also requires
read access to the Quotation and relevant BOMs. Standard ERPNext role combinations
are described in [README.md](README.md); a role name alone does not override
company, User Permission or document restrictions.

Viewing a snapshot requires both its role permissions and current source
Quotation read access. Missing/invalid source links are denied. Standard REST
reads, lists, report queries and count/value access use the registered permission
hooks. Snapshot sharing is blocked because standard shares could otherwise
bypass query filtering. These application rules do not restrict trusted database
administrators or arbitrary server-side code using permission-bypassing APIs.

## History and comparison

**View History** lists 20 saved analyses per page, newest first, with date,
financial values, completeness and analyst. Equal dates are ordered by creation
time and name. No saved history produces an empty-state message.

Select a snapshot and click **Compare with Current Estimate**. Historical values
come from saved JSON, while current values are calculated afresh. Changes are
current minus historical; margin changes are percentage points. Margin direction
is increased, decreased, unchanged or unavailable. Incomplete estimates, missing
values and differing companies/currencies suppress financial deltas instead of
assuming zero. Viewing or comparing does not create or alter snapshots.

The authenticated POST history/comparison endpoints require Quotation and
analysis read access. Lists use permission-aware queries and each returned
snapshot is checked individually. Comparison checks both the stored Link and
snapshot JSON against the requested Quotation, preventing cross-quotation access.

## Validation

Automated coverage includes server-generated snapshots, null handling, historical
immutability, ordering, comparison arithmetic, role restrictions, revoked source
access, REST handlers/lists/reports/count/value queries, sharing denial and
cross-quotation rejection. The latest complete local suite passed 116 tests;
fixtures were rolled back with persistent table hashes unchanged. JavaScript
suites cover dialog behavior, escaping, pagination and incomplete results.

Earlier fresh-site basic save/history/comparison checks passed. Latest
purchase-evidence browser checks, authenticated two-company HTTP testing,
production-scale permissions/performance review and GitHub CI runs remain
separate release checks. See [TESTING.md](TESTING.md) for reproducible commands.
