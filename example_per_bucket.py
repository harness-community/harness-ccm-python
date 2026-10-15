from sys import argv, exit
from os import getenv

from requests import post

from perspectives import Folder
from costcategories import CostCategory

PARAMS = {
    "routingId": getenv("HARNESS_ACCOUNT_ID"),
    "accountIdentifier": getenv("HARNESS_ACCOUNT_ID"),
}

HEADERS = {
    "x-api-key": getenv("HARNESS_PLATFORM_API_KEY"),
}


def create_perspective(
    name: str, cc_id: str, cc_name: str, bucket: str, folder_id: str
):
    resp = post(
        f"https://{getenv('HARNESS_URL')}/gateway/ccm/api/perspective",
        params=PARAMS,
        headers=HEADERS,
        json={
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
            "viewRules": [
                {
                    "viewConditions": [
                        {
                            "type": "VIEW_ID_CONDITION",
                            "viewField": {
                                "fieldId": cc_id,
                                "fieldName": cc_name,
                                "identifierName": "Cost Categories",
                                "identifier": "BUSINESS_MAPPING",
                            },
                            "viewOperator": "IN",
                            "values": [bucket],
                        }
                    ]
                }
            ],
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
        },
    )

    resp.raise_for_status()

    return resp.json()


if __name__ == "__main__":
    if len(argv) < 3:
        print(f"usage: {argv[0]} <perspective folder> <cost catagory name>")
        exit(1)

    folder_name = argv[1]
    cost_catagory_name = argv[2]

    folder = Folder(folder_name, create=True)
    cc = CostCategory(cost_catagory_name)

    print(folder)
    print(cc)

    for bucket in cc.get().get("resource").get("costTargets"):
        name = bucket.get("name")
        print(name)
        print(
            create_perspective(
                f"{cc.name} - {name}", cc.uuid, cc.name, name, folder.uuid
            ).get("status")
        )
