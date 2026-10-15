from csv import reader
from sys import argv, exit

from costcategories import (
    CostCategory,
    Bucket,
    SharedBucket,
    ViewCondition,
    ViewOperator,
)


if __name__ == "__main__":
    if len(argv) < 2:
        print(f"usage: {argv[0]} <csv file>")
        exit(1)

    csv_file = argv[1]

    # load in the file
    file = open(csv_file, "r")
    reader = reader(file, delimiter=",")

    # grab first row (headers) and build cost category storage
    metadata = reader.__next__()

    cost_categories = {}
    # cost categories are defined after column 2
    for category in metadata[2:]:
        cost_categories[category] = {"buckets": {}, "shared": {}}

    # process all other rows
    for row in reader:
        cloud = row[0]
        account_id = row[1]

        # for each cost category (column 3 onward), place account in bucket
        for idx, bucket in enumerate(row[2:], start=2):
            # catch shared buckets
            if bucket.startswith("shared_"):
                name = bucket.split("_")[2]
                type = bucket.split("_")[1]

                # add account to shared bucket
                if name in cost_categories[metadata[idx]]["shared"]:
                    if (
                        cloud
                        in cost_categories[metadata[idx]]["shared"][name]["accounts"]
                    ):
                        cost_categories[metadata[idx]]["shared"][name]["accounts"][
                            cloud
                        ].append(account_id)
                    else:
                        cost_categories[metadata[idx]]["shared"][name]["accounts"][
                            cloud
                        ] = [account_id]
                else:
                    cost_categories[metadata[idx]]["shared"][name] = {
                        "accounts": {cloud: [account_id]},
                        "type": type,
                    }

            # regular buckets
            else:
                if bucket in cost_categories[metadata[idx]]["buckets"]:
                    if cloud in cost_categories[metadata[idx]]["buckets"][bucket]:
                        cost_categories[metadata[idx]]["buckets"][bucket][cloud].append(
                            account_id
                        )
                    else:
                        cost_categories[metadata[idx]]["buckets"][bucket][cloud] = [
                            account_id
                        ]
                else:
                    cost_categories[metadata[idx]]["buckets"][bucket] = {
                        cloud: [account_id]
                    }

    # create each cost category
    for category in cost_categories:
        # build cost targets (buckets)
        cost_targets = []

        for bucket_name in cost_categories[category]["buckets"].keys():
            bucket = Bucket(bucket_name)

            if "aws" in cost_categories[category]["buckets"][bucket_name]:
                bucket.add_rule(
                    {
                        "viewConditions": [
                            ViewCondition(
                                "awsUsageaccountid",
                                "Account",
                                "AWS",
                                "AWS",
                                ViewOperator.IN,
                                cost_categories[category]["buckets"][bucket_name][
                                    "aws"
                                ],
                            ).format()
                        ]
                    }
                )
            if "azure" in cost_categories[category]["buckets"][bucket_name]:
                bucket.add_rule(
                    {
                        "viewConditions": [
                            ViewCondition(
                                "azureSubscriptionGuid",
                                "Subscription id",
                                "AZURE",
                                "Azure",
                                ViewOperator.IN,
                                cost_categories[category]["buckets"][bucket_name][
                                    "azure"
                                ],
                            ).format()
                        ]
                    }
                )
            if "gcp" in cost_categories[category]["buckets"][bucket_name]:
                bucket.add_rule(
                    {
                        "viewConditions": [
                            ViewCondition(
                                "gcpProjectId",
                                "Project",
                                "GCP",
                                "GCP",
                                ViewOperator.IN,
                                cost_categories[category]["buckets"][bucket_name][
                                    "gcp"
                                ],
                            ).format()
                        ]
                    }
                )

            cost_targets.append(bucket.format())

        shared_buckets = []

        for bucket_name in cost_categories[category]["shared"].keys():
            bucket = SharedBucket(
                bucket_name, cost_categories[category]["shared"][bucket_name]["type"]
            )

            if "aws" in cost_categories[category]["shared"][bucket_name]["accounts"]:
                bucket.add_rule(
                    {
                        "viewConditions": [
                            ViewCondition(
                                "awsUsageaccountid",
                                "Account",
                                "AWS",
                                "AWS",
                                ViewOperator.IN,
                                cost_categories[category]["shared"][bucket_name][
                                    "accounts"
                                ]["aws"],
                            ).format()
                        ]
                    }
                )
            if "azure" in cost_categories[category]["shared"][bucket_name]["accounts"]:
                bucket.add_rule(
                    {
                        "viewConditions": [
                            ViewCondition(
                                "azureSubscriptionGuid",
                                "Subscription id",
                                "AZURE",
                                "Azure",
                                ViewOperator.IN,
                                cost_categories[category]["shared"][bucket_name][
                                    "accounts"
                                ]["azure"],
                            ).format()
                        ]
                    }
                )
            if "gcp" in cost_categories[category]["shared"][bucket_name]["accounts"]:
                bucket.add_rule(
                    {
                        "viewConditions": [
                            ViewCondition(
                                "gcpProjectId",
                                "Project",
                                "GCP",
                                "GCP",
                                ViewOperator.IN,
                                cost_categories[category]["shared"][bucket_name][
                                    "accounts"
                                ]["gcp"],
                            ).format()
                        ]
                    }
                )

            shared_buckets.append(bucket.format())

        # create cost category and update based on buckets
        cc = CostCategory(category)

        if cc.update(cost_targets, shared_buckets):
            print("update successful")
            print(cc)
