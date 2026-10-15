from argparse import ArgumentParser
from sys import exit

from costcategories import Bucket, CostCategory, ViewCondition, ViewOperator
from harness import ApiError
from provision.config import load_yaml
from provision.manifest import load_manifest, save_manifest
from provision.shape import synthetic_buckets


def seed(shape_path: str, manifest_path: str) -> None:
    shape = load_yaml(shape_path)
    category_name = shape.get("category")
    if not category_name:
        raise SystemExit("shape file is missing category")
    if not shape.get("buckets"):
        raise SystemExit("shape file is missing buckets")

    built = synthetic_buckets(shape["buckets"])
    category = CostCategory(category_name)
    category.buckets = [_bucket(entry) for entry in built]
    category.shared_buckets = []
    try:
        category.update()
    except ApiError as exc:
        raise SystemExit(f"failed to seed cost category: {exc}") from exc
    if not category.uuid:
        category = CostCategory(category_name)
    if not category.uuid:
        raise SystemExit("cost category id was not returned")

    manifest = load_manifest(manifest_path)
    manifest["cost_category"] = {
        "name": category_name,
        "uuid": category.uuid,
        "seeded": True,
    }
    save_manifest(manifest_path, manifest)
    accounts = sum(len(entry["labels"]) for entry in built)
    print(
        f"seeded {category_name} ({category.uuid}): "
        f"{len(built)} buckets, {accounts} accounts"
    )


def _bucket(entry: dict) -> Bucket:
    bucket = Bucket(entry["name"])
    bucket.add_rule(
        {
            "viewConditions": [
                ViewCondition(
                    "awsUsageaccountid",
                    "Account",
                    "AWS",
                    "AWS",
                    ViewOperator.IN,
                    entry["labels"],
                ).format()
            ]
        }
    )
    return bucket


def main(argv=None) -> int:
    parser = ArgumentParser(
        description=(
            "Create a synthetic cost category in the account "
            "named by HARNESS_ACCOUNT_ID."
        )
    )
    parser.add_argument(
        "--shape",
        default="examples/testbed-shape.yaml",
        help="bucket names and account counts",
    )
    parser.add_argument(
        "--manifest",
        default="testbed-manifest.json",
        help="file that records the seeded cost category id",
    )
    args = parser.parse_args(argv)
    try:
        seed(args.shape, args.manifest)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    exit(main())
