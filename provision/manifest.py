from copy import deepcopy
from json import dump, load
from os.path import exists


EMPTY = {
    "cost_category": None,
    "folders": [],
    "perspectives": [],
    "budgets": [],
    "budget_groups": [],
    "errors": [],
    "skipped": [],
}


def empty_manifest() -> dict:
    return deepcopy(EMPTY)


def load_manifest(path: str) -> dict:
    if not path or not exists(path):
        return empty_manifest()
    with open(path, "r", encoding="utf-8") as handle:
        loaded = load(handle)
    if not isinstance(loaded, dict):
        return empty_manifest()
    for key, value in EMPTY.items():
        loaded.setdefault(key, deepcopy(value))
    return loaded


def save_manifest(path: str, manifest: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        dump(manifest, handle, indent=2)
        handle.write("\n")


def remember(items: list, entry: dict) -> None:
    for existing in items:
        same_id = entry.get("uuid") and existing.get("uuid") == entry["uuid"]
        same_name = existing.get("name") == entry.get("name")
        if same_id or same_name:
            created = bool(existing.get("created") or entry.get("created"))
            existing.update(entry)
            existing["created"] = created
            return
    items.append(entry)
