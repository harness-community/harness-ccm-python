from harness import as_list, entity_id, index_by_name, request


def list_budgets() -> dict:
    return index_by_name(as_list(request("GET", "budgets")))


def create_budget(payload: dict) -> dict:
    body = request("POST", "budgets", json=payload)
    amount = _amount(body)
    return {
        "name": payload["name"],
        "uuid": entity_id(body),
        "budgetAmount": amount,
        "raw": body,
    }


def update_budget(budget_id: str, payload: dict) -> dict:
    body = request(
        "PUT",
        f"budgets/{budget_id}",
        json={**payload, "uuid": budget_id},
    )
    return {
        "name": payload["name"],
        "uuid": budget_id,
        "budgetAmount": float(payload.get("budgetAmount") or 0),
        "raw": body,
    }


def delete_budget(budget_id: str) -> None:
    request("DELETE", f"budgets/{budget_id}")


def _amount(body) -> float:
    if not isinstance(body, dict):
        return 0
    if body.get("budgetAmount") is not None:
        return float(body["budgetAmount"])
    for key in ("data", "resource"):
        nested = body.get(key)
        if isinstance(nested, dict) and nested.get("budgetAmount") is not None:
            return float(nested["budgetAmount"])
    return 0
