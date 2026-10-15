# harness-ccm-python

all examples are for python >= 3.8

all code uses the following for configuration:

- `HARNESS_URL`: url for your harness instances, usually `app.harness.io` or `app3.harness.io`
- `HARNESS_ACCOUNT_ID`: account id
- `HARNESS_PLATFORM_API_KEY`: api token

## costcategories

helper classes for dealing with cost categories

## perspectives

helper classes for dealing with perspectives

## example_accounts_csv.py

example python for taking a csv of cloud accounts and "buckets" they are in and creating a cost category from this information

input:
```
cloudType,AccountID,CategoryName
aws,000000000001,bucket1
aws,000000000002,bucket2
aws,000000000003,bucket3
azure,0000-000-000-0001,bucket1
azure,0000-000-000-0002,bucket2
azure,0000-000-000-0003,bucket3
gcp,proj-0001,bucket1
gcp,proj-0002,bucket2
gcp,proj-0003,bucket3
```

the csv should have a header row, where all columns after the first two are the names of the cost categories you want to create

if you want to created shared buckets, name the bucket starting with `shared_<TYPE>_` where `<TYPE>` is one of `EQUAL` or `PROPORTIONAL`, example:

```
aws,000000000003,shared_EQUAL_Shared Services E
aws,000000000004,shared_EQUAL_Shared Services E
aws,000000000005,shared_PROPORTIONAL_Shared Services F
```

output:

a cost category with three buckets [`bucket1`, `bucket2`, `bucket3`] with an aws, azure, and gcp account in each 

## example_per_bucket.py

create a perspective for every bucket in a cost category

```
python example_per_bucket.py "A Folder" "A Cost Category"
```

if the folder dosnt exist, it will be created

## generate_from_buckets.py

Install with `pip install -e .` (preferred) or `pip install -r requirements.txt`. Dependencies are declared in `pyproject.toml`; `requirements.txt` mirrors them for pip-only installs. The command uses the same `HARNESS_URL`, `HARNESS_ACCOUNT_ID`, and `HARNESS_PLATFORM_API_KEY` variables as the other examples.

The installed CLI exposes the same flows:

```
harness-ccm-python generate examples/account-budgets.yaml
harness-ccm-python generate examples/testbed.yaml --apply --limit 1
harness-ccm-python seed-testbed
harness-ccm-python teardown-testbed
```

Direct scripts (`python generate_from_buckets.py ...`, `python seed_testbed.py`, `python teardown_testbed.py`) remain supported.

Creates one perspective and one budget for each account in the selected cost-category buckets, then one budget group whose children are the budgets for that bucket.

A bucket can hold one account or many. Accounts are the values on an `awsUsageaccountid`, `azureSubscriptionGuid`, or `gcpProjectId` condition. The default `perspective.rule_mode` is `category_and_account`: the perspective requires the cost category bucket and that one account value. Sibling conditions from the bucket rule are not copied, because the category already applied them. `account` copies only the account condition. `account_with_sibling_conditions` also copies the other AND conditions on that rule.

`on_exists: update` rewrites an existing perspective's rules and keeps its name and folder. `skip` leaves the existing perspective unchanged.

Name templates can use `{category}`, `{bucket}`, `{folder}`, `{account_name}`, `{account_label}`, `{account_id}`, and, for budgets, `{perspective_name}`.

```
python generate_from_buckets.py examples/account-budgets.yaml
python generate_from_buckets.py examples/account-budgets.yaml --apply --limit 1
```

Without `--apply` the command prints the payloads and does not create anything. Writes happen only when `--apply` is passed.

`behavior.on_exists` is `skip`, `fail`, or `update`. Folders and perspectives are reused in update mode. An annual budget and its budget group are named with the fiscal year from the first create, such as `Platform Production - FY27`. Matching budgets are updated before their budget group. Harness does not allow a budget's start time to change, so the next fiscal year creates ` - FY28` budgets and a group while the prior year's resources and history remain intact.

Each account perspective gets its own budget, and the budgets in a bucket roll up into that bucket's budget group.

Set `amount`, `period` (`MONTHLY` or `YEARLY`; `ANNUAL` is accepted), and, for an annual budget, `monthly_breakdown`. `monthly_breakdown: true` splits `amount` across the 12 months that start at `budget.start`, or uses `monthly_amounts` when that list of 12 values is set. `start` is `month_start`, `year_start`, a `YYYY-MM-DD` date, or epoch milliseconds.

A bucket can share one budget across its accounts with `buckets.budgets.<bucket name>`. When each account has its own budget, list them under that bucket's `accounts` map. The key is the account id from the cost-category label, such as `100000000001`, or the full label. Each entry sets its own `amount`, and can override `period` or `monthly_breakdown`. Accounts in that bucket that are not listed are skipped, so no view or budget is created for them. The budget group contains only the account budgets that were created, and its amount is their sum.

Amounts and alerts can also come from an `.xlsx` workbook or a `.csv` file with the same headers. There is no need to convert a workbook to csv first. Pass `--spreadsheet path` to override `spreadsheet.file`; the configured file is not opened when that flag is set. A relative path in the YAML is resolved from the YAML file. An absolute path or a `~/...` path is used as given, both in the YAML and with `--spreadsheet`. A relative `--spreadsheet` path is resolved from the current directory.

