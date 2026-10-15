from os import getenv

from requests import get, post

PARAMS = {
    "routingId": getenv("HARNESS_ACCOUNT_ID"),
    "accountIdentifier": getenv("HARNESS_ACCOUNT_ID"),
}

HEADERS = {
    "x-api-key": getenv("HARNESS_PLATFORM_API_KEY"),
}


class Folder:
    def __init__(
        self,
        name: str,
        uuid: str = "",
        create: bool = False,
    ):
        self.name = name

        # if existing folder get its id
        # otherwise create it
        if not uuid:
            if all_cc := [
                x.get("uuid") for x in Folder.get_all() if x.get("name") == self.name
            ]:
                self.uuid = all_cc.pop()
            elif create:
                self.create()
            else:
                self.uuid = None

    def create(self):
        resp = post(
            f"https://{getenv('HARNESS_URL')}/gateway/ccm/api/perspectiveFolders/create",
            params=PARAMS,
            headers=HEADERS,
            json={"ceViewFolder": {"name": self.name}, "perspectiveIds": []},
        )

        resp.raise_for_status()

        self.uuid = resp.json().get("data", {}).get("uuid")

    def get_all():
        resp = get(
            f"https://{getenv('HARNESS_URL')}/gateway/ccm/api/perspectiveFolders",
            params=PARAMS,
            headers=HEADERS,
        )

        resp.raise_for_status()

        return resp.json().get("data", [])

    def __repr__(self):
        return f"Perspective Folder: {self.name} ({self.uuid})"
