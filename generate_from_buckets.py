from argparse import ArgumentParser
from sys import exit

from provision.config import load_runs
from provision.generate import generate, load_targets


def main(argv=None) -> int:
    parser = ArgumentParser(
        description=(
            "Create one perspective and budget per account in the selected "
            "cost-category buckets, then one budget group per bucket."
        )
    )
    parser.add_argument("config", help="path to a YAML config")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="create resources; without this flag the run only prints payloads",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="maximum number of accounts to process",
    )
    parser.add_argument(
        "--manifest",
        help="write created ids to this JSON file (overrides behavior.manifest)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print every would-create line, request payload, and skipped item",
    )
    parser.add_argument(
        "--spreadsheet",
        help="budget workbook or csv (overrides spreadsheet.file)",
    )
    args = parser.parse_args(argv)

    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be a positive integer")

    try:
        runs = load_runs(args.config, args.spreadsheet)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    failed = False
    try:
        for config in runs:
            manifest = args.manifest or config["behavior"].get("manifest")
            loaded = load_targets(config["cost_category"])
            result = generate(
                config,
                loaded["targets"],
                apply=args.apply,
                limit=args.limit,
                manifest_path=manifest,
                category=loaded,
                verbose=args.verbose,
            )
            failed = failed or bool(result["errors"])
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    return 1 if failed else 0


if __name__ == "__main__":
    exit(main())
