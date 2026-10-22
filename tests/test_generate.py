from tempfile import TemporaryDirectory
import os
import unittest

from harness import ApiError, entity_id
from provision.config import normalize_config
from provision.generate import generate
from provision.models import BudgetAction
from provision.plan import ProvisionPlan, _plan_group
from provision.manifest import load_manifest
from teardown_testbed import _delete


def _account(values):
    return {
        "type": "VIEW_ID_CONDITION",
        "viewField": {
            "fieldId": "awsUsageaccountid",
            "fieldName": "Account",
            "identifier": "AWS",
            "identifierName": "AWS",
        },
        "viewOperator": "IN",
        "values": values,
    }


def _tag():
    return {
        "type": "VIEW_ID_CONDITION",
        "viewField": {
            "fieldId": "labels.value",
            "fieldName": "env",
            "identifier": "LABEL",
            "identifierName": "label",
        },
        "viewOperator": "IN",
        "values": ["prod"],
    }


TARGETS = [
    {
        "name": "platform",
        "rules": [
            {
                "viewConditions": [
                    _account(
                        [
                            "Alpha Delivery (111111111111)",
                            "Beta Delivery (222222222222)",
                        ]
                    ),
                    _tag(),
                ]
            }
        ],
    },
    {"name": "labels-only", "rules": [{"viewConditions": [_tag()]}]},
]


def _config(**overrides):
    raw = {
        "cost_category": "AccountBudgets-testbed",
        "perspective": {
            "folder": "{bucket}",
            "name": "{account_label}",
            "rule_mode": "account_with_sibling_conditions",
        },
        "budget": {"name": "{perspective_name}"},
        "budget_group": {"name": "{bucket}"},
    }
    raw.update(overrides)
    return normalize_config(raw)


class FakeHarness:
    def __init__(self, fail=None):
        self.account_id = "acct"
        self.folders = {}
        self.perspectives = {}
        self.budgets = {}
        self.groups = {}
        self.fail = set(fail or [])
        self.attempts = []

    def find_folder(self, name):
        return self.folders.get(name)

    def create_folder(self, name):
        item = {"name": name, "uuid": f"folder:{name}"}
        self.folders[name] = item
        return item

    def find_perspective(self, name):
        return self.perspectives.get(name)

    def create_perspective(self, payload):
        item = {"name": payload["name"], "uuid": f"perspective:{payload['name']}"}
        self.perspectives[payload["name"]] = item
        self.attempts.append(("perspective", payload))
        return item

    def update_perspective(self, perspective_id, payload):
        self.attempts.append(("perspective_update", payload))
        item = {
            "name": payload["name"],
            "uuid": perspective_id,
            "folderId": payload.get("folderId"),
        }
        self.perspectives[payload["name"]] = item
        return item

    def find_budget(self, name):
        return self.budgets.get(name)

    def create_budget(self, payload):
        self.attempts.append(("budget", payload))
        self._gate(payload["name"])
        item = {
            "name": payload["name"],
            "uuid": f"budget:{payload['name']}",
            "budgetAmount": payload.get("budgetAmount") or 0,
            "startTime": payload.get("startTime"),
        }
        self.budgets[payload["name"]] = item
        return item

    def update_budget(self, budget_id, payload):
        self.attempts.append(("budget_update", payload))
        item = {
            "name": payload["name"],
            "uuid": budget_id,
            "budgetAmount": payload.get("budgetAmount") or 0,
            "startTime": payload.get("startTime"),
        }
        self.budgets[payload["name"]] = item
        return item

    def find_budget_group(self, name):
        return self.groups.get(name)

    def create_budget_group(self, payload):
        self.attempts.append(("group", payload))
        item = {
            "name": payload["name"],
            "uuid": f"group:{payload['name']}",
            "startTime": payload.get("startTime"),
        }
        self.groups[payload["name"]] = item
        return item

    def update_budget_group(self, group_id, payload):
        self.attempts.append(("group_update", payload))
        item = {
            "name": payload["name"],
            "uuid": group_id,
            "startTime": payload.get("startTime"),
        }
        self.groups[payload["name"]] = item
        return item

    def _gate(self, name):
        if name in self.fail:
            raise ApiError(400, f"rejected {name}")


