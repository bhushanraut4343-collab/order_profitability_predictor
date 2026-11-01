"""Accidental shared-site access and Redis failure must stop before fixtures."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

spec = importlib.util.spec_from_file_location(
	"opp_test_environment", Path(__file__).resolve().parents[2] / "scripts/test_environment.py"
)
environment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(environment)


class DisposableEnvironmentTests(unittest.TestCase):
	def setUp(self):
		self.directory = tempfile.TemporaryDirectory(prefix="opp-env-unit-")
		self.addCleanup(self.directory.cleanup)
		self.bench = Path(self.directory.name)
		self.site = "opp-it-unit.localhost"
		(self.bench / "sites" / self.site).mkdir(parents=True)
		self.config = {role: f"redis://127.0.0.1:50000/{i}" for i, role in enumerate(environment.REDIS_ROLES)}
		(self.bench / "sites/common_site_config.json").write_text(json.dumps(self.config))
		self.site_config = self.bench / "sites" / self.site / "site_config.json"
		self.site_config.write_text(json.dumps({"db_name": "opp_unit_database"}))

	def test_shared_sites_are_refused(self):
		for site in environment.PROTECTED_SITES:
			with self.subTest(site=site), self.assertRaises(ValueError):
				environment.environment_config(self.bench, site)

	def test_marker_required_and_cannot_be_overwritten(self):
		with self.assertRaises(FileNotFoundError):
			environment.require_disposable(self.bench, self.site)
		environment.mark_disposable(self.bench, self.site)
		self.assertEqual(environment.require_disposable(self.bench, self.site), self.bench)
		with self.assertRaises(FileExistsError):
			environment.mark_disposable(self.bench, self.site)

	def test_changed_database_is_refused(self):
		environment.mark_disposable(self.bench, self.site)
		self.site_config.write_text(json.dumps({"db_name": "different_database"}))
		with self.assertRaises(ValueError):
			environment.require_disposable(self.bench, self.site)

	def test_changed_redis_is_refused(self):
		environment.mark_disposable(self.bench, self.site)
		self.config["redis_queue"] = "redis://127.0.0.1:50001/0"
		(self.bench / "sites/common_site_config.json").write_text(json.dumps(self.config))
		with self.assertRaises(ValueError):
			environment.require_disposable(self.bench, self.site)

	def test_all_three_redis_endpoints_must_answer(self):
		client = MagicMock()
		client.__enter__.return_value.ping.return_value = True
		with patch("redis.Redis.from_url", return_value=client) as connect:
			environment.check_redis(self.config)
		self.assertEqual(connect.call_count, 3)
		self.assertEqual({c.args[0] for c in connect.call_args_list}, set(self.config.values()))

	def test_redis_failure_is_fatal_without_credential_disclosure(self):
		with patch("redis.Redis.from_url", side_effect=RuntimeError("private-password-sentinel")):
			with self.assertRaises(RuntimeError) as raised:
				environment.check_redis(self.config)
		self.assertNotIn("private-password-sentinel", str(raised.exception))
		self.assertIn("no fixtures were created", str(raised.exception))

	def test_missing_cache_cannot_fall_back_to_nontransactional_sql(self):
		import frappe
		from frappe.utils.global_search import sync_value_in_queue
		from redis.exceptions import ConnectionError as RedisConnectionError

		self.assertTrue(frappe.flags.in_test)
		with (
			patch.object(frappe.cache, "lpush", side_effect=RedisConnectionError),
			patch("frappe.utils.global_search.sync_value") as direct_sql,
		):
			with self.assertRaises(AssertionError):
				sync_value_in_queue({"doctype": "User", "name": "synthetic-test"})
		direct_sql.assert_not_called()
