from harness import as_list, entity_id, index_by_name, request


def perspective_payload(name: str, folder_id: str, conditions: list) -> dict:
    return {
        "viewVersion": "v1",
        "viewTimeRange": {"viewTimeRangeType": "LAST_7"},
        "viewType": "CUSTOMER",
        "viewVisualization": {
            "groupBy": {
                "fieldId": "product",
                "fieldName": "Product",
                "identifier": "COMMON",
                "identifierName": "COMMON",
            },
            "chartType": "STACKED_LINE_CHART",
        },
        "name": name,
        "viewRules": [{"viewConditions": conditions}],
        "viewState": "COMPLETED",
        "viewPreferences": {
            "showAnomalies": True,
            "includeOthers": False,
            "includeUnallocatedCost": False,
            "awsPreferences": {
                "includeDiscounts": True,
                "includeCredits": True,
                "includeRefunds": True,
                "includeTaxes": True,
                "awsCost": "UNBLENDED",
            },
            "gcpPreferences": {"includeDiscounts": True, "includeTaxes": True},
        },
        "folderId": folder_id,
    }


def list_perspectives() -> dict:
    page_no = 0
    page_size = 100
    views = []
    seen = set()
    while page_no < 100:
        body = request(
            "GET",
            "perspective/getAllPerspectives",
            params={
                "pageSize": page_size,
                "pageNo": page_no,
                "sortType": "NAME",
                "sortOrder": "ASCENDING",
            },
        )
        data = body.get("data") if isinstance(body, dict) else {}
        total = None
        if isinstance(data, dict):
            batch = data.get("views") or []
            total = data.get("totalCount")
        else:
            batch = as_list(body)
        added = 0
        for view in batch:
            marker = view.get("id") or view.get("uuid") or view.get("name")
            if marker in seen:
                continue
            seen.add(marker)
            views.append(view)
            added += 1
        page_no += 1
        if not batch or added == 0:
            break
        if total is not None and len(views) >= total:
            break
        if len(batch) < page_size:
            break
    return index_by_name(views)


def create_perspective(payload: dict) -> dict:
    body = request("POST", "perspective", json=payload)
    return {"name": payload["name"], "uuid": entity_id(body), "raw": body}


def update_perspective(perspective_id: str, payload: dict) -> dict:
    body = request(
        "PUT",
        "perspective",
        json={**payload, "uuid": perspective_id},
    )
    return {"name": payload["name"], "uuid": perspective_id, "raw": body}


def delete_perspective(perspective_id: str) -> None:
    request("DELETE", "perspective", params={"perspectiveId": perspective_id})


def delete_folder(folder_id: str) -> None:
    request("DELETE", f"perspectiveFolders/{folder_id}")
