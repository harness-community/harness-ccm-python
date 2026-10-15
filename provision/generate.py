from costcategories import CostCategory
from provision.execute import execute_plan
from provision.live import LiveHarness
from provision.manifest import load_manifest, save_manifest
from provision.models import PlanIssue, public_issues
from provision.plan import build_plan, snapshot_from_harness


def load_targets(category_name: str) -> dict:
    category = CostCategory(category_name)
    if not category.uuid:
        raise SystemExit(f"cost category not found: {category_name}")
    body = category.get()
    resource = body.get("resource") or body
    return {
        "name": category.name,
        "uuid": category.uuid,
        "targets": resource.get("costTargets") or [],
    }


def generate(
    config: dict,
    targets: list,
    apply: bool = False,
    limit: int = None,
    manifest_path: str = None,
    harness=None,
    category: dict = None,
) -> dict:
    dry_run = not apply
    if harness is None:
        harness = LiveHarness()
    if limit is None:
        limit = config["behavior"].get("limit")
    if limit is not None and (
        not isinstance(limit, int) or isinstance(limit, bool) or limit < 1
    ):
        raise ValueError("limit must be a positive integer")

    remote = snapshot_from_harness(harness)
    plan = build_plan(
        config,
        targets,
        remote,
        limit=limit,
        category=category,
    )

    for warning in plan.warnings:
        print(warning)

    manifest = load_manifest(manifest_path) if not dry_run else None
    stats = {
        "folders": 0,
        "perspectives": 0,
        "budgets": 0,
        "groups": 0,
        "updated_perspectives": 0,
        "updated_budgets": 0,
        "updated_groups": 0,
    }
    errors = list(plan.errors)

    try:
        if plan.errors and not dry_run:
            for item in plan.errors:
                issue = item if isinstance(item, PlanIssue) else PlanIssue(**item)
                print(
                    f"error {issue.kind.replace('_', ' ')} {issue.name}: {issue.error}"
                )
        else:
            errors = execute_plan(
                config, plan, harness, dry_run, manifest, stats
            )
    finally:
        errors = public_issues(errors)
        if manifest is not None and manifest_path:
            manifest["errors"] = errors
            manifest["skipped"] = plan.skipped
            save_manifest(manifest_path, manifest)

    for skipped in plan.skipped:
        account = skipped.get("account")
        if account:
            print(
                f"skipped account {account} in {skipped['bucket']}: {skipped['reason']}"
            )
        else:
            print(f"skipped bucket {skipped['bucket']}: {skipped['reason']}")

    action = "would create" if dry_run else "created"
    print(
        "{action} folders {folders} perspectives {perspectives} "
        "budgets {budgets} budget groups {groups}".format(action=action, **stats)
    )
    update_action = "would update" if dry_run else "updated"
    print(
        "{action} perspectives {updated_perspectives} "
        "budgets {updated_budgets} budget groups {updated_groups}".format(
            action=update_action, **stats
        )
    )
    print(
        "accounts {accounts} dry_run {dry_run} errors {errors}".format(
            accounts=plan.account_count,
            dry_run=dry_run,
            errors=len(errors),
        )
    )
    return {
        "dry_run": dry_run,
        "accounts": plan.account_count,
        "errors": errors,
        "skipped": plan.skipped,
        "plan": plan,
    }
