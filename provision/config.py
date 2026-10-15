from datetime import date, datetime, timezone

import yaml

from provision.sheet import attach_spreadsheet, normalize_spreadsheet


PERIODS = {"DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "YEARLY"}
PERIOD_ALIASES = {
    "MONTHLY": "MONTHLY",
    "ANNUAL": "YEARLY",
    "ANNUALLY": "YEARLY",
    "YEARLY": "YEARLY",
}
BUDGET_TYPES = {"SPECIFIED_AMOUNT", "PREVIOUS_MONTH_SPEND", "PREVIOUS_PERIOD_SPEND"}
CASCADES = {"EQUAL", "PROPORTIONAL", "NO_CASCADE"}
RULE_MODES = {"account", "account_with_sibling_conditions", "category_and_account"}
ON_EXISTS = {"skip", "fail", "update"}
BUDGET_NAME_MAX = 80

DEFAULTS = {
    "account_fields": [
        "awsUsageaccountid",
        "azureSubscriptionGuid",
        "gcpProjectId",
    ],
    "buckets": {"include": None, "exclude": []},
    "perspective": {
        "folder": "{folder}",
        "name": "{account_name}",
        "rule_mode": "category_and_account",
    },
    "budget": {
        "name": "{account_name}",
        "type": "PREVIOUS_PERIOD_SPEND",
        "period": "MONTHLY",
        "start": "month_start",
        "amount": None,
        "monthly_breakdown": False,
        "monthly_amounts": [],
        "growth_rate": 0,
        "alerts": [],
    },
    "budget_group": {
        "enabled": True,
        "name": "{folder}",
        "cascade": "NO_CASCADE",
        "alerts": [],
    },
    "behavior": {
        "on_exists": "skip",
        "include_shared": False,
        "manifest": None,
        "limit": None,
    },
}


class _Missing(dict):
    def __missing__(self, key):
        raise KeyError(key)


def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a mapping")
    return loaded


def load_config(path: str) -> dict:
    config = normalize_config(load_yaml(path))
    return attach_spreadsheet(config, path)


def load_runs(path: str, spreadsheet: str = None) -> list:
    raw = load_yaml(path)
    categories = raw.get("categories")
    if not categories:
        runs = [normalize_config(raw)]
    else:
        if not isinstance(categories, list):
            raise ValueError("categories must be a list")
        shared = {key: value for key, value in raw.items() if key != "categories"}
        runs = [normalize_config(_merge(shared, entry)) for entry in categories]
    return [attach_spreadsheet(run, path, spreadsheet) for run in runs]


def normalize_config(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("config must be a mapping")
    if not raw.get("cost_category"):
        raise ValueError("cost_category is required")
    config = _merge(DEFAULTS, raw)
    config["spreadsheet"] = normalize_spreadsheet(config.get("spreadsheet"))
    sheet_supplies_amount = bool(
        config["spreadsheet"]
        and config["spreadsheet"]["only"]
        and config["spreadsheet"]["columns"]["months"]
    )
    _require(config["perspective"]["rule_mode"], RULE_MODES, "perspective.rule_mode")
    _require(config["budget_group"]["cascade"], CASCADES, "budget_group.cascade")
    if "dry_run" in config["behavior"]:
        raise ValueError("behavior.dry_run is not supported; omit it and pass --apply to write")
    _require(config["behavior"]["on_exists"], ON_EXISTS, "behavior.on_exists")
    limit = config["behavior"].get("limit")
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
        raise ValueError("behavior.limit must be a positive integer")
    config["budget"] = _normalize_budget(
        config["budget"], "budget", sheet_supplies_amount
    )
    config["budget"]["alerts"] = _normalize_alerts(config["budget"].get("alerts"), "budget.alerts")
    config["budget_group"]["alerts"] = _normalize_alerts(
        config["budget_group"].get("alerts"), "budget_group.alerts"
    )
    bucket_budgets = config["buckets"].get("budgets") or {}
    if not isinstance(bucket_budgets, dict):
        raise ValueError("buckets.budgets must be a mapping of bucket name to budget settings")
    normalized_budgets = {}
    for name, settings in bucket_budgets.items():
        if not isinstance(settings, dict):
            raise ValueError(f"buckets.budgets.{name} must be a mapping")
        settings = dict(settings)
        account_settings = settings.pop("accounts", None)
        prepared = _merge(config["budget"], settings)
        prepared.pop("accounts", None)
        if "monthly_amounts" not in settings and (
            "amount" in settings or settings.get("monthly_breakdown") is False
        ):
            prepared["monthly_amounts"] = []
        bucket_budget = _normalize_budget(
            prepared, f"buckets.budgets.{name}", sheet_supplies_amount
        )
        if account_settings is not None:
            bucket_budget["accounts"] = _normalize_account_budgets(
                bucket_budget,
                account_settings,
                f"buckets.budgets.{name}",
                sheet_supplies_amount,
            )
        normalized_budgets[name] = bucket_budget
    config["buckets"]["budgets"] = normalized_budgets
    include = config["buckets"].get("include")
    exclude = config["buckets"].get("exclude") or []
    if include is not None and not isinstance(include, list):
        raise ValueError("buckets.include must be a list")
    if not isinstance(exclude, list):
        raise ValueError("buckets.exclude must be a list")
    config["buckets"]["include"] = include
    config["buckets"]["exclude"] = exclude
    return config


def render(template: str, values: dict) -> str:
    try:
        return str(template).format_map(_Missing(values))
    except KeyError as exc:
        raise ValueError(f"unknown template field {exc.args[0]}") from exc


def budget_for(
    config: dict,
    bucket_name: str,
    account_id: str = None,
    account_label: str = None,
    now: datetime = None,
) -> dict:
    bucket_budget = config["buckets"].get("budgets", {}).get(bucket_name)
    if not bucket_budget:
        budget = dict(config["budget"])
    else:
        accounts = bucket_budget.get("accounts")
        if accounts:
            matched = _match_account(accounts, account_id, account_label)
            if matched is None:
                return None
            budget = dict(matched)
        else:
            budget = {
                key: value
                for key, value in bucket_budget.items()
                if key != "accounts"
            }
    budget.pop("accounts", None)
    budget = _apply_sheet(config, budget, bucket_name, account_id, account_label)
    if budget is None:
        return None
    budget.setdefault("_account_name", _account_name(account_label, account_id))
    budget.setdefault("_folder", bucket_name)
    budget["start_time"] = resolve_start(budget["start"], now)
    if budget["monthly_breakdown"] and not budget["monthly_amounts"]:
        budget["monthly_amounts"] = split_amount(budget["amount"], 12)
        budget["amount"] = sum(budget["monthly_amounts"])
    return budget


def resolve_start(value, now: datetime = None) -> int:
    current = now or datetime.now(timezone.utc)
    if value == "month_start":
        start = datetime(current.year, current.month, 1, tzinfo=timezone.utc)
        return int(start.timestamp() * 1000)
    if value == "year_start":
        start = datetime(current.year, 1, 1, tzinfo=timezone.utc)
        return int(start.timestamp() * 1000)
    if isinstance(value, int):
        return value
    parsed = _calendar_date(value)
    if parsed is not None:
        start = datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)
        return int(start.timestamp() * 1000)
    raise ValueError(
        "budget.start must be month_start, year_start, YYYY-MM-DD, or epoch milliseconds"
    )


def month_starts(start_ms: int, count: int = 12) -> list:
    current = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
    year = current.year
    month = current.month
    stamps = []
    for _ in range(count):
        stamps.append(int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp() * 1000))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return stamps


