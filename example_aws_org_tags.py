"""
Example: Create Harness Cost Categories from AWS Organizations Account Tags

This script demonstrates how to:
1. Use boto3 to call the AWS Organizations API and list all accounts
2. Retrieve tags for each account
3. Create Harness cost categories based on a specific tag key
4. Organize accounts into buckets based on their tag values

Prerequisites:
- AWS credentials configured with Organizations read permissions
- boto3 installed: pip install boto3
- Harness environment variables set:
  - HARNESS_URL
  - HARNESS_ACCOUNT_ID
  - HARNESS_PLATFORM_API_KEY

Usage:
    python example_aws_org_tags.py --tag-key Environment
    python example_aws_org_tags.py --tag-key Department --category-name "Department Cost Allocation"
"""

import boto3
import argparse
from collections import defaultdict
from costcategories.costcategory import CostCategory
from costcategories.bucket import Bucket
from costcategories.cloudaccount import CloudAccount
from costcategories.viewcondition import ViewCondition, ViewOperator


def list_aws_accounts_with_tags(tag_key):
    """
    List all AWS accounts from Organizations and retrieve the specified tag value.

    Args:
        tag_key (str): The tag key to look for on each account

    Returns:
        dict: Dictionary mapping tag values to lists of account IDs
              Example: {'Production': ['123456789012', '234567890123'], 'Development': ['345678901234']}
    """
    org_client = boto3.client("organizations")
    accounts_by_tag = defaultdict(list)
    untagged_accounts = []

    print(f"Fetching AWS accounts from Organizations API...")

    try:
        # List all accounts in the organization
        paginator = org_client.get_paginator("list_accounts")

        for page in paginator.paginate():
            for account in page["Accounts"]:
                account_id = account["Id"]
                account_name = account["Name"]
                status = account["Status"]

                # Skip suspended or closed accounts
                if status != "ACTIVE":
                    print(
                        f"  Skipping {account_name} ({account_id}) - Status: {status}"
                    )
                    continue

                # Get tags for this account
                try:
                    tags_response = org_client.list_tags_for_resource(
                        ResourceId=account_id
                    )

                    # Look for the specific tag key
                    tag_value = None
                    for tag in tags_response.get("Tags", []):
                        if tag["Key"] == tag_key:
                            tag_value = tag["Value"]
                            break

                    if tag_value:
                        accounts_by_tag[tag_value].append(
                            {"id": account_id, "name": account_name}
                        )
                        print(
                            f"  ✓ {account_name} ({account_id}) → {tag_key}={tag_value}"
                        )
                    else:
                        untagged_accounts.append(
                            {"id": account_id, "name": account_name}
                        )
                        print(
                            f"  ⚠ {account_name} ({account_id}) → No '{tag_key}' tag found"
                        )

                except org_client.exceptions.AccountNotFoundException:
                    print(f"  ✗ Account {account_id} not found")
                except org_client.exceptions.AccessDeniedException:
                    print(f"  ✗ Access denied to tags for {account_id}")
                except Exception as e:
                    print(f"  ✗ Error fetching tags for {account_id}: {str(e)}")

        # Summary
        print(f"\nSummary:")
        print(
            f"  Found {sum(len(accounts) for accounts in accounts_by_tag.values())} tagged accounts across {len(accounts_by_tag)} different values"
        )
        print(f"  Found {len(untagged_accounts)} untagged accounts")

        return accounts_by_tag, untagged_accounts

    except org_client.exceptions.AccessDeniedException:
        print(
            "ERROR: Access denied. Ensure you have organizations:ListAccounts permission"
        )
        raise
    except Exception as e:
        print(f"ERROR: Failed to list accounts: {str(e)}")
        raise


def create_cost_category_from_tags(
    tag_key, accounts_by_tag, untagged_accounts, category_name=None
):
    """
    Create a Harness cost category with buckets based on tag values.

    Args:
        tag_key (str): The tag key used for categorization
        accounts_by_tag (dict): Dictionary mapping tag values to account lists
        untagged_accounts (list): List of accounts without the tag
        category_name (str, optional): Name for the cost category. Defaults to "Cost by {tag_key}"

    Returns:
        CostCategory: The created cost category object
    """
    if not category_name:
        category_name = f"Cost by {tag_key}"

    print(f"\nCreating cost category: '{category_name}'")

    # Create buckets for each tag value
    buckets = []

    for tag_value, accounts in sorted(accounts_by_tag.items()):
        print(f"  Creating bucket: '{tag_value}' with {len(accounts)} accounts")

        # Create CloudAccount objects for this bucket
        cloud_accounts = [
            CloudAccount(cloud="AWS", identifier=account["id"]) for account in accounts
        ]

        # Create a ViewCondition that matches these account IDs
        # The field ID for AWS account is 'awsUsageaccountid'
        account_ids = [account["id"] for account in accounts]
        condition = ViewCondition(
            field_id="awsUsageaccountid", operator=ViewOperator.IN, values=account_ids
        )

        # Create bucket with the condition as a rule
        bucket = Bucket(name=tag_value, rules=[[condition]])
        buckets.append(bucket)

    # Optionally create a bucket for untagged accounts
    if untagged_accounts:
        print(f"  Creating bucket: 'Untagged' with {len(untagged_accounts)} accounts")

        untagged_ids = [account["id"] for account in untagged_accounts]
        untagged_condition = ViewCondition(
            field_id="awsUsageaccountid", operator=ViewOperator.IN, values=untagged_ids
        )

        untagged_bucket = Bucket(name="Untagged", rules=[[untagged_condition]])
        buckets.append(untagged_bucket)

    # Create the cost category
    cost_category = CostCategory(name=category_name, buckets=buckets)

    print(f"\nCreating cost category in Harness with {len(buckets)} buckets...")
    response = cost_category.create()

    if response and response.status_code == 200:
        print(f"✓ Successfully created cost category '{category_name}'")
        print(f"  Response: {response.json()}")
    else:
        print(f"✗ Failed to create cost category")
        if response:
            print(f"  Status code: {response.status_code}")
            print(f"  Response: {response.text}")

    return cost_category


def main():
    parser = argparse.ArgumentParser(
        description="Create Harness cost categories from AWS Organizations account tags"
    )
    parser.add_argument(
        "--tag-key",
        required=True,
        help="The tag key to use for categorizing accounts (e.g., Environment, Department, CostCenter)",
    )
    parser.add_argument(
        "--category-name",
        help='Custom name for the cost category (defaults to "Cost by {tag-key}")',
    )
    parser.add_argument(
        "--include-untagged",
        action="store_true",
        default=True,
        help="Include a bucket for accounts without the specified tag (default: True)",
    )

    args = parser.parse_args()

    # Step 1: List AWS accounts and get their tags
    accounts_by_tag, untagged_accounts = list_aws_accounts_with_tags(args.tag_key)

    if not accounts_by_tag and not untagged_accounts:
        print("\nNo accounts found. Exiting.")
        return

    if not accounts_by_tag:
        print(f"\nNo accounts found with the '{args.tag_key}' tag. Exiting.")
        return

    # Step 2: Create cost category in Harness
    if not args.include_untagged:
        untagged_accounts = []

    cost_category = create_cost_category_from_tags(
        tag_key=args.tag_key,
        accounts_by_tag=accounts_by_tag,
        untagged_accounts=untagged_accounts,
        category_name=args.category_name,
    )

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
