"""Run unittest discovery with optional rollback-only site integration tests."""

import argparse
import hashlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1]


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--site", required=True, help="Existing disposable test site")
	parser.add_argument("--integration", action="store_true")
	args = parser.parse_args()
	if args.site == "erpnext.localhost" or not any(word in args.site for word in ("test", "ci")):
		parser.error("Use an explicitly named test/CI site; development/business sites are refused.")
	# Standard bench layout; never change site configuration or default site.
	bench = APP.parents[1]
	os.chdir(bench / "sites")
	os.environ["OPP_RUN_SITE_TESTS"] = "1" if args.integration else "0"
	os.environ["OPP_RUN_SECURITY_TESTS"] = "1" if args.integration else "0"
	import frappe

	frappe.init(site=args.site)
	baseline = None

	def fingerprint():
		# Include all business, child, authentication and configuration tables.
		# Exclude only framework operational logs; no confidential values are printed.
		values = {}
		for table in frappe.db.get_tables():
			if table.startswith(("__", "tab")) and not table.endswith((" Log", " Log Detail")):
				quoted = table.replace("`", "``")
				rows = frappe.db.sql(f"SELECT * FROM `{quoted}`", as_dict=True)
				encoded = sorted(frappe.as_json(row) for row in rows)
				values[table] = hashlib.sha256("\n".join(encoded).encode()).hexdigest()
		return values

	def forbid_commit(*_args, **_kwargs):
		raise AssertionError("Database commits are forbidden during app tests")

	try:
		if args.integration:
			frappe.connect()
			frappe.set_user("Administrator")
			baseline = fingerprint()
			frappe.db.rollback()
		suite = unittest.defaultTestLoader.discover(str(APP / "order_profitability_predictor/tests"))
		with patch("frappe.database.database.Database.commit", forbid_commit):
			result = unittest.TextTestRunner(verbosity=2).run(suite)
		if args.integration and result.skipped:
			raise AssertionError("Full integration run must not skip tests")
		return 0 if result.wasSuccessful() else 1
	finally:
		if args.integration:
			frappe.set_user("Administrator")
			frappe.db.rollback()
			if baseline is not None:
				after = fingerprint()
				changed = sorted(
					key for key in baseline.keys() | after.keys() if baseline.get(key) != after.get(key)
				)
				print("Persistent table changes:", changed)
				if changed:
					raise AssertionError("Test rollback did not preserve site data")
			frappe.db.rollback()
		frappe.destroy()


if __name__ == "__main__":
	sys.exit(main())
