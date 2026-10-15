from harness import entity_id, request


class Folder:
    def __init__(
        self,
        name: str,
        uuid: str = "",
        create: bool = False,
    ):
        self.name = name
        self.uuid = uuid or None

        if not self.uuid:
            matched = [
                item.get("uuid")
                for item in Folder.get_all()
                if item.get("name") == self.name
            ]
            if matched:
                self.uuid = matched[0]
            elif create:
                self.create()

    def create(self):
        body = request(
            "POST",
            "perspectiveFolders/create",
            json={"ceViewFolder": {"name": self.name}, "perspectiveIds": []},
        )
        self.uuid = entity_id(body)

    @staticmethod
    def get_all():
        body = request("GET", "perspectiveFolders")
        data = body.get("data", []) if isinstance(body, dict) else []
        return data if isinstance(data, list) else []

    def __repr__(self):
        return f"Perspective Folder: {self.name} ({self.uuid})"
