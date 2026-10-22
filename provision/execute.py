from json import dumps

from harness import ApiError
from perspectives.perspective import perspective_payload
from provision.manifest import remember
from provision.models import ExecutionResult, PlanIssue
from provision.payloads import budget_group_payload, budget_payload
from provision.plan import fiscal_year_name

VERBOSE = False


def set_verbose(value: bool) -> None:
    global VERBOSE
    VERBOSE = bool(value)


def _detail(text: str) -> None:
    """Per-item dry-run chatter and payloads; only shown with --verbose."""
    if VERBOSE:
        print(text)


def execute_plan(
    config: dict,
    plan,
    harness,
    dry_run: bool,
    manifest,
    stats: dict,
) -> list:
    errors = list(plan.errors)
    # Plan errors are reported once, in the consolidated section at the end.
    if plan.errors and not dry_run:
        return errors

    folder_ids = {}
    perspective_ids = {}
    budget_results = {}

    for action in plan.folders:
        folder = _ensure_folder(action, harness, dry_run, manifest, errors, stats)
        if folder is not None:
            folder_ids[action.name] = folder

    for action in plan.perspectives:
        folder = folder_ids.get(action.folder_name) or {"uuid": None}
        perspective = _ensure_perspective(
            action, folder.get("uuid"), harness, dry_run, manifest, errors, stats
        )
        if perspective is not None:
            perspective_ids[action.name] = perspective

    for action in plan.budgets:
        perspective = perspective_ids.get(action.perspective_name)
        if perspective is None:
            continue
        folder = folder_ids.get(
            next(
                (
                    item.folder_name
                    for item in plan.perspectives
                    if item.name == action.perspective_name
                ),
                None,
            )
        )
        folder_id = (folder or {}).get("uuid")
        result = _ensure_budget(
            action, perspective, folder_id, harness, dry_run, manifest, errors, stats
        )
        if result is not None:
            budget_results[action.key] = result

    budgets_by_key = {item.key: item for item in plan.budgets}
    for action in plan.groups:
        if dry_run:
            children = [
                {
                    "uuid": "<dry-run>",
                    "name": budgets_by_key[key].name,
                    "amount": float(budgets_by_key[key].budget.get("amount") or 0),
                    "monthly_amounts": list(
                        budgets_by_key[key].budget.get("monthly_amounts") or []
                    ),
                }
                for key in action.budget_keys
                if key in budgets_by_key
            ]
        else:
            children = [
                budget_results[key].as_dict()
                for key in action.budget_keys
                if key in budget_results and budget_results[key].uuid
            ]
            if not children:
                continue
        _ensure_group(
            config, action, children, harness, dry_run, manifest, errors, stats
        )

    return errors


def _issue_text(item) -> str:
    if isinstance(item, PlanIssue):
        kind, name, error = item.kind, item.name, item.error
    else:
        kind, name, error = item["kind"], item["name"], item["error"]
    return f"error {kind.replace('_', ' ')} {name}: {error}"


def _record_error(errors, kind, name, message):
    issue = PlanIssue(kind, name, message)
    errors.append(issue)
    print(_issue_text(issue))


def _budget_result(action, uuid, amount, created) -> ExecutionResult:
    return ExecutionResult(
        kind="budget",
        name=action.name,
        uuid=uuid,
        created=created,
        amount=amount,
        bucket=action.bucket,
        period=action.budget["period"],
        start_time=action.budget["start_time"],
        monthly_breakdown=bool(action.budget.get("monthly_breakdown")),
        monthly_amounts=list(action.budget.get("monthly_amounts") or []),
        folder=action.folder,
    )


def _ensure_folder(action, harness, dry_run, manifest, errors, stats):
    if action.operation == "reuse":
        return {"name": action.name, "uuid": action.existing_uuid}
    if dry_run:
        _detail(f"would create folder {action.name}")
        stats["folders"] += 1
        return {"name": action.name, "uuid": None}
    try:
        created = harness.create_folder(action.name)
    except ApiError as exc:
        _record_error(errors, "folder", action.name, str(exc))
        return None
    if not created.get("uuid"):
        _record_error(
            errors, "folder", action.name, "create response did not include an id"
        )
        return None
    stats["folders"] += 1
    if manifest is not None:
        remember(
            manifest["folders"],
            {"name": action.name, "uuid": created["uuid"], "created": True},
        )
    print(f"created folder {action.name}")
    return created


