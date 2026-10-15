# AWS Organizations Tag-Based Cost Categories Example

This example demonstrates how to create Harness cost categories based on AWS Organizations account tags.

## Overview

The `example_aws_org_tags.py` script performs the following:

1. **Call AWS Organizations API** using boto3 to list all active accounts
2. **Retrieve tags** for each account
3. **Organize accounts** by a specific tag key (e.g., "Environment", "Department", "CostCenter")
4. **Create Harness cost categories** with buckets for each unique tag value

## Key Features

- **Paginated account listing** - handles organizations with many accounts
- **Tag retrieval** - gets tags for each account and extracts the specified tag key
- **Active accounts only** - skips suspended/closed accounts
- **Untagged bucket** - optionally creates a bucket for accounts without the tag
- **Error handling** - gracefully handles missing permissions or API errors
- **Command-line interface** - easy to use with different tag keys

## Prerequisites

### 1. AWS Credentials

You need AWS credentials configured with Organizations permissions:
- `organizations:ListAccounts`
- `organizations:ListTagsForResource`

Configure credentials using one of these methods:
- AWS CLI: `aws configure`
- Environment variables: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- IAM role (if running on EC2/ECS/Lambda)

### 2. Python Packages

Install boto3:
```bash
pip install boto3
```

### 3. Harness Environment Variables

Set the following environment variables:
```bash
export HARNESS_URL="https://app.harness.io"
export HARNESS_ACCOUNT_ID="your-account-id"
export HARNESS_PLATFORM_API_KEY="your-api-key"
```

## Usage Examples

### Create cost category based on Environment tags
```bash
python example_aws_org_tags.py --tag-key Environment
```

This will:
- List all AWS accounts in your organization
- Group them by their "Environment" tag value
- Create a cost category named "Cost by Environment" with buckets like "Production", "Development", "Staging", etc.

### Create cost category based on Department tags with custom name
```bash
python example_aws_org_tags.py --tag-key Department --category-name "Department Cost Allocation"
```

### Create cost category based on CostCenter tags
```bash
python example_aws_org_tags.py --tag-key CostCenter
```

## How It Works

1. **AWS Organizations API Call**: The script uses `boto3.client('organizations')` to list all accounts and their tags
2. **Tag Organization**: Accounts are grouped into a dictionary based on their tag values
3. **Bucket Creation**: Each unique tag value becomes a bucket in the cost category
4. **Harness API Call**: The cost category is created in Harness using the existing `CostCategory` class

## Example Output

```
Fetching AWS accounts from Organizations API...
  ✓ Production Account 1 (123456789012) → Environment=Production
  ✓ Production Account 2 (234567890123) → Environment=Production
  ✓ Dev Account (345678901234) → Environment=Development
  ⚠ Legacy Account (456789012345) → No 'Environment' tag found

Summary:
  Found 3 tagged accounts across 2 different values
  Found 1 untagged accounts

Creating cost category: 'Cost by Environment'
  Creating bucket: 'Development' with 1 accounts
  Creating bucket: 'Production' with 2 accounts
  Creating bucket: 'Untagged' with 1 accounts

Creating cost category in Harness with 3 buckets...
✓ Successfully created cost category 'Cost by Environment'

Done!
```

## Architecture

The script follows the existing patterns in the codebase, using:
- `CostCategory` - main cost category object
- `Bucket` - represents each tag value bucket
- `ViewCondition` - filters for AWS account IDs
- `CloudAccount` - AWS account representation
- `ViewOperator.IN` - matches accounts in the bucket

## Common Tag Keys

Popular tag keys to use with this script:
- `Environment` - Production, Development, Staging, etc.
- `Department` - Engineering, Finance, Marketing, etc.
- `CostCenter` - Cost center codes for chargeback
- `Project` - Project names or codes
- `Owner` - Team or individual owners
- `Application` - Application names
