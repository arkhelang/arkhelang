"""The arkhe command-line interface.

v0.1 surface: `arkhe validate <module.arkhe.yaml> [--json]`.
Exit codes: 0 valid, 1 invalid, 2 usage or internal error.
"""

from __future__ import annotations

import argparse
import sys

from .validate import validate_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arkhe", description="Arkhe: an ontology language for AI systems.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="Validate an Arkhe module.")
    p_val.add_argument("file", help="Path to a .arkhe.yaml module")
    p_val.add_argument("--json", action="store_true", help="Machine-readable output")

    args = parser.parse_args(argv)

    if args.command == "validate":
        try:
            result = validate_file(args.file)
        except OSError as exc:
            print(f"arkhe: cannot read {args.file}: {exc.strerror or exc}", file=sys.stderr)
            return 2
        if args.json:
            print(result.to_json())
        elif result.ok:
            print(f"{args.file}: valid")
        else:
            for finding in result.findings:
                print(f"{args.file}: [{finding.code}] {finding.path}: {finding.message}")
            print(f"{args.file}: invalid ({len(result.findings)} finding(s))")
        return 0 if result.ok else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
