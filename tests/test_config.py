from datetime import datetime, timezone
import unittest

from provision.config import (
    budget_for,
    load_config,
    load_runs,
    normalize_config,
    proportions,
    render,
    resolve_start,
)
from provision.payloads import budget_group_payload, budget_payload


class ConfigTest(unittest.TestCase):
    def test_default_names_use_folder_and_account_name_fields(self):
        config = normalize_config(
            {
                "cost_category": "Example",
                "budget": {
                    "type": "SPECIFIED_AMOUNT",
                    "period": "MONTHLY",
                    "amount": 10,
                },
            }
        )
        budget = budget_for(
            config,
            "platform",
            "111111111111",
            "Platform Production (111111111111)",
        )

        self.assertEqual(config["perspective"]["rule_mode"], "category_and_account")
        self.assertEqual(config["perspective"]["folder"], "{folder}")
        self.assertEqual(config["perspective"]["name"], "{account_name}")
        self.assertEqual(config["budget"]["name"], "{account_name}")
        self.assertEqual(config["budget_group"]["name"], "{folder}")
        self.assertEqual(budget["_folder"], "platform")
        self.assertEqual(budget["_account_name"], "Platform Production")

    def test_behavior_dry_run_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            normalize_config(
                {
                    "cost_category": "Example",
                    "behavior": {"dry_run": False},
                    "budget": {"type": "PREVIOUS_PERIOD_SPEND"},
                }
            )
        self.assertIn("behavior.dry_run is not supported", str(caught.exception))

    def test_specified_amount_requires_an_amount(self):
        with self.assertRaises(ValueError):
            normalize_config(
                {"cost_category": "Example", "budget": {"type": "SPECIFIED_AMOUNT"}}
            )

    def test_month_start_is_utc_day_one(self):
        start = resolve_start(
            "month_start", datetime(2026, 10, 8, 15, tzinfo=timezone.utc)
        )
        self.assertEqual(
            start,
            int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp() * 1000),
        )

    def test_unknown_template_field(self):
        with self.assertRaises(ValueError):
            render("{missing}", {"bucket": "platform"})

    def test_proportions_sum_to_100(self):
        for count in (1, 3, 20):
            self.assertAlmostEqual(sum(proportions(count)), 100)

    def test_budget_payload_scopes_to_the_perspective(self):
        payload = budget_payload(
            "acct",
            "budget",
            "perspective-id",
            "perspective",
            {
                "type": "PREVIOUS_PERIOD_SPEND",
                "period": "MONTHLY",
                "growth_rate": 0,
                "alerts": [],
                "amount": None,
            },
            1,
        )
        self.assertEqual(payload["scope"]["type"], "PERSPECTIVE")
        self.assertEqual(payload["scope"]["viewId"], "perspective-id")
        self.assertEqual(payload["scope"]["viewName"], "perspective")
        self.assertEqual(payload["scope"]["budgetScopeType"], "PERSPECTIVE")
        self.assertNotIn("entityIds", payload["scope"])
        self.assertNotIn("folderId", payload)
        self.assertNotIn("budgetAmount", payload)
        with_folder = budget_payload(
            "acct",
            "budget",
            "perspective-id",
            "perspective",
            {
                "type": "PREVIOUS_PERIOD_SPEND",
                "period": "MONTHLY",
                "growth_rate": 0,
                "alerts": [],
                "amount": None,
            },
            1,
            "folder-id",
        )
        self.assertEqual(with_folder["folderId"], "folder-id")

    def test_proportional_group_splits_children(self):
        payload = budget_group_payload(
            "acct",
            "group",
            0,
            "MONTHLY",
            1,
            "PROPORTIONAL",
            [{"uuid": "a"}, {"uuid": "b"}],
            [],
        )
        self.assertEqual(
            [child["id"] for child in payload["childEntities"]], ["a", "b"]
        )
        self.assertAlmostEqual(
            sum(child["proportion"] for child in payload["childEntities"]), 100
        )

    def test_year_start_is_utc_january(self):
        start = resolve_start(
            "year_start", datetime(2026, 10, 8, 15, tzinfo=timezone.utc)
        )
        self.assertEqual(
            start,
            int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000),
        )

    def test_annual_monthly_breakdown_splits_the_amount(self):
        config = normalize_config(
            {
                "cost_category": "Example",
                "budget": {
                    "type": "SPECIFIED_AMOUNT",
                    "period": "ANNUAL",
                    "amount": 1200,
                    "monthly_breakdown": True,
                    "start": "year_start",
                },
            }
        )
        budget = budget_for(
            config, "any", now=datetime(2026, 6, 1, tzinfo=timezone.utc)
        )
        self.assertEqual(budget["period"], "YEARLY")
        self.assertEqual(len(budget["monthly_amounts"]), 12)
        self.assertAlmostEqual(sum(budget["monthly_amounts"]), 1200)
        payload = budget_payload(
            "acct", "name", "pid", "pname", budget, budget["start_time"]
        )
        months = payload["budgetMonthlyBreakdown"]["budgetMonthlyAmount"]
        self.assertEqual(payload["budgetMonthlyBreakdown"]["budgetBreakdown"], "MONTHLY")
        self.assertEqual(len(months), 12)
        self.assertEqual(months[0]["time"], budget["start_time"])

    def test_monthly_breakdown_requires_an_annual_period(self):
        with self.assertRaises(ValueError):
            normalize_config(
                {
                    "cost_category": "Example",
                    "budget": {
                        "type": "SPECIFIED_AMOUNT",
                        "period": "MONTHLY",
                        "amount": 100,
                        "monthly_breakdown": True,
                    },
                }
            )

    def test_each_category_keeps_its_own_budget(self):
        runs = load_runs("examples/category-budgets.yaml")
        self.assertEqual(
            [(run["cost_category"], run["budget"]["period"], run["budget"]["amount"]) for run in runs],
            [("AccountBudgets", "MONTHLY", 1500), ("CostCenterByAccount", "YEARLY", 12000)],
        )
        self.assertFalse(runs[0]["budget"]["monthly_breakdown"])
        self.assertTrue(runs[1]["budget"]["monthly_breakdown"])

    def test_sample_configs_load(self):
        sample = load_config("examples/account-budgets.yaml")
        testbed = load_config("examples/testbed.yaml")
        self.assertEqual(sample["buckets"]["include"], ["platform"])
        self.assertNotIn("dry_run", sample["behavior"])
        self.assertEqual(testbed["cost_category"], "AccountBudgets-testbed")
        self.assertIsNone(testbed["buckets"]["include"])
        self.assertEqual(testbed["behavior"]["manifest"], "testbed-manifest.json")
        self.assertEqual(testbed["perspective"]["name"], sample["perspective"]["name"])
        self.assertEqual(testbed["budget"]["name"], sample["budget"]["name"])
        self.assertEqual(
            testbed["budget_group"]["name"], sample["budget_group"]["name"]
        )
        self.assertTrue(testbed["spreadsheet"]["only"])
        self.assertIn("100000000001", testbed["spreadsheet"]["rows"])
        self.assertNotIn("", testbed["spreadsheet"]["rows"])
        first = budget_for(
            testbed,
            "platform",
            "100000000001",
            "100000000001",
        )
        self.assertEqual(first["period"], "YEARLY")
        self.assertEqual(first["start_time"], resolve_start("2026-04-01"))
        self.assertEqual(first["monthly_amounts"][0], 4000)
        self.assertEqual(first["monthly_amounts"][-1], 3900)
        self.assertAlmostEqual(sum(first["monthly_amounts"]), 47700)
        self.assertEqual(
            [alert["percentage"] for alert in first["alerts"]],
            [80, 100, 80, 100],
        )
        self.assertEqual(
            [alert["based_on"] for alert in first["alerts"]],
            ["ACTUAL_COST", "ACTUAL_COST", "FORECASTED_COST", "FORECASTED_COST"],
        )
        self.assertEqual(first["alerts"][0]["emails"], ["finops@example.com"])
        self.assertEqual(first["_sheet_warnings"], [])
        self.assertIsNone(
            budget_for(testbed, "security", "100000000005", "not listed")
        )


if __name__ == "__main__":
    unittest.main()
