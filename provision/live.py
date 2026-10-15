from budgets.budget import create_budget, list_budgets, update_budget
from budgets.group import create_budget_group, list_budget_groups, update_budget_group
from harness import ApiError, account_id, entity_id, index_by_name, request
from perspectives.common import Folder
from perspectives.perspective import (
    create_perspective,
    list_perspectives,
    update_perspective,
)


class LiveHarness:
    def __init__(self):
        self.account_id = account_id()
        self._folders = None
        self._perspectives = None
        self._budgets = None
        self._groups = None

    def find_folder(self, name: str):
        if self._folders is None:
            try:
                listed = Folder.get_all()
            except ApiError:
                raise
            self._folders = index_by_name(listed or [])
        return self._folders.get(name)

    def create_folder(self, name: str) -> dict:
        body = request(
            "POST",
            "perspectiveFolders/create",
            json={"ceViewFolder": {"name": name}, "perspectiveIds": []},
        )
        item = {"name": name, "uuid": entity_id(body)}
        if self._folders is None:
            self._folders = {}
        self._folders[name] = item
        return item

    def find_perspective(self, name: str):
        if self._perspectives is None:
            self._perspectives = list_perspectives()
        return self._perspectives.get(name)

    def create_perspective(self, payload: dict) -> dict:
        created = create_perspective(payload)
        if self._perspectives is None:
            self._perspectives = {}
        if created.get("uuid"):
            self._perspectives[created["name"]] = created
        return created

    def update_perspective(self, perspective_id: str, payload: dict) -> dict:
        updated = update_perspective(perspective_id, payload)
        if self._perspectives is None:
            self._perspectives = {}
        self._perspectives[updated["name"]] = updated
        return updated

    def find_budget(self, name: str):
        if self._budgets is None:
            self._budgets = list_budgets()
        return self._budgets.get(name)

    def create_budget(self, payload: dict) -> dict:
        created = create_budget(payload)
        if self._budgets is None:
            self._budgets = {}
        if created.get("uuid"):
            self._budgets[created["name"]] = created
        return created

    def update_budget(self, budget_id: str, payload: dict) -> dict:
        updated = update_budget(budget_id, payload)
        if self._budgets is None:
            self._budgets = {}
        self._budgets[updated["name"]] = updated
        return updated

    def find_budget_group(self, name: str):
        if self._groups is None:
            self._groups = list_budget_groups()
        return self._groups.get(name)

    def create_budget_group(self, payload: dict) -> dict:
        created = create_budget_group(payload)
        if self._groups is None:
            self._groups = {}
        if created.get("uuid"):
            self._groups[created["name"]] = created
        return created

    def update_budget_group(self, group_id: str, payload: dict) -> dict:
        updated = update_budget_group(group_id, payload)
        if self._groups is None:
            self._groups = {}
        self._groups[updated["name"]] = updated
        return updated
