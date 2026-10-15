from harness import as_list, entity_id, index_by_name, request


def list_budget_groups() -> dict:
    return index_by_name(as_list(request("GET", "budgetGroups")))


def create_budget_group(payload: dict) -> dict:
    body = request("POST", "budgetGroups", json=payload)
    return {"name": payload["name"], "uuid": entity_id(body), "raw": body}


def update_budget_group(group_id: str, payload: dict) -> dict:
    body = request(
        "PUT",
        f"budgetGroups/{group_id}",
        json={**payload, "uuid": group_id},
    )
    return {"name": payload["name"], "uuid": group_id, "raw": body}


def delete_budget_group(group_id: str) -> None:
    request("DELETE", f"budgetGroups/{group_id}")


def delete_cost_category(category_id: str) -> None:
    request("DELETE", f"business-mapping/{category_id}")
