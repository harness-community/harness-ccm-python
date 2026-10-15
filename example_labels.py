from costcategories import (
    CloudAccount,
    CostCategory,
    Bucket,
    ViewCondition,
    ViewOperator,
)


if __name__ == "__main__":
    cost_category = CostCategory("My buissness units")

    # create a bucket for costs
    bucket = Bucket("This Buissness Unit")

    # add a rule for costs in this bucket
    # rules have some number of view conditions
    # view conditions use AND when specified in the same rule
    # all rules are combined with OR

    # resources with the label application_id values app123 or app456
    bucket.add_rule(
        {
            "viewConditions": [
                ViewCondition(
                    "labels.value",
                    "user_application_id",
                    "LABEL",
                    "label",
                    ViewOperator.IN,
                    ["app123", "app456"],
                ).format()
            ]
        }
    )

    # OR

    # not in the dynamodb service but with application_id in app789
    bucket.add_rule(
        {
            "viewConditions": [
                ViewCondition(
                    "awsServicecode",
                    "Service",
                    "AWS",
                    "AWS",
                    ViewOperator.NOT_IN,
                    ["Amazon DynamoDB"],
                ).format(),
                ViewCondition(
                    "labels.value",
                    "user_application_id",
                    "LABEL",
                    "label",
                    ViewOperator.IN,
                    [
                        "app789",
                    ],
                ).format(),
            ]
        }
    )

    # add as many buckets and rules as needed
    cost_category.add(bucket)

    # you can update or create the cost category given all the buckets
    if cost_category.update():
        print("update successful")
        print(cost_category)
