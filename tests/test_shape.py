import unittest

from provision.accounts import parse_account_id
from provision.config import load_yaml
from provision.shape import synthetic_buckets


class ShapeTest(unittest.TestCase):
    def test_product_by_account_shape(self):
        shape = load_yaml("examples/testbed-shape.yaml")
        self.assertEqual(shape["category"], "AccountBudgets-testbed")
        self.assertEqual(len(shape["buckets"]), 3)
        self.assertEqual(sum(bucket["accounts"] for bucket in shape["buckets"]), 5)
        self.assertEqual(
            next(
                bucket["accounts"]
                for bucket in shape["buckets"]
                if bucket["name"] == "platform"
            ),
            2,
        )

        built = synthetic_buckets(shape["buckets"])
        labels = [label for bucket in built for label in bucket["labels"]]
        identifiers = [parse_account_id(label) for label in labels]
        self.assertEqual(len(labels), 5)
        self.assertEqual(len(set(identifiers)), 5)
        self.assertTrue(all(len(identifier) == 12 for identifier in identifiers))
        self.assertEqual(labels[0], "platform account 01 (100000000001)")


if __name__ == "__main__":
    unittest.main()
