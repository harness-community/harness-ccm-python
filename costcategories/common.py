from enum import Enum

from harness import as_list, entity_id, request


class CloudAccount:
    def __init__(
        self,
        cloud: str,
        identifier: str,
        bucket: str,
    ):
        cloud_fmt = cloud.lower()
        if cloud_fmt not in ["aws", "azure", "gcp"]:
            raise Exception(f"Unknown cloud {cloud}")

        self.cloud = cloud_fmt
        self.identifier = identifier
        self.bucket = bucket


class ViewOperator(Enum):
    IN = "IN"
    NOT_IN = "NOT_IN"
    NULL = "NULL"
    NOT_NULL = "NOT_NULL"
    LIKE = "LIKE"


class ViewCondition:
    def __init__(
        self,
        fieldId: str,
        fieldName: str,
        identifier: str,
        identifierName: str,
        viewOperator: ViewOperator,
        values: list,
    ):
        self.fieldId = fieldId
        self.fieldName = fieldName
        self.identifier = identifier
        self.identifierName = identifierName
        self.viewOperator = viewOperator
        self.values = values

    def format(self):
        return {
            "type": "VIEW_ID_CONDITION",
            "viewField": {
                "fieldId": self.fieldId,
                "fieldName": self.fieldName,
                "identifier": self.identifier,
                "identifierName": self.identifierName,
            },
            "viewOperator": self.viewOperator.value,
            "values": self.values,
        }


class Bucket:
    def __init__(
        self,
        name: str,
    ):
        self.name = name
        self.rules = []

    def __repr__(self) -> str:
        return f"{self.name}: {len(self.rules)} rules"

    def add_rule(self, rule):
        self.rules.append(rule)

    def format(self) -> dict:
        return {"name": self.name, "rules": self.rules}


class Strategy(Enum):
    EQUAL = "EQUAL"
    PROPORTIONAL = "PROPORTIONAL"
    FIXED = "FIXED"


class Split:
    def __init__(self, name: str, percent: float):
        self.name = name
        self.percent = percent

    def format(self) -> dict:
        return {"costTargetName": self.name, "percentageContribution": self.percent}


class SharedBucket(Bucket):
    def __init__(self, name: str, strategy: str, splits: list = None):
        super().__init__(name)
        self.strategy = strategy
        self.splits = splits or []

    def __repr__(self) -> str:
        return super().__repr__() + f" {self.strategy}: {len(self.splits)} splits"

    def format(self) -> dict:
        return super().format() | {
            "strategy": self.strategy,
            "splits": [split.format() for split in self.splits] if self.splits else None,
        }


class CostCategory:
    def __init__(
        self,
        name: str,
        uuid: str = "",
        buckets: list = None,
        shared_buckets: list = None,
        create: bool = False,
    ):
        self.name = name
        self.uuid = uuid or None
        self.buckets = list(buckets or [])
        self.shared_buckets = list(shared_buckets or [])

        if not self.uuid:
            matched = [
                item.get("uuid")
                for item in CostCategory.get_all()
                if item.get("name") == self.name
            ]
            if matched:
                self.uuid = matched[0]
            elif create:
                self.create()

    def __repr__(self) -> str:
        category = f"Cost Category: {self.name} ({self.uuid})"
        for bucket in self.buckets:
            category += f"\n\t{bucket}"
        return category

    def add(self, bucket: Bucket):
        self.buckets.append(bucket)

    def payload(self, cost_targets: list = None, shared_buckets: list = None) -> dict:
        from harness import account_id

        targets = list(cost_targets or [])
        shared = list(shared_buckets or [])
        if not targets:
            targets = [bucket.format() for bucket in self.buckets]
        if not shared:
            shared = [bucket.format() for bucket in self.shared_buckets]

        return {
            "accountId": account_id(),
            "name": self.name,
            "uuid": self.uuid,
            "costTargets": targets,
            "sharedCosts": shared,
            "unallocatedCost": {
                "strategy": "DISPLAY_NAME",
                "label": "Unattributed",
                "sharingStrategy": None,
                "splits": None,
            },
        }

    def update(self, cost_targets: list = None, shared_buckets: list = None) -> bool:
        if not self.uuid:
            return self.create(cost_targets, shared_buckets)
        request(
            "PUT",
            "business-mapping",
            json=self.payload(cost_targets, shared_buckets),
        )
        return True

    def create(self, cost_targets: list = None, shared_buckets: list = None) -> bool:
        body = request(
            "POST",
            "business-mapping",
            json=self.payload(cost_targets, shared_buckets),
        )
        self.uuid = entity_id(body)
        return bool(self.uuid)

    @staticmethod
    def get_all() -> list:
        body = request(
            "GET",
            "ccm/api/business-mapping",
            params={"limit": 100},
            via_gateway=False,
        )
        if isinstance(body, dict):
            resource = body.get("resource") or body.get("data") or body
            if isinstance(resource, dict) and isinstance(
                resource.get("businessMappings"), list
            ):
                return resource["businessMappings"]
        return as_list(body)

    def get(self) -> dict:
        return request(
            "GET",
            f"ccm/api/business-mapping/{self.uuid}",
            params={"limit": 100},
            via_gateway=False,
        )