```yaml
spreadsheet:
  file: budgets.xlsx
  sheet: Budgets          # xlsx only; omit to use the first sheet
  key: account            # account or bucket
  only: true              # rows are the allow-list
  columns:
    account_id: Account ID
    account_name: Account Name
    folder: Folder
    bucket: Cost Bucket
    amount: Annual Budget # optional when months is configured
    months: 2026-04       # expands through 2027-03 and sets the fiscal start
    recipients: Recipients
    alerts:
      - header: Alert 80
        percentage: 80
        based_on: ACTUAL_COST
      - header: Alert 100
        percentage: 100
        based_on: ACTUAL_COST
```

`key: account` matches the Account ID column. Keep Account ID and Account Name in separate columns; a combined cell such as `Testing (012345678901)` is not parsed. Account Name is optional. It is the default perspective and budget name; when absent, the name is derived from the cost-category account label. When it differs from that label, the run prints a warning and still matches on account id. Format Account ID as text so a value such as `012345678901` keeps its leading zeroes. A numeric cell of 12 digits or fewer is left-padded to 12 digits.

The optional Folder column is the default perspective-folder and budget-group name. A blank Folder cell prints a warning and falls back to the cost-bucket name. Budget groups remain one per cost bucket, so every account row in a bucket must use the same Folder value. Templates can use `{folder}`, `{account_name}`, `{bucket}`, `{category}`, `{account_id}`, and `{account_label}`.

`key: bucket` uses the Cost Bucket column and applies that row to every account in the bucket. `amount` replaces the YAML amount.

For custom monthly variance, set `columns.months` to the first `YYYY-MM` header. For example, `months: 2026-04` reads the twelve cells from `2026-04` through `2027-03`, sets an annual budget starting April 1, and sums those cells for the annual amount. The cells may all differ. `amount` is optional in this mode; when mapped, it is only a cross-check and a difference greater than `$0.02` prints a warning. A list of 12 headers remains supported for spreadsheets whose month headers are not `YYYY-MM`.

Columns that are not in the mapping are ignored, including blank or repeated headers. A mapped header that appears more than once is an error that names the column letters; rename or remove the extra column. A row with no value in the key column, such as a `Total` row, is skipped and reported.

A threshold cell is enabled by `Y`, `yes`, or `true`. `N`, `no`, `false`, and a blank cell leave it off. `recipients` is one comma-separated list and is attached to every enabled threshold on that row. Another threshold is another `alerts` entry and another column, for example `header: Alert 120` with `percentage: 120`. `only: true` skips accounts or buckets that have no row. `only: false` overlays matching rows onto the YAML defaults. A row whose account id or bucket is not in the selected cost category is reported and skipped. Duplicate account ids, or duplicate bucket names in bucket mode, are an error.

A file with one `cost_category` uses its `budget` block as the default. A file can instead list `categories`, and each entry supplies its own `budget`. See `examples/category-budgets.yaml`.

Accounts in one budget group must share `type`, `period`, `start`, monthly-breakdown mode, and Folder. Amounts can differ. `cascade` is `NO_CASCADE`, `EQUAL`, or `PROPORTIONAL`. `NO_CASCADE` leaves each account amount as it was created. `PREVIOUS_PERIOD_SPEND` does not send a dollar amount. `SPECIFIED_AMOUNT` requires an amount from YAML, a total column, or month columns.

For the next fiscal year, replace the spreadsheet month headers and values, change `columns.months` to the new first month, and set `behavior.on_exists: update`. Dry-run first, then use `--apply`. Same-fiscal-year values update the `FY27` budgets and group in place. A changed fiscal start creates the `FY28` budgets and group, preserving the previous fiscal year. Keep Account Name and Folder unchanged when you want to reuse the same perspective and folder; changing either is treated as a naming change, not an implicit rename.

The published budget API limits `name` to 1..80 characters. Names are sent as rendered. A rejected create is printed and, when a manifest path is set, stored there with the API error. Names are not shortened.

`example_per_bucket.py` is still the path that creates one perspective per bucket.

## test bed

Seeds a synthetic cost category into whichever account `HARNESS_URL`, `HARNESS_ACCOUNT_ID`, and `HARNESS_PLATFORM_API_KEY` point at. The category name is `AccountBudgets-testbed`. There are 3 buckets and 5 synthetic accounts. There is no cost-data check.

```
python seed_testbed.py
python generate_from_buckets.py examples/testbed.yaml
python generate_from_buckets.py examples/testbed.yaml --apply
python teardown_testbed.py
```

`examples/testbed.yaml` uses Account Name for perspectives and budgets, and Folder for perspective folders and budget groups. `examples/testbed-budgets.csv` is the allow-list: the twelve columns beginning at `2026-04` become each account's annual budget and preserve any month-to-month variance. `FY27 Total` is a cross-check. Dollar values such as `$ 4,000.00` are accepted. Mapping the same Alert column twice (for `ACTUAL_COST` and `FORECASTED_COST`) creates one threshold per mapping when the cell is enabled. The dry run ends with created and updated counts. Only spreadsheet account IDs that exist in `AccountBudgets-testbed` are included.

`seed_testbed.py` writes the cost category id to `testbed-manifest.json`. An apply with `examples/testbed.yaml` adds the folders, perspectives, budgets, and budget groups it created. `teardown_testbed.py` deletes only those ids, in order: budget groups, budgets, perspectives, folders, then the seeded cost category.
