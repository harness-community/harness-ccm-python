import unittest

from provision.accounts import expand_buckets, parse_account_id


def _account_condition(values, field_id="awsUsageaccountid"):
    return {
        "type": "VIEW_ID_CONDITION",
        "viewField": {
            "fieldId": field_id,
            "fieldName": "Account",
            "identifier": "AWS",
            "identifierName": "AWS",
        },
        "viewOperator": "IN",
        "values": values,
    }


def _tag_condition():
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


FIELDS = ["awsUsageaccountid", "azureSubscriptionGuid", "gcpProjectId"]


class ExpandBucketsTest(unittest.TestCase):
    def test_splits_each_account_in_a_bucket(self):
        targets = [
            {
                "name": "platform",
                "rules": [
                    {
                        "viewConditions": [
                            _account_condition(
                                [
                                    "platform account 01 (100000000001)",
                                    "platform account 02 (100000000002)",
                                ]
                            )
                        ]
                    }
                ],
            }
        ]

        result = expand_buckets(targets, FIELDS)

        self.assertEqual(len(result.accounts), 2)
        self.assertEqual(result.skipped, [])
        self.assertEqual(result.accounts[0].bucket, "platform")
        self.assertEqual(result.accounts[0].account_id, "100000000001")
        self.assertEqual(result.accounts[0].conditions[0]["values"], [
            "platform account 01 (100000000001)"
        ])
        self.assertEqual(
            targets[0]["rules"][0]["viewConditions"][0]["values"][0],
            "platform account 01 (100000000001)",
        )

    def test_keeps_sibling_and_conditions(self):
        targets = [
            {
                "name": "platform",
                "rules": [
                    {
                        "viewConditions": [
                            _account_condition(
                                ["alpha (111111111111)", "beta (222222222222)"]
                            ),
                            _tag_condition(),
                        ]
                    }
                ],
            }
        ]

        result = expand_buckets(
            targets, FIELDS, rule_mode="account_with_sibling_conditions"
        )

        self.assertEqual(len(result.accounts), 2)
        self.assertEqual(len(result.accounts[0].conditions), 2)
        self.assertEqual(result.accounts[0].conditions[1]["values"], ["prod"])
        self.assertEqual(result.accounts[1].conditions[0]["values"], ["beta (222222222222)"])

    def test_category_and_account_keeps_only_the_account_condition(self):
        targets = [
            {
                "name": "platform",
                "rules": [
                    {
                        "viewConditions": [
                            _account_condition(["alpha (111111111111)"]),
                            _tag_condition(),
                        ]
                    }
                ],
            }
        ]

        result = expand_buckets(
            targets, FIELDS, rule_mode="category_and_account"
        )

        self.assertEqual(len(result.accounts[0].conditions), 1)
        self.assertEqual(
            result.accounts[0].conditions[0]["values"], ["alpha (111111111111)"]
        )

    def test_account_mode_drops_siblings(self):
        targets = [
            {
                "name": "platform",
                "rules": [
                    {
                        "viewConditions": [
                            _account_condition(["alpha (111111111111)"]),
                            _tag_condition(),
                        ]
                    }
                ],
            }
        ]

        result = expand_buckets(targets, FIELDS, rule_mode="account")

        self.assertEqual(len(result.accounts[0].conditions), 1)
        self.assertEqual(
            result.accounts[0].conditions[0]["viewField"]["fieldId"],
            "awsUsageaccountid",
        )

    def test_include_and_exclude(self):
        targets = [
            {"name": "keep", "rules": [{"viewConditions": [_account_condition(["a (1)"])]}]},
            {"name": "drop", "rules": [{"viewConditions": [_account_condition(["b (2)"])]}]},
            {"name": "also", "rules": [{"viewConditions": [_account_condition(["c (3)"])]}]},
        ]

        result = expand_buckets(
            targets, FIELDS, include=["keep", "drop"], exclude=["drop"]
        )

        self.assertEqual([item.bucket for item in result.accounts], ["keep"])

    def test_skips_buckets_without_account_values(self):
        targets = [
            {
                "name": "labels-only",
                "rules": [{"viewConditions": [_tag_condition()]}],
            }
        ]

        result = expand_buckets(targets, FIELDS)

        self.assertEqual(result.accounts, [])
        self.assertEqual(result.skipped[0]["reason"], "no account values")

    def test_skips_shared_buckets_unless_requested(self):
        targets = [
            {
                "name": "shared-services",
                "strategy": "EQUAL",
                "splits": [],
                "rules": [{"viewConditions": [_account_condition(["a (1)"])]}],
            }
        ]

        skipped = expand_buckets(targets, FIELDS)
        included = expand_buckets(targets, FIELDS, include_shared=True)

        self.assertEqual(skipped.skipped[0]["reason"], "shared cost bucket")
        self.assertEqual(len(included.accounts), 1)

    def test_does_not_expand_not_in_operator(self):
        condition = _account_condition(["a (1)"])
        condition["viewOperator"] = "NOT_IN"
        result = expand_buckets(
            [{"name": "excluded", "rules": [{"viewConditions": [condition]}]}],
            FIELDS,
        )

        self.assertEqual(result.accounts, [])
        self.assertEqual(result.skipped[0]["reason"], "no account values")

    def test_parse_account_id_falls_back_to_the_label(self):
        self.assertEqual(parse_account_id("plain-project"), "plain-project")


if __name__ == "__main__":
    unittest.main()
