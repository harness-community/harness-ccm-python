from copy import deepcopy
from dataclasses import dataclass, field
from re import compile


_ACCOUNT_ID = compile(r"\(([^)]+)\)\s*$")


@dataclass(frozen=True)
class AccountRecord:
    bucket: str
    account_label: str
    account_id: str
    conditions: list


@dataclass
class ExpandResult:
    accounts: list = field(default_factory=list)
    skipped: list = field(default_factory=list)


def parse_account_id(label: str) -> str:
    match = _ACCOUNT_ID.search(label.strip())
    if match:
        return match.group(1)
    return label


def expand_buckets(
    cost_targets: list,
    account_fields: list,
    include: list = None,
    exclude: list = None,
    rule_mode: str = "account_with_sibling_conditions",
    include_shared: bool = False,
) -> ExpandResult:
    if rule_mode not in (
        "account",
        "account_with_sibling_conditions",
        "category_and_account",
    ):
        raise ValueError(f"unknown rule_mode {rule_mode}")

    fields = set(account_fields or [])
    result = ExpandResult()
    for target in cost_targets or []:
        name = target.get("name")
        if not _selected(name, include, exclude):
            continue
        if _is_shared(target) and not include_shared:
            result.skipped.append(
                {"bucket": name, "reason": "shared cost bucket"}
            )
            continue
        records = _accounts_in_target(target, fields, rule_mode)
        if not records:
            result.skipped.append(
                {"bucket": name, "reason": "no account values"}
            )
            continue
        result.accounts.extend(records)
    return result


def _selected(name: str, include: list, exclude: list) -> bool:
    if include is not None and name not in include:
        return False
    if exclude and name in exclude:
        return False
    return True


def _is_shared(target: dict) -> bool:
    return bool(target.get("strategy") or target.get("splits"))


def _accounts_in_target(target: dict, fields: set, rule_mode: str) -> list:
    records = []
    for rule in target.get("rules") or []:
        conditions = rule.get("viewConditions") or []
        for index, condition in enumerate(conditions):
            if not _is_account_condition(condition, fields):
                continue
            for value in condition.get("values") or []:
                if value is None or str(value).strip() == "":
                    continue
                label = str(value)
                records.append(
                    AccountRecord(
                        bucket=target.get("name"),
                        account_label=label,
                        account_id=parse_account_id(label),
                        conditions=_conditions_for(
                            conditions, index, label, rule_mode
                        ),
                    )
                )
    return records


def _is_account_condition(condition: dict, fields: set) -> bool:
    view_field = condition.get("viewField") or {}
    operator = condition.get("viewOperator")
    return view_field.get("fieldId") in fields and operator == "IN"


def category_bucket_condition(category_id: str, category_name: str, bucket: str) -> dict:
    return {
        "type": "VIEW_ID_CONDITION",
        "viewField": {
            "fieldId": category_id,
            "fieldName": category_name,
            "identifier": "BUSINESS_MAPPING",
            "identifierName": "Cost Categories",
        },
        "viewOperator": "IN",
        "values": [bucket],
    }


def _conditions_for(
    conditions: list, index: int, label: str, rule_mode: str
) -> list:
    account_condition = deepcopy(conditions[index])
    account_condition["values"] = [label]
    if rule_mode in ("account", "category_and_account"):
        return [account_condition]
    siblings = [
        deepcopy(condition)
        for position, condition in enumerate(conditions)
        if position != index
    ]
    return [account_condition, *siblings]
