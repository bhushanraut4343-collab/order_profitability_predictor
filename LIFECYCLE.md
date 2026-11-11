# Installation, upgrade, backup and recovery

These are operator procedures, not commands executed by opening this guide.
Use authorized change control, replace every placeholder, verify the Bench/site
identity, and protect backups as confidential financial and authentication data.
Do not put passwords or encryption keys in shell arguments, tickets or logs.

## Install and configure

Follow [README.md](README.md) for the GitHub source and standard installation.
Verify the source before installation or deployment:

```bash
cd /absolute/path/to/target/frappe-bench
git -C apps/order_profitability_predictor status --short
git -C apps/order_profitability_predictor rev-parse HEAD
bench --site <site-name> list-apps
```

Acceptance tested revision `3a24c06`, not an unreviewed future branch tip. Required
versions and role combinations are in the README. No OPP setup wizard is required.
The optional minimum-margin setting defaults to 15%; valid values are 0–100.
Open a saved Quotation to use the app. Calculations do not save unsaved form edits.

## Full backup before changes

```bash
bench --site <site-name> backup --with-files
```

Record and independently verify the generated database, public-file, private-file
and site-configuration backup paths. Preserve the site's encryption key securely;
without it, restoring database rows does not guarantee that stored credentials
can be decrypted. Preserve any separate backup-encryption material if encrypted
backups are used. Site credential encryption and backup-file encryption are
separate concerns.

Record SHA-256 checksums, then verify archives can be read and the database dump
can be decompressed. For example, for the actual generated formats:

```bash
sha256sum <database.sql.gz> <public-files.tar> <private-files.tar> <site-config.json>
gzip -t <database.sql.gz>
tar -tf <public-files.tar> > /dev/null
tar -tf <private-files.tar> > /dev/null
```

Checksums alone do not prove recoverability. Verify a restore in a separate,
owned destination, including snapshot JSON, links, attachments, permissions and
encrypted values. Keep backup manifests and encryption material access-controlled.

## Upgrade an existing installation

Back up and verify recovery first. Review local changes and the exact source diff;
never discard a dirty checkout. Arrange a maintenance window for every affected
site sharing the Bench. An operator can select an approved revision using normal
Git operations, for example a detached deployment checkout:

```bash
cd /absolute/path/to/target/frappe-bench
git -C apps/order_profitability_predictor checkout --detach <approved-revision>
bench --site <site-name> migrate
bench build --app order_profitability_predictor
bench --site <site-name> clear-cache
bench --site <site-name> list-apps
```

Do not treat a source checkout alone as an upgrade or rollback. Review framework
and dependency changes, restart the Bench's web processes through its normal
service manager when required, and reload Desk. Never use force/skip-failing
migration options to hide errors. Validate calculations, History, Compare and
restricted-user access; compare pre/post snapshot IDs, timestamps, JSON and links.
For this release, local upgrade acceptance covered `6a157c2` to `3a24c06` only.

## Uninstall data loss

**Standard uninstall deletes the Profitability Analysis DocType/table and all
saved analyses. Reinstalling creates an empty table and does not restore them.**
Application-level snapshot immutability does not prevent site-level uninstall.
Do not uninstall to fix missing buttons, denied access or stale assets.

A verified full pre-uninstall backup is required for recovery. Ordinary uninstall
is not a snapshot archive or export workflow. ERPNext source records are expected
to remain, but always verify their preservation; unrelated customizations can
change an individual site's behavior. No destructive uninstall command is supplied
as a routine customer troubleshooting step.

## Recovery into a separate destination

A full restore can return **unrelated ERPNext and customer data to the backup's
point in time**, losing later destination changes. Prefer a new isolated destination
for verification. Never restore over a site until its identity, data-loss scope
and maintenance plan have been explicitly approved.

Provision a compatible Bench with reviewed Frappe, ERPNext and OPP source revisions,
an independent database, Redis endpoints and destination site. Verify ownership,
destination identity, isolation and backup hashes before restoration. Keep web
processes, background workers and scheduling stopped, block outbound delivery and
external integration access, and disable outgoing email for the isolated test copy.
Do not rely only on settings stored in the destination database for isolation.

Securely restore the source site's required credential-encryption configuration
**before restoration, migration or any operation that could access encrypted values**.
Preserve destination database identity, credentials, sockets and Redis configuration;
do not overwrite its whole configuration with the source file. If the backup files
are separately encrypted, arrange their decryption through the installed Bench's
supported secure workflow before use. Consult `restore --help`; never expose keys
in command history or logs. Stop if isolation or encryption configuration is uncertain.

With those safeguards verified, restore the database and files:

```bash
cd /absolute/path/to/destination/frappe-bench
bench --site <new-destination-site> restore <absolute-database.sql.gz> \
  --with-public-files <absolute-public-files.tar> \
  --with-private-files <absolute-private-files.tar>
```

**Restoring the database may overwrite destination site settings**, including email,
scheduler and external integration settings with the source values. Keep the
independent process/network safeguards in place. After restoration, recheck and
reapply destination email suppression, paused scheduling and disabled integrations;
verify destination database/Redis identity and required encryption configuration
again. Complete these checks **before migration or enabling normal operations**.

Only after those checks pass, run:

```bash
bench --site <new-destination-site> migrate
bench build --app order_profitability_predictor
bench --site <new-destination-site> clear-cache
```

A failed restore or migration requires investigation, not force or partial-success
assumptions. Keep normal operations disabled until recovery validation succeeds.

Before opening the destination to users, verify installed apps, original snapshot
IDs, values (including unknown values), JSON hashes, dates and source links;
Quotation/BOM/control records; accounting and stock; roles and field permissions;
public/private attachment hashes and private-file denials; authorized/restricted
HTTP access; and decryption of a known encrypted test value without logging it.
Recheck backup hashes after use. Recovery must not modify the source environment.

## Completed local lifecycle acceptance

Frappe/ERPNext 16.52.0 was used in independent disposable environments.

| Scenario | Verified result |
| --- | --- |
| Fresh installation | Standard install, migration, build, schema, functionality, permissions and 127 control records passed. Repeated install/migration did not duplicate data. |
| Upgrade | `6a157c2` to `3a24c06` preserved both original snapshots, values, JSON, dates and links; backup and idempotency checks passed. |
| Full backup/restore | Independent destination restored complete/incomplete snapshots, attachments, permissions, encrypted credentials and 134 control records. |
| Uninstall | Both original snapshots and their DocType/table were removed; unrelated ERPNext records remained intact. |
| Reinstallation | Table initially empty; exactly one new synthetic analysis was created; functionality, permissions and idempotency passed. |
| Separate recovery | Pre-uninstall backup restored both original snapshots independently of the reinstalled environment. |

These are completed local acceptance results, not guarantees for arbitrary site
customizations or other versions. Authenticated HTTP/API checks are distinct from
manual Chrome verification. See [TESTING.md](TESTING.md).
