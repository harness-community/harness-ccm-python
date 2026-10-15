from provision.config import alert_payloads, month_starts, proportions


def budget_payload(
    account: str,
    name: str,
    perspective_id: str,
    perspective_name: str,
    budget: dict,
    start_time: int,
    folder_id: str = None,
) -> dict:
    body = {
        "accountId": account,
        "name": name,
        "scope": {
            "type": "PERSPECTIVE",
            "viewId": perspective_id,
            "viewName": perspective_name,
            "budgetScopeType": "PERSPECTIVE",
        },
        "type": budget["type"],
        "period": budget["period"],
        "startTime": start_time,
        "growthRate": budget.get("growth_rate", 0),
        "alertThresholds": alert_payloads(budget.get("alerts")),
    }
    if folder_id:
        body["folderId"] = folder_id
    if budget.get("amount") is not None:
        body["budgetAmount"] = budget["amount"]
    breakdown = yearly_breakdown(
        budget.get("period"),
        budget.get("monthly_breakdown"),
        budget.get("monthly_amounts") or [],
        start_time,
    )
    if breakdown:
        body["budgetMonthlyBreakdown"] = breakdown
    return body


def yearly_breakdown(period, monthly_breakdown, monthly_amounts, start_time) -> dict:
    if period != "YEARLY":
        return None
    if not monthly_breakdown:
        return {"budgetBreakdown": "YEARLY"}
    times = month_starts(start_time, len(monthly_amounts))
    return {
        "budgetBreakdown": "MONTHLY",
        "budgetMonthlyAmount": [
            {"time": times[index], "value": amount}
            for index, amount in enumerate(monthly_amounts)
        ],
    }


def budget_group_payload(
    account: str,
    name: str,
    amount: float,
    period: str,
    start_time: int,
    cascade: str,
    budgets: list,
    alerts: list,
    monthly_breakdown: bool = False,
    monthly_amounts: list = None,
) -> dict:
    shares = proportions(len(budgets)) if cascade == "PROPORTIONAL" else None
    children = []
    for index, budget in enumerate(budgets):
        child = {
            "id": budget["uuid"],
            "isBudgetGroup": False,
            "budgetGroup": False,
        }
        if shares is not None:
            child["proportion"] = shares[index]
        children.append(child)
    body = {
        "accountId": account,
        "name": name,
        "budgetGroupAmount": amount,
        "period": period,
        "startTime": start_time,
        "cascadeType": cascade,
        "childEntities": children,
        "alertThresholds": alert_payloads(alerts),
    }
    breakdown = yearly_breakdown(
        period, monthly_breakdown, monthly_amounts or [], start_time
    )
    if breakdown:
        body["budgetGroupMonthlyBreakdown"] = breakdown
    return body