def split_amount(amount, count: int = 12) -> list:
    cents = int(round(float(amount) * 100))
    base = cents // count
    extra = cents % count
    return [(base + (1 if index < extra else 0)) / 100 for index in range(count)]


def name_warning(kind: str, name: str) -> str:
    length = len(name)
    if 1 <= length <= BUDGET_NAME_MAX:
        return None
    return f"{kind} name length {length} is outside 1..{BUDGET_NAME_MAX}: {name}"


def alert_payloads(alerts: list) -> list:
    payloads = []
    for alert in alerts or []:
        payloads.append(
            {
                "percentage": alert["percentage"],
                "basedOn": alert.get("based_on", alert.get("basedOn")),
                "emailAddresses": alert.get("emails", alert.get("emailAddresses", [])),
                "userGroupIds": alert.get(
                    "user_group_ids", alert.get("userGroupIds", [])
                ),
                "slackWebhooks": alert.get(
                    "slack_webhooks", alert.get("slackWebhooks", [])
                ),
            }
        )
    return payloads


def proportions(count: int) -> list:
    if count <= 0:
        return []
    units = [10000 // count] * count
    remainder = 10000 % count
    for index in range(remainder):
        units[index] += 1
    return [unit / 100 for unit in units]


def _merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _normalize_account_budgets(
    bucket_budget: dict, accounts, label: str, allow_missing_amount: bool = False
) -> dict:
    if not isinstance(accounts, dict):
        raise ValueError(f"{label}.accounts must be a mapping of account id to budget settings")
    normalized = {}
    for key, settings in accounts.items():
        if not isinstance(settings, dict):
            raise ValueError(f"{label}.accounts.{key} must be a mapping")
        prepared = _merge(
            {field: value for field, value in bucket_budget.items() if field != "accounts"},
            settings,
        )
        prepared.pop("accounts", None)
        if "monthly_amounts" not in settings and (
            "amount" in settings or settings.get("monthly_breakdown") is False
        ):
            prepared["monthly_amounts"] = []
        normalized[str(key)] = _normalize_budget(
            prepared, f"{label}.accounts.{key}", allow_missing_amount
        )
    return normalized


def _apply_sheet(config, budget, bucket_name, account_id, account_label):
    sheet = config.get("spreadsheet")
    if not sheet:
        return budget
    if sheet.get("rows") is None:
        raise ValueError("spreadsheet rows were not loaded")
    if sheet["key"] == "bucket":
        row = sheet["rows"].get(bucket_name)
    elif account_id is None:
        row = None
    else:
        row = sheet["rows"].get(str(account_id))
    if row is None:
        if sheet["only"]:
            return None
        return budget
    updated = dict(budget)
    updated["amount"] = row["amount"]
    updated["alerts"] = [
        {**alert, "emails": list(alert.get("emails") or [])} for alert in row["alerts"]
    ]
    updated["_account_name"] = row.get("account_name") or _account_name(
        account_label, account_id
    )
    updated["_folder"] = row.get("folder") or bucket_name
    monthly_amounts = list(row.get("monthly_amounts") or [])
    if monthly_amounts:
        month_start = sheet["columns"].get("month_start")
        if month_start:
            updated["start"] = month_start
        updated["period"] = "YEARLY"
        updated["monthly_breakdown"] = True
        updated["monthly_amounts"] = monthly_amounts
        updated["amount"] = sum(monthly_amounts)
    else:
        updated["monthly_amounts"] = []
    warnings = list(row.get("warnings") or [])
    name_warning = _sheet_name_warning(row, account_id, account_label)
    if name_warning:
        warnings.append(name_warning)
    updated["_sheet_warnings"] = warnings
    return updated


def _sheet_name_warning(row: dict, account_id: str, account_label: str):
    expected = row.get("account_name")
    if not expected or not account_label or account_id is None:
        return None
    label = account_label.strip()
    if label == str(account_id):
        return None
    suffix = f"({account_id})"
    actual = label[: -len(suffix)].rstrip() if label.endswith(suffix) else label
    if actual == expected:
        return None
    return f"account name {expected} does not match {actual} for {account_id}"


def _match_account(accounts: dict, account_id: str, account_label: str):
    if account_id is not None and str(account_id) in accounts:
        return accounts[str(account_id)]
    if account_label and account_label in accounts:
        return accounts[account_label]
    return None


def _account_name(account_label: str, account_id: str) -> str:
    label = (account_label or str(account_id or "")).strip()
    suffix = f"({account_id})" if account_id is not None else ""
    if suffix and label.endswith(suffix):
        return label[: -len(suffix)].rstrip()
    return label


def _normalize_budget(
    budget: dict, label: str, allow_missing_amount: bool = False
) -> dict:
    normalized = dict(budget)
    _require(normalized.get("type"), BUDGET_TYPES, f"{label}.type")
    normalized["period"] = _period(normalized.get("period"), label)
    normalized["monthly_breakdown"] = _monthly_breakdown(
        normalized.get("monthly_breakdown", False), label
    )
    if normalized["monthly_breakdown"] and normalized["period"] != "YEARLY":
        raise ValueError(f"{label}.monthly_breakdown requires an annual period")
    amounts = normalized.get("monthly_amounts") or []
    if amounts and not normalized["monthly_breakdown"]:
        raise ValueError(f"{label}.monthly_amounts requires monthly_breakdown: true")
    if amounts and len(amounts) != 12:
        raise ValueError(f"{label}.monthly_amounts must contain 12 values")
    normalized["monthly_amounts"] = [_nonnegative_amount(value, f"{label}.monthly_amounts") for value in amounts]
    start = normalized.get("start")
    if not _valid_start(start):
        raise ValueError(
            f"{label}.start must be month_start, year_start, YYYY-MM-DD, or epoch milliseconds"
        )
    if normalized.get("amount") is not None:
        normalized["amount"] = _nonnegative_amount(normalized["amount"], f"{label}.amount")
    if normalized["monthly_breakdown"] and not normalized["monthly_amounts"]:
        if normalized.get("amount") is None and not allow_missing_amount:
            raise ValueError(
                f"{label}.amount or monthly_amounts is required when monthly_breakdown is true"
            )
    if normalized["type"] == "SPECIFIED_AMOUNT":
        if normalized["monthly_amounts"]:
            normalized["amount"] = sum(normalized["monthly_amounts"])
        elif normalized.get("amount") is None and not allow_missing_amount:
            raise ValueError(f"{label}.amount is required when type is SPECIFIED_AMOUNT")
    if "alerts" in normalized:
        normalized["alerts"] = _normalize_alerts(normalized.get("alerts"), f"{label}.alerts")
    return normalized


def _nonnegative_amount(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    amount = float(value)
    if amount < 0:
        raise ValueError(f"{label} must be zero or greater")
    return amount


def _normalize_alerts(alerts, label: str) -> list:
    if alerts is None:
        return []
    if not isinstance(alerts, list):
        raise ValueError(f"{label} must be a list")
    normalized = []
    for index, alert in enumerate(alerts):
        entry = f"{label}[{index}]"
        if not isinstance(alert, dict):
            raise ValueError(f"{entry} must be a mapping")
        percentage = alert.get("percentage")
        if isinstance(percentage, bool) or not isinstance(percentage, (int, float)):
            raise ValueError(f"{entry}.percentage must be a number")
        based_on = alert.get("based_on", alert.get("basedOn", "ACTUAL_COST"))
        if based_on not in ("ACTUAL_COST", "FORECASTED_COST"):
            raise ValueError(f"{entry}.based_on must be ACTUAL_COST or FORECASTED_COST")
        emails = alert.get("emails", alert.get("emailAddresses", []))
        if emails is None:
            emails = []
        if not isinstance(emails, list):
            raise ValueError(f"{entry}.emails must be a list")
        normalized.append(
            {
                "percentage": float(percentage),
                "based_on": based_on,
                "emails": [str(item) for item in emails],
                "user_group_ids": list(
                    alert.get("user_group_ids", alert.get("userGroupIds", [])) or []
                ),
                "slack_webhooks": list(
                    alert.get("slack_webhooks", alert.get("slackWebhooks", [])) or []
                ),
            }
        )
    return normalized


def _valid_start(value) -> bool:
    if value in ("month_start", "year_start") or isinstance(value, int):
        return True
    return _calendar_date(value) is not None


def _calendar_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and len(value) == 10 and value[4] == "-" and value[7] == "-":
        try:
            year, month, day = (int(part) for part in value.split("-"))
            return date(year, month, day)
        except ValueError:
            return None
    return None


def _period(value, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label}.period must be MONTHLY or YEARLY")
    period = PERIOD_ALIASES.get(value.upper(), value.upper())
    _require(period, PERIODS, f"{label}.period")
    return period


def _monthly_breakdown(value, label: str) -> bool:
    if value in (True, False):
        return value
    if isinstance(value, str) and value.lower() in ("true", "yes"):
        return True
    if isinstance(value, str) and value.lower() in ("false", "no"):
        return False
    raise ValueError(f"{label}.monthly_breakdown must be true or false")


def _require(value, allowed: set, label: str) -> None:
    if value not in allowed:
        raise ValueError(f"{label} must be one of {sorted(allowed)}")
