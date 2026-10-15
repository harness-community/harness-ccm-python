from argparse import ArgumentParser
from sys import exit

from budgets.budget import delete_budget
from budgets.group import delete_budget_group, delete_cost_category
from harness import ApiError
from perspectives.perspective import delete_folder, delete_perspective
from provision.manifest import load_manifest


def teardown(manifest_path: str) -> int:
    manifest = load_manifest(manifest_path)
    errors = []
    for item in manifest.get("budget_groups") or []:
        _delete("budget group", item, delete_budget_group, errors, created_only=True)
    for item in manifest.get("budgets") or []:
        _delete("budget", item, delete_budget, errors, created_only=True)
    for item in manifest.get("perspectives") or []:
        _delete("perspective", item, delete_perspective, errors, created_only=True)
    for item in manifest.get("folders") or []:
        _delete("folder", item, delete_folder, errors, created_only=True)
    category = manifest.get("cost_category") or {}
    if category.get("seeded"):
        _delete(
            "cost category",
            category,
            delete_cost_category,
            errors,
            created_only=False,
        )
    return 1 if errors else 0


def _delete(kind: str, item: dict, delete, errors: list, created_only: bool) -> None:
    if not item or not item.get("uuid"):
        return
    if created_only and not item.get("created"):
        return
    try:
        delete(item["uuid"])
    except ApiError as exc:
        if exc.status == 404:
            print(f"already gone {kind} {item.get('name')}")
            return
        errors.append({"kind": kind, "name": item.get("name"), "error": str(exc)})
        print(f"error deleting {kind} {item.get('name')}: {exc}")
        return
    print(f"deleted {kind} {item.get('name')} ({item['uuid']})")


def main(argv=None) -> int:
    parser = ArgumentParser(
        description="Delete only the ids recorded in a test-bed manifest."
    )
    parser.add_argument(
        "--manifest",
        default="testbed-manifest.json",
        help="manifest written by seed_testbed.py and generate_from_buckets.py",
    )
    args = parser.parse_args(argv)
    return teardown(args.manifest)


if __name__ == "__main__":
    exit(main())
