from collections import defaultdict
from datetime import datetime, timezone

from provision.accounts import category_bucket_condition, expand_buckets
from provision.config import budget_for, name_warning, render
from provision.models import (
    BudgetAction,
    FolderAction,
    GroupAction,
    PerspectiveAction,
    PlanIssue,
    ProvisionPlan,
)
from provision.sheet import unused_rows


class RemoteState:
    """Name-indexed snapshot used only for planning decisions."""

    def __init__(self, folders=None, perspectives=None, budgets=None, groups=None):
        self.folders = folders or {}
        self.perspectives = perspectives or {}
        self.budgets = budgets or {}
        self.groups = groups or {}


def snapshot_from_harness(harness) -> RemoteState:
    return RemoteState(
        folders=_index(harness, "find_folder", getattr(harness, "folders", None)),
        perspectives=_index(
            harness, "find_perspective", getattr(harness, "perspectives", None)
        ),
        budgets=_index(harness, "find_budget", getattr(harness, "budgets", None)),
        groups=_index(
            harness, "find_budget_group", getattr(harness, "groups", None)
        ),
    )


def _index(harness, finder_name, direct):
    if isinstance(direct, dict):
        return dict(direct)
    # LiveHarness caches on first find; probe with an impossible name to load.
    getattr(harness, finder_name)("__provision_plan_probe__")
    cache_name = {
        "find_folder": "_folders",
        "find_perspective": "_perspectives",
        "find_budget": "_budgets",
        "find_budget_group": "_groups",
    }[finder_name]
    cached = getattr(harness, cache_name, None)
    return dict(cached or {})


def build_plan(
    config: dict,
    targets: list,
    remote: RemoteState,
    limit: int = None,
    category: dict = None,
) -> ProvisionPlan:
    rule_mode = config["perspective"]["rule_mode"]
    if rule_mode == "category_and_account" and not (
        category and category.get("uuid") and category.get("name")
    ):
        raise ValueError(
            "cost category id is required for category_and_account perspectives"
        )

    expanded = expand_buckets(
        targets,
        config["account_fields"],
        include=config["buckets"].get("include"),
        exclude=config["buckets"].get("exclude"),
        rule_mode=rule_mode,
        include_shared=config["behavior"]["include_shared"],
    )
    accounts = list(expanded.accounts)
    if limit is not None:
        accounts = accounts[:limit]

    plan = ProvisionPlan(skipped=list(expanded.skipped), account_count=len(accounts))
    for message in unused_rows(config.get("spreadsheet"), expanded.accounts):
        plan.warnings.append(message)

    on_exists = config["behavior"]["on_exists"]
    folder_actions = {}
    perspective_names = {}
    budget_names = {}
    account_keys = set()
    bucket_budgets = defaultdict(list)

    for record in accounts:
        account_key = (record.bucket, record.account_id)
        if account_key in account_keys:
            _issue(
                plan,
                "account",
                record.account_label,
                f"duplicate account {record.account_id} in bucket {record.bucket}",
            )
            continue
        account_keys.add(account_key)

        values = {
            "category": config["cost_category"],
            "bucket": record.bucket,
            "account_label": record.account_label,
            "account_id": record.account_id,
        }
        budget = budget_for(
            config, record.bucket, record.account_id, record.account_label
        )
        if budget is None:
            plan.skipped.append(
                {
                    "bucket": record.bucket,
                    "account": record.account_label,
                    "reason": "no budget configured for this account",
                }
            )
            continue

        values["account_name"] = budget.get("_account_name")
        values["folder"] = budget.get("_folder")
        for warning in budget.pop("_sheet_warnings", []):
            plan.warnings.append(f"warning: {warning}")

        folder_name = render(config["perspective"]["folder"], values)
        perspective_name = render(config["perspective"]["name"], values)
        budget_name = render(
            budget["name"],
            {**values, "perspective_name": perspective_name},
        )
        if budget["period"] == "YEARLY":
            budget_name = fiscal_year_name(budget_name, budget["start_time"])

        warning = name_warning("budget", budget_name)
        if warning:
            _issue(plan, "budget", budget_name, warning)

        if folder_name not in folder_actions:
            existing_folder = remote.folders.get(folder_name)
            folder_actions[folder_name] = FolderAction(
                name=folder_name,
                operation="reuse" if existing_folder else "create",
                existing_uuid=(existing_folder or {}).get("uuid"),
            )

        conditions = list(record.conditions)
        if rule_mode == "category_and_account":
            conditions = [
                category_bucket_condition(
                    category["uuid"], category["name"], record.bucket
                ),
                *conditions,
            ]

        existing_perspective = remote.perspectives.get(perspective_name)
        if perspective_name in perspective_names:
            _issue(
                plan,
                "perspective",
                perspective_name,
                "duplicate perspective name in this run",
            )
            continue
        if existing_perspective and on_exists == "fail":
            _issue(
                plan,
                "perspective",
                perspective_name,
                f"perspective already exists: {perspective_name}",
            )
            perspective_op = "skip"
        elif existing_perspective and on_exists == "update":
            perspective_op = "update"
        elif existing_perspective:
            perspective_op = "skip"
        else:
            perspective_op = "create"
        perspective_names[perspective_name] = record.bucket
        plan.perspectives.append(
            PerspectiveAction(
                name=perspective_name,
                folder_name=folder_name,
                bucket=record.bucket,
                conditions=conditions,
                operation=perspective_op,
                existing_uuid=(existing_perspective or {}).get("uuid"),
                existing_folder_id=(existing_perspective or {}).get("folderId"),
            )
        )

        budget_key = f"{record.bucket}:{record.account_id}:{budget_name}"
        existing_budget = remote.budgets.get(budget_name)
        resolved_name = budget_name
        if on_exists == "update" and existing_budget and start_changed(
            existing_budget, budget["start_time"]
        ):
            resolved_name = fiscal_year_name(budget_name, budget["start_time"])
            existing_budget = remote.budgets.get(resolved_name)
        elif on_exists == "update" and not existing_budget:
            fiscal_name = fiscal_year_name(budget_name, budget["start_time"])
            fiscal_existing = remote.budgets.get(fiscal_name)
            if fiscal_existing:
                resolved_name = fiscal_name
                existing_budget = fiscal_existing

        if resolved_name in budget_names:
            _issue(plan, "budget", resolved_name, "duplicate budget name in this run")
            continue
        if existing_budget and on_exists == "fail":
            _issue(
                plan,
                "budget",
                resolved_name,
                f"budget already exists: {resolved_name}",
            )
            budget_op = "skip"
        elif existing_budget and on_exists == "update":
            budget_op = "update"
        elif existing_budget:
            budget_op = "skip"
        else:
            budget_op = "create"
        budget_names[resolved_name] = budget_key
        action = BudgetAction(
            key=budget_key,
            name=resolved_name,
            perspective_name=perspective_name,
            bucket=record.bucket,
            folder=budget.get("_folder") or record.bucket,
            budget=budget,
            operation=budget_op,
            existing_uuid=(existing_budget or {}).get("uuid"),
            existing_amount=float((existing_budget or {}).get("budgetAmount") or 0),
        )
        plan.budgets.append(action)
        bucket_budgets[record.bucket].append(action)

    plan.folders = list(folder_actions.values())

    if config["budget_group"]["enabled"]:
        for bucket, children in bucket_budgets.items():
            _plan_group(config, remote, on_exists, bucket, children, plan)

    return plan


