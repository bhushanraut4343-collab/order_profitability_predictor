"""Opt-in staff/security integration tests with unique, rolled-back fixtures."""

import hashlib
import os
import unittest
from uuid import uuid4

import frappe
from frappe import client
from frappe.api.v1 import read_doc

from order_profitability_predictor.api import check_quotation_profitability, save_quotation_analysis
from order_profitability_predictor.history import compare_quotation_analysis, get_quotation_history
from order_profitability_predictor.tests.site_fixtures import make_manufacturing_fixture


@unittest.skipUnless(os.environ.get("OPP_RUN_SECURITY_TESTS") == "1", "Opt-in temporary-user security suite")
class StaffPermissionsLiveTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.original_user = frappe.session.user
		frappe.connect()
		frappe.set_user("Administrator")
		cls.users = {}
		cls.counts = {
			dt: frappe.db.count(dt)
			for dt in [
				"User",
				"Customer",
				"User Permission",
				"Quotation",
				"Profitability Analysis",
				"Company",
				"BOM",
				"Item",
			]
		}
		cls.refs = [("User", name) for name in frappe.get_all("User", pluck="name")]
		cls.before = cls.source_hashes()
		token = uuid4().hex[:12]
		try:
			for key, roles in {
				"sales": ["Sales Manager"],
				"sales_manufacturing": ["Sales Manager", "Manufacturing User"],
				"sales_user_manufacturing": ["Sales User", "Manufacturing User"],
				"system": ["System Manager"],
				"system_full": ["System Manager", "Sales User", "Manufacturing User"],
				"manufacturing": ["Manufacturing User"],
			}.items():
				user = frappe.get_doc(
					dict(
						doctype="User",
						email=f"opp-{token}-{key}@example.invalid",
						first_name="OPP Temporary Security Test",
						enabled=1,
						user_type="System User",
						send_welcome_email=0,
						roles=[dict(role=r) for r in roles],
					)
				).insert()
				cls.users[key] = user.name
			cls.fixture = make_manufacturing_fixture()
			cls.Q = cls.fixture.quotation
			cls.Q2 = cls.fixture.other_quotation
			cls.B = cls.fixture.bom
			cls.A = cls.fixture.analysis
		except Exception:
			frappe.db.rollback()
			frappe.set_user(cls.original_user)
			raise

	@classmethod
	def source_hashes(cls):
		return [
			hashlib.sha256(frappe.as_json(frappe.get_doc(dt, name).as_dict()).encode()).hexdigest()
			for dt, name in cls.refs
		]

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for user in cls.users.values():
			frappe.clear_cache(user=user)
		frappe.db.rollback()
		assert not any(frappe.db.exists("User", u) for u in cls.users.values())
		assert cls.before == cls.source_hashes(), "Existing demo source changed"
		assert cls.counts == {dt: frappe.db.count(dt) for dt in cls.counts}, "Temporary records remain"
		print(
			"\nStaff test rollback verified: temporary users/permissions/analyses absent; existing records unchanged."
		)
		frappe.set_user(cls.original_user)

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("opp_staff_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="opp_staff_test")
		for user in self.users.values():
			frappe.clear_cache(user=user)

	def use(self, key):
		frappe.set_user(self.users[key])

	def restrict(self, allow, value, applicable_for=None):
		frappe.set_user("Administrator")
		frappe.get_doc(
			dict(
				doctype="User Permission",
				user=self.users["sales_manufacturing"],
				allow=allow,
				for_value=value,
				apply_to_all_doctypes=int(not applicable_for),
				applicable_for=applicable_for,
			)
		).insert()
		frappe.clear_cache(user=self.users["sales_manufacturing"])
		self.use("sales_manufacturing")

	def restrict_source_access(self):
		self.restrict("Quotation", self.Q2, "Quotation")
		self.assertFalse(frappe.has_permission("Quotation", "read", doc=self.Q))

	def test_sales_manager_alone_cannot_calculate_without_bom_access(self):
		self.use("sales")
		self.assertTrue(frappe.has_permission("Quotation", "read", doc=self.Q))
		self.assertFalse(frappe.has_permission("BOM", "read", doc=self.B))
		self.assertTrue(frappe.has_permission("Profitability Analysis", "read", doc=self.A))
		with self.assertRaises(frappe.PermissionError):
			check_quotation_profitability(self.Q)

	def test_sales_manager_plus_manufacturing_can_calculate_and_save(self):
		self.use("sales_manufacturing")
		result = check_quotation_profitability(self.Q)
		self.assertEqual(result["estimated_total_cost"], 720)
		self.assertEqual(compare_quotation_analysis(self.Q, self.A)["changes"]["expected_gross_profit"], 0)
		self.assertTrue(any(row["name"] == self.A for row in get_quotation_history(self.Q)["analyses"]))
		self.assertEqual(read_doc("Profitability Analysis", self.A).name, self.A)
		saved = save_quotation_analysis(self.Q)
		self.assertEqual(read_doc("Profitability Analysis", saved["name"]).quotation, self.Q)

	def test_sales_user_plus_manufacturing_can_only_calculate(self):
		self.use("sales_user_manufacturing")
		self.assertEqual(check_quotation_profitability(self.Q)["estimated_total_cost"], 720)
		self.assertFalse(frappe.has_permission("Profitability Analysis", "read"))
		self.assertFalse(frappe.has_permission("Profitability Analysis", "create"))
		with self.assertRaises(frappe.PermissionError):
			get_quotation_history(self.Q)
		with self.assertRaises(frappe.PermissionError):
			save_quotation_analysis(self.Q)

	def test_system_manager_alone_needs_quotation_and_bom_roles(self):
		self.use("system")
		self.assertFalse(frappe.has_permission("Quotation", "read", doc=self.Q))
		self.assertFalse(frappe.has_permission("BOM", "read", doc=self.B))
		self.assertFalse(frappe.has_permission("Profitability Analysis", "read", doc=self.A))
		with self.assertRaises(frappe.PermissionError):
			read_doc("Profitability Analysis", self.A)
		with self.assertRaises(frappe.PermissionError):
			check_quotation_profitability(self.Q)

	def test_system_manager_with_sales_and_manufacturing_roles(self):
		self.use("system_full")
		self.assertEqual(check_quotation_profitability(self.Q)["expected_gross_margin_percentage"], 40)
		self.assertEqual(read_doc("Profitability Analysis", self.A).name, self.A)

	def test_unauthorized_staff_cannot_read_snapshot_or_endpoints(self):
		self.use("manufacturing")
		for fn, args in [
			(check_quotation_profitability, (self.Q,)),
			(save_quotation_analysis, (self.Q,)),
			(get_quotation_history, (self.Q,)),
			(compare_quotation_analysis, (self.Q, self.A)),
			(read_doc, ("Profitability Analysis", self.A)),
			(client.get_list, ("Profitability Analysis",)),
		]:
			with self.subTest(method=fn.__name__), self.assertRaises(frappe.PermissionError):
				fn(*args)

	def test_custom_endpoints_reject_revoked_source_access(self):
		self.use("sales_manufacturing")
		self.assertEqual(check_quotation_profitability(self.Q)["estimated_total_cost"], 720)
		self.restrict_source_access()
		for fn, args in [
			(check_quotation_profitability, (self.Q,)),
			(save_quotation_analysis, (self.Q,)),
			(get_quotation_history, (self.Q,)),
			(compare_quotation_analysis, (self.Q, self.A)),
		]:
			with self.subTest(method=fn.__name__), self.assertRaises(frappe.PermissionError):
				fn(*args)

	def test_revoked_source_access_must_block_standard_snapshot_rest(self):
		self.restrict_source_access()
		with self.assertRaises(frappe.PermissionError):
			read_doc("Profitability Analysis", self.A)

	def test_revoked_source_access_must_hide_standard_snapshot_list(self):
		self.restrict_source_access()
		rows = client.get_list("Profitability Analysis", fields=["name"], filters={"name": self.A})
		self.assertEqual(rows, [])

	def test_direct_quotation_user_permission_also_restricts_snapshot_link(self):
		self.restrict("Quotation", self.Q2)
		with self.assertRaises(frappe.PermissionError):
			read_doc("Profitability Analysis", self.A)
		self.assertEqual(
			client.get_list("Profitability Analysis", fields=["name"], filters={"name": self.A}), []
		)

	def test_wrong_quotation_analysis_reference_rejected(self):
		self.use("sales_manufacturing")
		with self.assertRaises(frappe.PermissionError):
			compare_quotation_analysis(self.Q2, self.A)

	def test_company_restriction_on_permission_engine(self):
		# Site has only one company. Exercise another company in-memory only;
		# this is not claimed as a two-company REST integration test.
		self.restrict("Company", self.fixture.company)
		for dt, name in [("Quotation", self.Q), ("BOM", self.B), ("Profitability Analysis", self.A)]:
			doc = frappe.get_doc(dt, name)
			self.assertTrue(frappe.has_permission(dt, "read", doc=doc))
			doc.company = "OPP-NONEXISTENT-OTHER-COMPANY"
			self.assertFalse(frappe.has_permission(dt, "read", doc=doc))

	def test_revoked_source_hidden_from_report_query_and_count(self):
		from frappe.desk.reportview import execute

		self.restrict_source_access()
		self.assertFalse(execute("Profitability Analysis", fields=["name"], filters={"name": self.A}))
		self.assertEqual(client.get_count("Profitability Analysis", filters={"name": self.A}), 0)
		self.assertEqual(
			client.get_value("Profitability Analysis", "snapshot_json", filters={"name": self.A}), {}
		)

	def test_snapshot_sharing_cannot_override_source_security(self):
		from frappe.share import add_docshare

		# Even Administrator cannot create a bypassing snapshot share via normal APIs.
		with self.assertRaises(frappe.PermissionError):
			add_docshare("Profitability Analysis", self.A, user=self.users["manufacturing"], notify=0)
		self.assertFalse(
			frappe.db.exists("DocShare", {"share_doctype": "Profitability Analysis", "share_name": self.A})
		)

	def test_purchase_evidence_hidden_without_purchase_roles(self):
		from order_profitability_predictor.purchase_evidence import observed_purchase_evidence

		self.use("sales_manufacturing")
		basis = dict(company=self.fixture.company, item_code=self.fixture.raw, uom="Nos")
		evidence = observed_purchase_evidence([basis], "INR")
		self.assertEqual(evidence[(self.fixture.company, self.fixture.raw, "Nos")], {"status": "unavailable"})
