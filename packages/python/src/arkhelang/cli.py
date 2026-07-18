"""The arkhe command-line interface.

v0.1 surface: `arkhe validate <module.arkhe.yaml> [--json]`.
Exit codes: 0 valid, 1 invalid, 2 usage or internal error.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .validate import validate_file

_EXAMPLES = """\
examples:
  arkhe validate model-risk.arkhe.yaml
      Validate a module; findings print as file:line:col: [code] path: message.

  arkhe validate model-risk.arkhe.yaml --json
      Machine-readable findings for editors and CI.

exit codes:
  0  the module is valid
  1  the module is invalid (findings printed)
  2  usage error or unreadable input

finding codes:
  yaml               the file is not parseable YAML (duplicate keys included)
  struct             structural: the module does not match the v0.1 schema
  key-ref, key-type  entity keys must be declared, required, non-state properties
  state-initial      a state's initial value must be among its declared values
  link-ref           link endpoints must be declared entities
  name-collision     traversal and property names must not collide
  action-ref         action targets and authorities must be declared
  effect-*           effect path, value, cardinality, and duplicate rules
  guard-*            CEL guard syntax, names, traversal depth, stdlib, macros

`akl` is installed as an alias of `arkhe`.
Documentation: https://arkhelang.org and https://github.com/arkhelang/arkhelang
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arkhe",
        description="Arkhe: an ontology language for AI systems.",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"arkhe {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="command")

    p_val = sub.add_parser(
        "validate", help="Validate an Arkhe module (.arkhe.yaml).",
        description="Validate a module structurally (schema) and semantically "
                    "(names, lifecycle rules, effects, CEL guards).")
    p_val.add_argument("file", help="Path to a .arkhe.yaml module")
    p_val.add_argument("--json", action="store_true", help="Machine-readable output")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = _build_parser()
    if not argv:
        parser.print_help()
        return 0
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
            for f in result.findings:
                where = f"{args.file}:{f.line}:{f.column}" if f.line else args.file
                print(f"{where}: [{f.code}] {f.path}: {f.message}")
            n = len(result.findings)
            print(f"{args.file}: invalid ({n} finding{'s' if n != 1 else ''})")
        return 0 if result.ok else 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