def _plan_group(config, remote, on_exists, bucket, children, plan):
    if not children:
        return
    periods = {child.budget["period"] for child in children}
    starts = {child.budget["start_time"] for child in children}
    breakdowns = {bool(child.budget.get("monthly_breakdown")) for child in children}
    folders = {child.folder for child in children}
    if len(periods) != 1 or len(starts) != 1 or len(breakdowns) != 1:
        _issue(
            plan,
            "budget_group",
            bucket,
            "account budgets in a bucket must share period, start, and monthly breakdown",
        )
        return
    if len(folders) != 1:
        by_folder = defaultdict(list)
        for child in children:
            by_folder[child.folder].append(child.name)
        detail = "; ".join(
            f"{folder!r}: {len(names)} budget(s), e.g. {names[0]}"
            for folder, names in sorted(by_folder.items())
        )
        _issue(
            plan,
            "budget_group",
            bucket,
            "account budgets in a cost bucket must use the same folder "
            f"(found {len(by_folder)}: {detail}). Make the spreadsheet folder "
            "column identical for every row in this bucket, or map "
            "spreadsheet.columns.folder to the bucket column",
        )
        return

    keys = [child.key for child in children]
    if len(keys) != len(set(keys)):
        _issue(plan, "budget_group", bucket, "duplicate budget children in budget group")
        return

    first = children[0]
    values = {
        "category": config["cost_category"],
        "bucket": bucket,
        "folder": first.folder,
    }
    name = render(config["budget_group"]["name"], values)
    if first.budget["period"] == "YEARLY":
        name = fiscal_year_name(name, first.budget["start_time"])
    warning = name_warning("budget group", name)
    if warning:
        _issue(plan, "budget_group", name, warning)

    existing = remote.groups.get(name)
    if on_exists == "update" and existing and start_changed(
        existing, first.budget["start_time"]
    ):
        name = fiscal_year_name(name, first.budget["start_time"])
        existing = remote.groups.get(name)
    elif on_exists == "update" and not existing:
        fiscal_name = fiscal_year_name(name, first.budget["start_time"])
        fiscal_existing = remote.groups.get(fiscal_name)
        if fiscal_existing:
            name = fiscal_name
            existing = fiscal_existing

    if existing and on_exists == "fail":
        _issue(plan, "budget_group", name, f"budget group already exists: {name}")
        operation = "skip"
    elif existing and on_exists == "update":
        operation = "update"
    elif existing:
        operation = "skip"
    else:
        operation = "create"

    monthly_amounts = sum_months(children) if first.budget.get("monthly_breakdown") else []
    amount = sum(float(child.budget.get("amount") or 0) for child in children)
    plan.groups.append(
        GroupAction(
            name=name,
            bucket=bucket,
            folder=first.folder,
            budget_keys=keys,
            period=first.budget["period"],
            start_time=first.budget["start_time"],
            monthly_breakdown=bool(first.budget.get("monthly_breakdown")),
            monthly_amounts=monthly_amounts,
            amount=amount,
            operation=operation,
            existing_uuid=(existing or {}).get("uuid"),
        )
    )


def _issue(plan: ProvisionPlan, kind: str, name: str, error: str) -> None:
    plan.errors.append(PlanIssue(kind, name, error))


def fiscal_year_name(name: str, start_time: int) -> str:
    start = datetime.fromtimestamp(start_time / 1000, tz=timezone.utc)
    ending_year = start.year if start.month == 1 else start.year + 1
    suffix = f" - FY{ending_year % 100:02d}"
    return name if name.endswith(suffix) else f"{name}{suffix}"


def start_changed(existing: dict, desired: int) -> bool:
    current = existing.get("startTime")
    return current is not None and int(current) != int(desired)


def sum_months(children: list) -> list:
    totals = []
    for child in children:
        amounts = child.budget.get("monthly_amounts") or []
        if not totals:
            totals = [0] * len(amounts)
        for index, amount in enumerate(amounts):
            totals[index] += float(amount)
    return totals