class GenerateTest(unittest.TestCase):
    def test_category_and_account_filters_by_bucket_and_account(self):
        config = _config(
            perspective={
                "folder": "{bucket}",
                "name": "{account_label}",
                "rule_mode": "category_and_account",
            }
        )
        harness = FakeHarness()
        result = generate(
            config,
            TARGETS,
            apply=True,
            harness=harness,
            category={"name": "AccountBudgets-testbed", "uuid": "cc-1"},
        )
        self.assertEqual(result["errors"], [])
        created = [
            attempt for attempt in harness.attempts if attempt[0] == "perspective"
        ]
        conditions = created[0][1]["viewRules"][0]["viewConditions"]
        self.assertEqual(conditions[0]["viewField"]["fieldId"], "cc-1")
        self.assertEqual(conditions[0]["viewField"]["identifier"], "BUSINESS_MAPPING")
        self.assertEqual(conditions[0]["values"], ["platform"])
        self.assertEqual(
            conditions[1]["values"], ["Alpha Delivery (111111111111)"]
        )
        self.assertEqual(len(conditions), 2)

    def test_category_and_account_requires_the_category_id(self):
        config = _config(
            perspective={
                "folder": "{bucket}",
                "name": "{account_label}",
                "rule_mode": "category_and_account",
            }
        )
        with self.assertRaises(ValueError) as caught:
            generate(config, TARGETS, apply=True, harness=FakeHarness())
        self.assertIn("cost category id is required", str(caught.exception))

    def test_update_mode_replaces_perspective_rules(self):
        config = _config(
            perspective={
                "folder": "{bucket}",
                "name": "{account_label}",
                "rule_mode": "category_and_account",
            },
            behavior={"on_exists": "update"},
        )
        harness = FakeHarness()
        harness.folders["platform"] = {"name": "platform", "uuid": "folder:new"}
        harness.perspectives["Alpha Delivery (111111111111)"] = {
            "name": "Alpha Delivery (111111111111)",
            "uuid": "perspective:kept",
            "folderId": "folder:old",
        }
        generate(
            config,
            TARGETS,
            apply=True,
            harness=harness,
            category={"name": "AccountBudgets-testbed", "uuid": "cc-1"},
        )
        updated = [
            attempt
            for attempt in harness.attempts
            if attempt[0] == "perspective_update"
        ]
        self.assertEqual(updated[0][1]["uuid"], "perspective:kept")
        self.assertEqual(updated[0][1]["folderId"], "folder:old")
        self.assertEqual(
            updated[0][1]["viewRules"][0]["viewConditions"][0]["values"],
            ["platform"],
        )

    def test_spreadsheet_names_drive_folder_views_budgets_and_group(self):
        config = normalize_config(
            {
                "cost_category": "AccountBudgets",
                "budget": {
                    "type": "SPECIFIED_AMOUNT",
                    "period": "YEARLY",
                    "amount": 1,
                    "monthly_breakdown": True,
                    "start": "2026-04-01",
                },
                "spreadsheet": {
                    "file": "budgets.csv",
                    "key": "account",
                    "only": True,
                    "columns": {
                        "account_id": "Account ID",
                        "account_name": "Account Name",
                        "folder": "Folder",
                        "amount": "Annual Budget",
                        "alerts": [],
                    },
                },
            }
        )
        config["spreadsheet"]["rows"] = {
            "111111111111": {
                "account_id": "111111111111",
                "account_name": "Alpha",
                "folder": "Platform",
                "amount": 1200,
                "monthly_amounts": [],
                "alerts": [],
                "warnings": [],
            },
            "222222222222": {
                "account_id": "222222222222",
                "account_name": "Beta",
                "folder": "Platform",
                "amount": 2400,
                "monthly_amounts": [],
                "alerts": [],
                "warnings": [],
            },
        }
        harness = FakeHarness()

        result = generate(
            config,
            TARGETS,
            apply=True,
            harness=harness,
            category={"name": "AccountBudgets", "uuid": "cc-1"},
        )

        self.assertEqual(result["errors"], [])
        self.assertEqual(set(harness.folders), {"Platform"})
        self.assertEqual(set(harness.perspectives), {"Alpha", "Beta"})
        self.assertEqual(set(harness.budgets), {"Alpha - FY27", "Beta - FY27"})
        self.assertEqual(set(harness.groups), {"Platform - FY27"})

    def test_different_folders_in_one_bucket_prevent_the_group(self):
        config = normalize_config(
            {
                "cost_category": "AccountBudgets",
                "budget": {
                    "type": "SPECIFIED_AMOUNT",
                    "period": "MONTHLY",
                    "amount": 10,
                },
                "spreadsheet": {
                    "file": "budgets.csv",
                    "key": "account",
                    "only": True,
                    "columns": {
                        "account_id": "Account ID",
                        "account_name": "Account Name",
                        "folder": "Folder",
                        "amount": "Amount",
                        "alerts": [],
                    },
                },
            }
        )
        config["spreadsheet"]["rows"] = {
            account_id: {
                "account_id": account_id,
                "account_name": name,
                "folder": folder,
                "amount": 10,
                "monthly_amounts": [],
                "alerts": [],
                "warnings": [],
            }
            for account_id, name, folder in (
                ("111111111111", "Alpha", "Folder A"),
                ("222222222222", "Beta", "Folder B"),
            )
        }
        harness = FakeHarness()

        result = generate(
            config,
            TARGETS,
            apply=True,
            harness=harness,
            category={"name": "AccountBudgets", "uuid": "cc-1"},
        )

        # Whole-plan validation fails before any mutations.
        self.assertEqual(harness.folders, {})
        self.assertEqual(harness.perspectives, {})
        self.assertEqual(harness.budgets, {})
        self.assertEqual(harness.groups, {})
        self.assertEqual(result["errors"][0]["kind"], "budget_group")
        self.assertIn("same folder", result["errors"][0]["error"])

    def test_dry_run_does_not_create(self):
        harness = FakeHarness()
        result = generate(_config(), TARGETS, apply=False, harness=harness)
        self.assertTrue(result["dry_run"])
        self.assertEqual(harness.attempts, [])
        self.assertEqual(result["accounts"], 2)
        self.assertEqual(result["skipped"][0]["bucket"], "labels-only")

    def test_apply_creates_one_group_for_the_bucket(self):
        harness = FakeHarness()
        result = generate(_config(), TARGETS, apply=True, harness=harness)
        self.assertEqual(result["errors"], [])
        perspectives = [
            attempt for attempt in harness.attempts if attempt[0] == "perspective"
        ]
        budgets = [attempt for attempt in harness.attempts if attempt[0] == "budget"]
        groups = [attempt for attempt in harness.attempts if attempt[0] == "group"]
        self.assertEqual(len(perspectives), 2)
        self.assertEqual(len(budgets), 2)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(perspectives[0][1]["viewRules"][0]["viewConditions"]), 2)
        children = groups[0][1]["childEntities"]
        self.assertEqual(
            [child["id"] for child in children],
            [
                "budget:Alpha Delivery (111111111111)",
                "budget:Beta Delivery (222222222222)",
            ],
        )
        self.assertNotIn("proportion", children[0])
        self.assertEqual(groups[0][1]["cascadeType"], "NO_CASCADE")
        self.assertEqual(budgets[0][1]["startTime"], groups[0][1]["startTime"])
        self.assertEqual(budgets[0][1]["period"], groups[0][1]["period"])

    def test_update_mode_updates_budgets_before_their_group(self):
        harness = FakeHarness()
        generate(_config(), TARGETS, apply=True, harness=harness)
        harness.attempts = []
        config = _config(
            budget={
                "name": "{perspective_name}",
                "type": "SPECIFIED_AMOUNT",
                "period": "MONTHLY",
                "amount": 250,
                "monthly_breakdown": False,
            },
            behavior={"on_exists": "update"},
        )

        result = generate(config, TARGETS, apply=True, harness=harness)

        self.assertEqual(result["errors"], [])
        # Executor applies folders, then all perspectives, then budgets, then groups.
        self.assertEqual(
            [attempt[0] for attempt in harness.attempts],
            [
                "perspective_update",
                "perspective_update",
                "budget_update",
                "budget_update",
                "group_update",
            ],
        )
        budget_updates = [
            attempt for attempt in harness.attempts if attempt[0] == "budget_update"
        ]
        self.assertEqual(
            [attempt[1]["budgetAmount"] for attempt in budget_updates],
            [250, 250],
        )
        self.assertEqual(harness.attempts[-1][1]["budgetGroupAmount"], 500)

    def test_update_mode_versions_a_new_fiscal_year(self):
        harness = FakeHarness()
        old_config = _config(
            budget={
                "name": "{perspective_name}",
                "type": "SPECIFIED_AMOUNT",
                "period": "YEARLY",
                "amount": 1200,
                "monthly_breakdown": True,
                "start": "2026-04-01",
            }
        )
        generate(old_config, TARGETS, apply=True, harness=harness)
        harness.attempts = []
        new_config = _config(
            budget={
                "name": "{perspective_name}",
                "type": "SPECIFIED_AMOUNT",
                "period": "YEARLY",
                "amount": 2400,
                "monthly_breakdown": True,
                "start": "2027-04-01",
            },
            behavior={"on_exists": "update"},
        )

        result = generate(new_config, TARGETS, apply=True, harness=harness)

        self.assertEqual(result["errors"], [])
        creates = [attempt for attempt in harness.attempts if attempt[0] == "budget"]
        updates = [
            attempt for attempt in harness.attempts if attempt[0] == "budget_update"
        ]
        groups = [attempt for attempt in harness.attempts if attempt[0] == "group"]
        self.assertEqual(updates, [])
        self.assertEqual(
            [attempt[1]["name"] for attempt in creates],
            ["Alpha Delivery (111111111111) - FY28", "Beta Delivery (222222222222) - FY28"],
        )
        self.assertEqual(groups[0][1]["name"], "platform - FY28")
        self.assertIn("platform - FY27", harness.groups)
        self.assertIn("platform - FY28", harness.groups)

        harness.attempts = []
        generate(new_config, TARGETS, apply=True, harness=harness)
        self.assertEqual(
            [attempt[0] for attempt in harness.attempts],
            [
                "perspective_update",
                "perspective_update",
                "budget_update",
                "budget_update",
                "group_update",
            ],
        )

    def test_buckets_keep_their_own_period_and_amount(self):
        config = _config(
            budget={
                "type": "SPECIFIED_AMOUNT",
                "period": "MONTHLY",
                "amount": 100,
                "monthly_breakdown": False,
            },
            buckets={
                "budgets": {
                    "annual": {
                        "period": "ANNUAL",
                        "amount": 1200,
                        "monthly_breakdown": True,
                        "start": "year_start",
                    }
                }
            },
        )
        targets = [
            {
                "name": "monthly",
                "rules": [{"viewConditions": [_account(["One (111111111111)"])]}],
            },
            {
                "name": "annual",
                "rules": [{"viewConditions": [_account(["Two (222222222222)"])]}],
            },
        ]
        harness = FakeHarness()
        generate(config, targets, apply=True, harness=harness)
        budgets = [attempt for attempt in harness.attempts if attempt[0] == "budget"]
        groups = [attempt for attempt in harness.attempts if attempt[0] == "group"]
        self.assertEqual(budgets[0][1]["period"], "MONTHLY")
        self.assertEqual(budgets[0][1]["budgetAmount"], 100)
        self.assertNotIn("budgetMonthlyBreakdown", budgets[0][1])
        self.assertEqual(budgets[1][1]["period"], "YEARLY")
        self.assertAlmostEqual(budgets[1][1]["budgetAmount"], 1200)
        months = budgets[1][1]["budgetMonthlyBreakdown"]["budgetMonthlyAmount"]
        self.assertEqual(len(months), 12)
        self.assertEqual(groups[0][1]["period"], "MONTHLY")
        self.assertEqual(groups[1][1]["period"], "YEARLY")
        self.assertEqual(
            groups[1][1]["budgetGroupMonthlyBreakdown"]["budgetBreakdown"], "MONTHLY"
        )

    def test_each_account_budget_rolls_up_to_the_group(self):
        config = _config(
            budget={
                "type": "SPECIFIED_AMOUNT",
                "period": "YEARLY",
                "amount": 1,
                "monthly_breakdown": False,
                "start": "year_start",
            },
            buckets={
                "budgets": {
                    "hosted": {
                        "monthly_breakdown": True,
                        "accounts": {
                            "111111111111": {"amount": 400},
                            "222222222222": {"amount": 800},
                        },
                    }
                }
            },
        )
        targets = [
            {
                "name": "hosted",
                "rules": [
                    {
                        "viewConditions": [
                            _account(
                                [
                                    "Alpha (111111111111)",
                                    "Beta (222222222222)",
                                    "Gamma (333333333333)",
                                ]
                            )
                        ]
                    }
                ],
            }
        ]
        harness = FakeHarness()
        result = generate(config, targets, apply=True, harness=harness)
        budgets = [attempt for attempt in harness.attempts if attempt[0] == "budget"]
        groups = [attempt for attempt in harness.attempts if attempt[0] == "group"]
        self.assertEqual([item[1]["budgetAmount"] for item in budgets], [400, 800])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0][1]["budgetGroupAmount"], 1200)
        self.assertEqual(len(groups[0][1]["childEntities"]), 2)
        self.assertEqual(
            result["skipped"][-1]["reason"], "no budget configured for this account"
        )

    def test_spreadsheet_amounts_roll_up_and_unknown_rows_are_reported(self):
        from contextlib import redirect_stdout
        from io import StringIO

        config = _config(
            budget={
                "type": "SPECIFIED_AMOUNT",
                "period": "YEARLY",
                "amount": 1,
                "monthly_breakdown": False,
                "start": "year_start",
            },
            spreadsheet={
                "file": "budgets.csv",
                "key": "account",
                "only": True,
                "columns": {
                    "account_id": "Account ID",
                    "amount": "Annual Budget",
                    "alerts": [],
                },
            },
        )
        config["spreadsheet"]["rows"] = {
            "111111111111": {
                "amount": 400,
                "alerts": [
                    {
                        "percentage": 80,
                        "based_on": "ACTUAL_COST",
                        "emails": ["a@example.com"],
                    }
                ],
                "account_name": None,
                "warnings": ["Alert 80 is enabled with no recipients"],
            },
            "999999999999": {
                "amount": 5,
                "alerts": [],
                "account_name": None,
                "warnings": [],
            },
        }
        targets = [
            {
                "name": "hosted",
                "rules": [
                    {
                        "viewConditions": [
                            _account(
                                [
                                    "Alpha (111111111111)",
                                    "Beta (222222222222)",
                                ]
                            )
                        ]
                    }
                ],
            }
        ]
        harness = FakeHarness()
        output = StringIO()
        with redirect_stdout(output):
            result = generate(config, targets, apply=True, harness=harness)
        budgets = [attempt for attempt in harness.attempts if attempt[0] == "budget"]
        groups = [attempt for attempt in harness.attempts if attempt[0] == "group"]
        self.assertEqual(len(budgets), 1)
        self.assertEqual(budgets[0][1]["budgetAmount"], 400)
        self.assertEqual(
            budgets[0][1]["alertThresholds"][0]["emailAddresses"],
            ["a@example.com"],
        )
        self.assertEqual(groups[0][1]["budgetGroupAmount"], 400)
        self.assertEqual(result["skipped"][0]["account"], "Beta (222222222222)")
        text = output.getvalue()
        self.assertIn("Alert 80 is enabled with no recipients", text)
        self.assertIn("skipped spreadsheet account 999999999999", text)

    def test_limit_stops_after_n_accounts(self):
        harness = FakeHarness()
        generate(_config(), TARGETS, apply=True, limit=1, harness=harness)
        groups = [attempt for attempt in harness.attempts if attempt[0] == "group"]
        self.assertEqual(len(groups[0][1]["childEntities"]), 1)

    def test_budget_create_id_is_kept_when_the_api_returns_a_string(self):
        harness = FakeHarness()

        def create_budget(payload):
            harness.attempts.append(("budget", payload))
            item = {
                "name": payload["name"],
                "uuid": entity_id(
                    {"status": "SUCCESS", "data": f"budget:{payload['name']}"}
                ),
                "budgetAmount": payload.get("budgetAmount") or 0,
            }
            harness.budgets[payload["name"]] = item
            return item

        harness.create_budget = create_budget
        result = generate(_config(), TARGETS, apply=True, harness=harness)
        self.assertEqual(result["errors"], [])
        groups = [attempt for attempt in harness.attempts if attempt[0] == "group"]
        self.assertEqual(
            [child["id"] for child in groups[0][1]["childEntities"]],
            [
                "budget:Alpha Delivery (111111111111)",
                "budget:Beta Delivery (222222222222)",
            ],
        )

    def test_missing_create_id_is_printed(self):
        from contextlib import redirect_stdout
        from io import StringIO

        harness = FakeHarness()

        def create_budget(payload):
            harness.attempts.append(("budget", payload))
            return {"name": payload["name"], "uuid": None, "budgetAmount": 0}

        harness.create_budget = create_budget
        output = StringIO()
        with redirect_stdout(output):
            result = generate(_config(), TARGETS, apply=True, harness=harness)
        text = output.getvalue()
        self.assertEqual(len(result["errors"]), 2)
        self.assertIn("create response did not include an id", text)
        groups = [attempt for attempt in harness.attempts if attempt[0] == "group"]
        self.assertEqual(groups, [])

    def test_dry_run_prints_consolidated_errors_last(self):
        from contextlib import redirect_stdout
        from io import StringIO

        label = "platform account " * 6 + "(123456789012)"
        targets = [
            {
                "name": "platform",
                "rules": [{"viewConditions": [_account([label])]}],
            }
        ]
        output = StringIO()
        with redirect_stdout(output):
            generate(_config(), targets, apply=False, harness=FakeHarness())
        text = output.getvalue()
        self.assertIn("=== Errors (1) ===", text)
        self.assertNotIn('"budgetAmount"', text)
        self.assertTrue(text.rstrip().splitlines()[-1].startswith("  1. budget"))

    def test_rejected_name_is_not_shortened(self):
        label = "platform account " * 6 + "(123456789012)"
        self.assertGreater(len(label), 80)
        targets = [
            {
                "name": "platform",
                "rules": [{"viewConditions": [_account([label])]}],
            }
        ]
        harness = FakeHarness(fail={label})
        result = generate(_config(), targets, apply=True, harness=harness)
        self.assertEqual(result["errors"][0]["name"], label)
        self.assertIn("1..80", result["errors"][0]["error"])
        self.assertEqual(harness.attempts, [])

    def test_existing_resources_fail_before_any_write(self):
        harness = FakeHarness()
        harness.perspectives["Alpha Delivery (111111111111)"] = {
            "name": "Alpha Delivery (111111111111)",
            "uuid": "already-perspective",
        }
        harness.budgets["Beta Delivery (222222222222)"] = {
            "name": "Beta Delivery (222222222222)",
            "uuid": "already-budget",
        }
        config = _config()
        config["behavior"]["on_exists"] = "fail"
        result = generate(config, TARGETS, apply=True, harness=harness)
        messages = [item["error"] for item in result["errors"]]
        self.assertIn(
            "perspective already exists: Alpha Delivery (111111111111)", messages
        )
        self.assertIn(
            "budget already exists: Beta Delivery (222222222222)", messages
        )
        self.assertEqual(harness.attempts, [])

    def test_duplicate_names_block_the_apply(self):
        perspectives = _config(
            perspective={
                "folder": "{bucket}",
                "name": "{bucket}",
                "rule_mode": "account",
            }
        )
        perspective_harness = FakeHarness()
        perspective_result = generate(
            perspectives, TARGETS, apply=True, harness=perspective_harness
        )
        self.assertEqual(perspective_harness.attempts, [])
        self.assertIn(
            "duplicate perspective name in this run",
            [item["error"] for item in perspective_result["errors"]],
        )
        self.assertEqual(perspective_result["plan"].perspectives[0].operation, "create")

        budgets = _config(budget={"name": "{bucket}"})
        budget_harness = FakeHarness()
        budget_result = generate(budgets, TARGETS, apply=True, harness=budget_harness)
        self.assertIn(
            "duplicate budget name in this run",
            [item["error"] for item in budget_result["errors"]],
        )
        self.assertEqual(budget_harness.attempts, [])

    def test_duplicate_account_and_group_child_are_reported(self):
        targets = [
            {
                "name": "hosted",
                "rules": [
                    {
                        "viewConditions": [
                            _account(
                                [
                                    "Alpha (111111111111)",
                                    "Alpha again (111111111111)",
                                ]
                            )
                        ]
                    }
                ],
            }
        ]
        harness = FakeHarness()
        result = generate(_config(), targets, apply=True, harness=harness)
        self.assertIn("duplicate account", result["errors"][0]["error"])
        self.assertEqual(harness.attempts, [])

        plan = ProvisionPlan()
        budget = {
            "period": "MONTHLY",
            "start_time": 1,
            "monthly_breakdown": False,
            "monthly_amounts": [],
            "amount": 1,
        }
        child = BudgetAction(
            key="same",
            name="Alpha",
            perspective_name="Alpha",
            bucket="hosted",
            folder="hosted",
            budget=budget,
            operation="create",
        )
        _plan_group(
            _config(),
            type("Remote", (), {"groups": {}})(),
            "skip",
            "hosted",
            [child, child],
            plan,
        )
        self.assertEqual(
            plan.errors[0].error, "duplicate budget children in budget group"
        )

    def test_manifest_records_created_ids(self):
        harness = FakeHarness()
        with TemporaryDirectory() as directory:
            path = os.path.join(directory, "manifest.json")
            generate(
                _config(),
                TARGETS,
                apply=True,
                manifest_path=path,
                harness=harness,
            )
            manifest = load_manifest(path)
        self.assertTrue(all(item["created"] for item in manifest["perspectives"]))
        self.assertEqual(len(manifest["budgets"]), 2)
        self.assertEqual(len(manifest["budget_groups"]), 1)


class EntityIdTest(unittest.TestCase):
    def test_string_data_is_the_created_id(self):
        self.assertEqual(
            entity_id({"status": "SUCCESS", "data": "I176fw7dR76cFBs_lWJwyQ"}),
            "I176fw7dR76cFBs_lWJwyQ",
        )

    def test_nested_uuid_still_wins(self):
        self.assertEqual(entity_id({"resource": {"uuid": "abc"}}), "abc")
        self.assertEqual(entity_id({"uuid": "top", "data": "nested"}), "top")

    def test_list_data_is_not_an_id(self):
        self.assertIsNone(entity_id({"data": [{"uuid": "abc"}]}))


class TeardownTest(unittest.TestCase):
    def test_reused_ids_are_left_alone(self):
        calls = []
        _delete(
            "budget",
            {"name": "kept", "uuid": "1", "created": False},
            calls.append,
            [],
            True,
        )
        self.assertEqual(calls, [])

    def test_missing_resources_are_already_gone(self):
        errors = []

        def missing(_identifier):
            raise ApiError(404, "missing")

        _delete(
            "budget",
            {"name": "gone", "uuid": "1", "created": True},
            missing,
            errors,
            True,
        )
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