def _ensure_perspective(action, folder_id, harness, dry_run, manifest, errors, stats):
    if action.operation == "skip":
        _detail(f"skip perspective {action.name}")
        return {
            "name": action.name,
            "uuid": action.existing_uuid,
            "created": False,
        }
    if action.operation == "update":
        kept_folder = action.existing_folder_id or folder_id
        update_payload = perspective_payload(action.name, kept_folder, action.conditions)
        update_payload["uuid"] = action.existing_uuid
        if dry_run:
            _detail(f"would update perspective {action.name}")
            stats["updated_perspectives"] += 1
            _detail(dumps(update_payload, indent=2))
            return {
                "name": action.name,
                "uuid": action.existing_uuid,
                "created": False,
            }
        try:
            updated = harness.update_perspective(action.existing_uuid, update_payload)
        except ApiError as exc:
            _record_error(errors, "perspective", action.name, str(exc))
            return None
        stats["updated_perspectives"] += 1
        print(f"updated perspective {action.name}")
        return updated

    payload = perspective_payload(action.name, folder_id, action.conditions)
    if dry_run:
        _detail(f"would create perspective {action.name}")
        stats["perspectives"] += 1
        _detail(dumps(payload, indent=2))
        return {"name": action.name, "uuid": "<dry-run>", "created": False}
    try:
        created = harness.create_perspective(payload)
    except ApiError as exc:
        _record_error(errors, "perspective", action.name, str(exc))
        return None
    if not created.get("uuid"):
        _record_error(
            errors, "perspective", action.name, "create response did not include an id"
        )
        return None
    if manifest is not None:
        remember(
            manifest["perspectives"],
            {
                "name": action.name,
                "uuid": created["uuid"],
                "bucket": action.bucket,
                "created": True,
            },
        )
    stats["perspectives"] += 1
    print(f"created perspective {action.name}")
    return created


def _ensure_budget(action, perspective, folder_id, harness, dry_run, manifest, errors, stats):
    payload = budget_payload(
        harness.account_id,
        action.name,
        perspective.get("uuid"),
        perspective["name"],
        action.budget,
        action.budget["start_time"],
        folder_id,
    )
    if action.operation == "skip":
        _detail(f"skip budget {action.name}")
        return _budget_result(action, action.existing_uuid, action.existing_amount, False)
    if action.operation == "update":
        if dry_run:
            _detail(f"would update budget {action.name}")
            _detail(dumps(payload, indent=2))
            stats["updated_budgets"] += 1
            return _budget_result(
                action,
                action.existing_uuid,
                float(payload.get("budgetAmount") or 0),
                False,
            )
        try:
            updated = harness.update_budget(action.existing_uuid, payload)
        except ApiError as exc:
            _record_error(errors, "budget", action.name, str(exc))
            return None
        stats["updated_budgets"] += 1
        print(f"updated budget {action.name}")
        return _budget_result(
            action,
            updated["uuid"],
            float(payload.get("budgetAmount") or 0),
            False,
        )

    if dry_run:
        _detail(f"would create budget {action.name}")
        stats["budgets"] += 1
        _detail(dumps(payload, indent=2))
        return _budget_result(
            action,
            "<dry-run>",
            float(payload.get("budgetAmount") or 0),
            False,
        )
    try:
        created = harness.create_budget(payload)
    except ApiError as exc:
        _record_error(errors, "budget", action.name, str(exc))
        return None
    if not created.get("uuid"):
        _record_error(
            errors, "budget", action.name, "create response did not include an id"
        )
        return None
    if manifest is not None:
        remember(
            manifest["budgets"],
            {
                "name": action.name,
                "uuid": created["uuid"],
                "bucket": action.bucket,
                "created": True,
            },
        )
    stats["budgets"] += 1
    print(f"created budget {action.name}")
    return _budget_result(
        action,
        created["uuid"],
        float(created.get("budgetAmount") or action.budget.get("amount") or 0),
        True,
    )


def _ensure_group(config, action, children, harness, dry_run, manifest, errors, stats):
    payload = budget_group_payload(
        harness.account_id,
        action.name,
        action.amount,
        action.period,
        action.start_time,
        config["budget_group"]["cascade"],
        children,
        config["budget_group"].get("alerts"),
        monthly_breakdown=action.monthly_breakdown,
        monthly_amounts=action.monthly_amounts,
    )
    # Keep fiscal naming stable if the planner already resolved it.
    if action.period == "YEARLY":
        payload["name"] = fiscal_year_name(action.name, action.start_time)

    if action.operation == "skip":
        _detail(f"skip budget group {action.name}")
        return
    if action.operation == "update":
        if dry_run:
            _detail(f"would update budget group {action.name}")
            _detail(dumps(payload, indent=2))
            stats["updated_groups"] += 1
            return
        try:
            harness.update_budget_group(action.existing_uuid, payload)
        except ApiError as exc:
            _record_error(errors, "budget_group", action.name, str(exc))
            return
        stats["updated_groups"] += 1
        print(f"updated budget group {action.name}")
        return

    if dry_run:
        _detail(f"would create budget group {action.name}")
        stats["groups"] += 1
        _detail(dumps(payload, indent=2))
        return
    try:
        created = harness.create_budget_group(payload)
    except ApiError as exc:
        _record_error(errors, "budget_group", action.name, str(exc))
        return
    if not created.get("uuid"):
        _record_error(
            errors, "budget_group", action.name, "create response did not include an id"
        )
        return
    if manifest is not None:
        remember(
            manifest["budget_groups"],
            {
                "name": action.name,
                "uuid": created["uuid"],
                "bucket": action.bucket,
                "created": True,
            },
        )
    stats["groups"] += 1
    print(f"created budget group {action.name}")
