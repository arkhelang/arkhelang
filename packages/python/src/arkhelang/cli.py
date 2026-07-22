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
    p_val.add_argument(
        "path", help="A .arkhe.yaml module, or a directory to scan recursively")
    p_val.add_argument("--json", action="store_true", help="Machine-readable output")

    p_con = sub.add_parser(
        "contracts", help="Generate tool contracts (the Arkhe IR) from a module.",
        description="Validate the module, then emit one JSON contract per "
                    "action and a read contract per entity.")
    p_con.add_argument("file", help="Path to a .arkhe.yaml module")
    p_con.add_argument(
        "--out", metavar="DIR",
        help="Write one <name>.contract.json per contract into DIR "
             "(default: print a single JSON object to stdout)")

    p_emit = sub.add_parser(
        "emit", help="Emit an artifact from a module via its contracts.",
        description="Validate, generate contracts, then emit for a target. "
                    "Targets: lib (a Python module of guarded functions) and "
                    "okf (an Open Knowledge Format bundle of markdown concept "
                    "files, one per entity, link, action, role, and invariant).")
    p_emit.add_argument("file", help="Path to a .arkhe.yaml module")
    p_emit.add_argument("--target", choices=["lib", "okf"], default="lib",
                        help="Emitter target (default: lib)")
    p_emit.add_argument(
        "--out", metavar="PATH",
        help="Output path: a FILE for lib (default: stdout), a DIR for okf "
             "(default: print each file with a header to stdout)")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = _build_parser()
    if not argv:
        parser.print_help()
        return 0
    args = parser.parse_args(argv)

    if args.command == "validate":
        return _cmd_validate(args)

    if args.command == "contracts":
        return _cmd_contracts(args)

    if args.command == "emit":
        return _cmd_emit(args)

    parser.print_help()
    return 2


def _cmd_emit(args) -> int:
    from pathlib import Path

    import yaml

    from .contracts import generate

    try:
        result = validate_file(args.file)
    except OSError as exc:
        print(f"arkhe: cannot read {args.file}: {exc.strerror or exc}", file=sys.stderr)
        return 2
    if not result.ok:
        _print_findings(args.file, result)
        print("arkhe: refusing to emit from an invalid module", file=sys.stderr)
        return 1
    doc = yaml.safe_load(Path(args.file).read_text())
    contracts = generate(doc)

    if args.target == "okf":
        return _emit_okf(doc, contracts, args.out)
    return _emit_lib(doc, contracts, args.out)


def _emit_lib(doc, contracts, out) -> int:
    from pathlib import Path

    from .emitters import pylib

    try:
        source = pylib.emit(doc, contracts)
    except pylib.EmitError as exc:
        print(f"arkhe: cannot emit: {exc}", file=sys.stderr)
        return 1
    if out:
        try:
            Path(out).write_text(source)
        except OSError as exc:
            print(f"arkhe: cannot write {out}: {exc.strerror or exc}",
                  file=sys.stderr)
            return 2
        print(f"emitted {out}")
    else:
        print(source, end="")
    return 0


def _emit_okf(doc, contracts, out) -> int:
    from pathlib import Path

    from .emitters import okf

    try:
        bundle = okf.emit(doc, contracts)
    except okf.EmitError as exc:
        print(f"arkhe: cannot emit: {exc}", file=sys.stderr)
        return 1

    if not out:
        for rel, content in sorted(bundle.items()):
            print(f"==> {rel} <==")
            print(content)
        return 0

    out_dir = Path(out)
    manifest_path = out_dir / okf.MANIFEST_NAME

    # Prune only what a previous emit recorded owning. Without a manifest the
    # emitter has no record of what it may delete, so an out directory that
    # already holds markdown is refused rather than swept.
    if out_dir.exists() and not manifest_path.exists() and any(
            out_dir.rglob("*.md")):
        print(f"arkhe: cannot emit: {out_dir} already contains markdown files "
              f"but no {okf.MANIFEST_NAME}; point --out at an empty directory "
              "or remove those files yourself", file=sys.stderr)
        return 1

    try:
        previous = []
        if manifest_path.exists():
            previous = [line for line in manifest_path.read_text().splitlines()
                        if line]
        for rel in sorted(set(previous) - set(bundle)):
            stale = out_dir / rel
            if stale.is_file():
                stale.unlink()
        for rel, content in sorted(bundle.items()):
            path = out_dir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text("\n".join(sorted(bundle)) + "\n")
        _prune_empty_dirs(out_dir)
    except OSError as exc:
        print(f"arkhe: cannot write to {out}: {exc.strerror or exc}",
              file=sys.stderr)
        return 2
    print(f"{len(bundle)} files written to {out_dir}")
    return 0


