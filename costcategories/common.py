from os import getenv
from enum import Enum

from requests import get, put, post


HEADERS = {
    "x-api-key": getenv("HARNESS_PLATFORM_API_KEY"),
}


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
    def __init__(self, name: str, strategy: str, splits: list[Split] = []):
        super().__init__(name)
        self.strategy = strategy
        self.splits = splits

    def __repr__(self) -> str:
        return super().__repr__() + f" {self.strategy}: {len(self.splits)} splits"

    def format(self) -> dict:
        # payload = {"strategy": self.strategy}
        # if self.splits:
        #     payload | {"splits": [split.format() for split in self.splits] }

        return super().format() | {
            "strategy": self.strategy,
            "splits": [split.format() for split in self.splits]
            if self.splits
            else None,
        }


class CostCategory:
    def __init__(
        self,
        name: str,
        uuid: str = "",
        buckets: list[Bucket] = [],
        shared_buckets: list[SharedBucket] = [],
        create: bool = False,
    ):
        self.name = name

        # if existing cc get its id
        if not uuid:
            if all_cc := [
                x.get("uuid")
                for x in CostCategory.get_all()
                if x.get("name") == self.name
            ]:
                self.uuid = all_cc.pop()
            elif create:
                self.create()
            else:
                self.uuid = None

        self.buckets = buckets
        self.shared_buckets = shared_buckets

    def __repr__(self) -> str:
        category = f"Cost Category: {self.name} ({self.uuid})"
        for bucket in self.buckets:
            category += f"\n\t{bucket}"
        return category

    def add(self, bucket: Bucket):
        self.buckets.append(bucket)

    def payload(self, cost_targets: list = [], shared_buckets: list = []) -> dict:
        if not cost_targets:
            for bucket in self.buckets:
                cost_targets.append(bucket.format())

        if not shared_buckets:
            for bucket in self.shared_buckets:
                shared_buckets.append(bucket.format())

        return {
            "accountId": getenv("HARNESS_ACCOUNT_ID"),
            "name": self.name,
            "uuid": self.uuid,
            "costTargets": cost_targets,
            "sharedCosts": shared_buckets,
            "unallocatedCost": {
                "strategy": "DISPLAY_NAME",
                "label": "Unattributed",
                "sharingStrategy": None,
                "splits": None,
            },
        }

    def update(self, cost_targets: list = [], shared_buckets: list = []) -> bool:
        # given a list of cost targets update an existing cost catagory

        if not self.uuid:
            return self.create(cost_targets)
        else:
            resp = put(
                f"https://{getenv('HARNESS_URL')}/gateway/ccm/api/business-mapping",
                params={
                    "accountIdentifier": getenv("HARNESS_ACCOUNT_ID"),
                },
                headers=HEADERS,
                json=self.payload(cost_targets, shared_buckets),
            )

            resp.raise_for_status()

            return resp.status_code == 200

    def create(self, cost_targets: list = [], shared_buckets: list = []) -> bool:
        # given a list of cost targets create a cost catagory

        resp = post(
            f"https://{getenv('HARNESS_URL')}/gateway/ccm/api/business-mapping",
            params={
                "accountIdentifier": getenv("HARNESS_ACCOUNT_ID"),
            },
            headers=HEADERS,
            json=self.payload(cost_targets, shared_buckets),
        )

        resp.raise_for_status()

        if resp.status_code == 200:
            self.uuid = resp.json().get("resource", {}).get("uuid")
            return True

        return False

    def get_all() -> list:
        # get all the cost catagories in an account

        resp = get(
            f"https://{getenv('HARNESS_URL')}/ccm/api/business-mapping",
            params={"accountIdentifier": getenv("HARNESS_ACCOUNT_ID"), "limit": 100},
            headers=HEADERS,
        )

        resp.raise_for_status()

        return resp.json().get("resource", {}).get("businessMappings", [])

    def get(self) -> dict:
        # get the content of a cc

        resp = get(
            f"https://{getenv('HARNESS_URL')}/ccm/api/business-mapping/{self.uuid}",
            params={"accountIdentifier": getenv("HARNESS_ACCOUNT_ID"), "limit": 100},
            headers=HEADERS,
        )

        resp.raise_for_status()

        return resp.json()
