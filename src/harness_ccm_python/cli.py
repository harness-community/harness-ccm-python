from argparse import ArgumentParser
from sys import exit

from generate_from_buckets import main as generate_main
from seed_testbed import main as seed_main
from teardown_testbed import main as teardown_main


def main(argv=None) -> int:
    parser = ArgumentParser(
        prog="harness-ccm-python",
        description="Harness CCM helpers for perspectives, budgets, and test beds.",
    )
    sub = parser.add_subparsers(dest="command")

    generate = sub.add_parser(
        "generate",
        help="create perspectives, budgets, and budget groups from a YAML config",
    )
    generate.add_argument("config", help="path to a YAML config")
    generate.add_argument(
        "--apply",
        action="store_true",
        help="create resources; without this flag the run only prints payloads",
    )
    generate.add_argument("--limit", type=int, help="maximum number of accounts")
    generate.add_argument("--manifest", help="write created ids to this JSON file")
    generate.add_argument(
        "--spreadsheet", help="budget workbook or csv (overrides spreadsheet.file)"
    )

    seed = sub.add_parser(
        "seed-testbed",
        help="seed a synthetic cost category",
    )
    seed.add_argument(
        "--shape",
        default="examples/testbed-shape.yaml",
        help="bucket names and account counts",
    )
    seed.add_argument(
        "--manifest",
        default="testbed-manifest.json",
        help="file that records the seeded cost category id",
    )

    teardown = sub.add_parser(
        "teardown-testbed",
        help="delete ids recorded in a test-bed manifest",
    )
    teardown.add_argument(
        "--manifest",
        default="testbed-manifest.json",
        help="manifest written by seed and generate",
    )

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2

    if args.command == "generate":
        argv = [args.config]
        if args.apply:
            argv.append("--apply")
        if args.limit is not None:
            argv.extend(["--limit", str(args.limit)])
        if args.manifest:
            argv.extend(["--manifest", args.manifest])
        if args.spreadsheet:
            argv.extend(["--spreadsheet", args.spreadsheet])
        return generate_main(argv)

    if args.command == "seed-testbed":
        return seed_main(["--shape", args.shape, "--manifest", args.manifest])

    if args.command == "teardown-testbed":
        return teardown_main(["--manifest", args.manifest])

    parser.print_help()
    return 2


if __name__ == "__main__":
    exit(main())