def _prune_empty_dirs(root) -> None:
    """Remove directories left empty after a prune, deepest first."""
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def _use_colour() -> bool:
    import os
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


class _C:
    """ANSI colours, active only on a TTY with NO_COLOR unset."""

    def __init__(self):
        on = _use_colour()
        self.red = "\033[31m" if on else ""
        self.green = "\033[32m" if on else ""
        self.yellow = "\033[33m" if on else ""
        self.bold = "\033[1m" if on else ""
        self.dim = "\033[2m" if on else ""
        self.off = "\033[0m" if on else ""


def _source_excerpt(path, finding, c: _C) -> list[str]:
    """The offending source line with a caret under the column."""
    if finding.line is None:
        return []
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
        text = lines[finding.line - 1]
    except (OSError, IndexError, UnicodeDecodeError):
        return []
    gutter = f"{finding.line:>5} | "
    caret_pad = " " * (len(gutter) + (finding.column or 1) - 1)
    return [
        f"  {c.dim}{gutter}{c.off}{text}",
        f"  {caret_pad}{c.red}^{c.off}",
    ]


def _print_findings(path, result) -> None:
    c = _C()
    for f in result.findings:
        where = f"{path}:{f.line}:{f.column}" if f.line else str(path)
        print(f"  {c.bold}{where}{c.off}: {c.yellow}[{f.code}]{c.off} "
              f"{c.dim}{f.path}{c.off}: {f.message}")
        for line in _source_excerpt(path, f, c):
            print(line)


def _cmd_validate(args) -> int:
    import json
    from pathlib import Path

    target = Path(args.path)
    if target.is_dir():
        files = sorted(target.rglob("*.arkhe.yaml"))
        if not files:
            print(f"arkhe: no .arkhe.yaml modules under {target}", file=sys.stderr)
            return 2
    else:
        files = [target]

    print(f"arkhe {__version__} validate")
    print()
    results = {}
    for path in files:
        try:
            results[path] = validate_file(path)
        except OSError as exc:
            print(f"arkhe: cannot read {path}: {exc.strerror or exc}", file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps({
            str(p): json.loads(r.to_json()) for p, r in results.items()}, indent=2))
        return 0 if all(r.ok for r in results.values()) else 1

    for path, result in results.items():
        if not result.ok:
            _print_findings(path, result)
    if any(not r.ok for r in results.values()):
        print()

    c = _C()
    width = max(len(str(p)) for p in results)
    print(f"  {'module':<{width}}  findings  status")
    for path, result in results.items():
        n = len(result.findings)
        status = (f"{c.green}valid{c.off}" if result.ok
                  else f"{c.red}INVALID{c.off}")
        print(f"  {str(path):<{width}}  {n:>8}  {status}")
    valid = sum(1 for r in results.values() if r.ok)
    invalid = len(results) - valid
    print()
    print(f"  {len(results)} module{'s' if len(results) != 1 else ''}: "
          f"{valid} valid, {invalid} invalid")
    return 0 if invalid == 0 else 1


def _cmd_contracts(args) -> int:
    import json
    from pathlib import Path

    import yaml

    from .contracts import generate

    try:
        result = validate_file(args.file)
    except OSError as exc:
        print(f"arkhe: cannot read {args.file}: {exc.strerror or exc}", file=sys.stderr)
        return 2
    if not result.ok:
        for f in result.findings:
            where = f"{args.file}:{f.line}:{f.column}" if f.line else args.file
            print(f"{where}: [{f.code}] {f.path}: {f.message}", file=sys.stderr)
        print("arkhe: refusing to generate contracts from an invalid module",
              file=sys.stderr)
        return 1
    doc = yaml.safe_load(Path(args.file).read_text())
    all_contracts = generate(doc)
    if args.out:
        try:
            out_dir = Path(args.out)
            out_dir.mkdir(parents=True, exist_ok=True)
            for stale in out_dir.glob("*.contract.json"):
                if stale.name.replace(".contract.json", "") not in all_contracts:
                    stale.unlink()
            for name, contract in all_contracts.items():
                (out_dir / f"{name}.contract.json").write_text(
                    json.dumps(contract, indent=2) + "\n")
        except OSError as exc:
            print(f"arkhe: cannot write to {args.out}: {exc.strerror or exc}",
                  file=sys.stderr)
            return 2
        print(f"{len(all_contracts)} contracts written to {out_dir}")
    else:
        print(json.dumps(all_contracts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
