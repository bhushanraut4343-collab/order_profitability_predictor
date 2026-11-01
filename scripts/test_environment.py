"""Explicit disposable-environment marker and fail-fast Redis readiness checks."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

PROTECTED_SITES = {"erpnext.localhost", "opp-pilot-test.localhost"}
REDIS_ROLES = ("redis_cache", "redis_queue", "redis_socketio")
MARKER = ".opp-disposable-test.json"
DB_FIELDS = ("db_name", "db_user", "db_host", "db_port", "db_socket", "db_type")


def environment_config(bench, site):
	bench = Path(bench).resolve(strict=True)
	if site in PROTECTED_SITES or not site.startswith(("opp-ci", "opp-it-")):
		raise ValueError("Integration tests require a dedicated disposable opp-ci/opp-it site")
	if Path(site).name != site:
		raise ValueError("Invalid test site name")
	path = bench / "sites" / site
	if path.is_symlink():
		raise ValueError("Disposable site must not be a symlink")
	common = json.loads((bench / "sites/common_site_config.json").read_text())
	config = {**common, **json.loads((path / "site_config.json").read_text())}
	if not config.get("db_name"):
		raise ValueError("Missing disposable database")
	if any(not config.get(role) for role in REDIS_ROLES):
		raise ValueError("All three Redis endpoints must be explicitly configured")
	return bench, config


def mark_disposable(bench, site):
	"""Explicit opt-in, only after provisioning a new throwaway environment.

	This is an accident-prevention guard, not a security boundary against a user
	who can edit configuration or run arbitrary Python. Never mark a shared site.
	"""
	bench, config = environment_config(bench, site)
	marker = dict(
		run_id=uuid4().hex,
		bench=str(bench),
		site=site,
		database={key: config.get(key) for key in DB_FIELDS},
		redis={role: config[role] for role in REDIS_ROLES},
	)
	with (bench / MARKER).open("x") as stream:
		json.dump(marker, stream)
	return marker


def require_disposable(bench, site):
	bench, config = environment_config(bench, site)
	marker = json.loads((bench / MARKER).read_text())
	if not marker.get("run_id") or marker.get("bench") != str(bench) or marker.get("site") != site:
		raise ValueError("Disposable environment marker does not match this Bench/site")
	if marker.get("database") != {key: config.get(key) for key in DB_FIELDS}:
		raise ValueError("Disposable database configuration changed")
	if marker.get("redis") != {role: config[role] for role in REDIS_ROLES}:
		raise ValueError("Disposable Redis configuration changed")
	return bench


def check_redis(config):
	from redis import Redis

	for role in REDIS_ROLES:
		try:
			with Redis.from_url(config[role], socket_connect_timeout=3, socket_timeout=3) as client:
				if client.ping() is not True:
					raise RuntimeError("Unexpected PING response")
		except Exception:
			# Connection exceptions can contain credential-bearing URLs.
			raise RuntimeError(f"Disposable {role} is unavailable; no fixtures were created") from None
		print(f"Redis readiness: {role} OK")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--bench", type=Path, required=True)
	parser.add_argument("--site", required=True)
	args = parser.parse_args()
	_, config = environment_config(args.bench, args.site)
	check_redis(config)
	mark_disposable(args.bench, args.site)
	print("Disposable environment explicitly marked; no database records changed.")
