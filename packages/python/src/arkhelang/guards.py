"""CEL guard analysis for the Arkhe v0.1 subset.

Two layers: syntax (celpy compile) and a structural walk of the parse tree
that resolves member paths against the module's entities and links, enforces
the two-hop traversal bound (ADR 0005), and restricts function calls to the
declared stdlib plus a small set of CEL built-ins. Bracket access with a
string literal (x["name"]) is treated identically to dot access; bracket
access with a non-literal index is rejected as unanalyzable in v0.1.

A variable bound through a traversal sees the far entity's properties and
the traversed link's own properties (ADR 0006, provisional). A variable
bound over an unanalyzable base (for example the result of map or filter)
is opaque: its uses are accepted without further checking.

Scope note: this checks names, traversals, and calls. It does not type-check
operators (comparing a date to a bool passes this layer); full expression
typing is a later conformance level.
"""

from __future__ import annotations

from dataclasses import dataclass

import celpy
from lark import Token, Tree

from .model import Module

STDLIB = {"months_since", "days_since", "today"}
GLOBAL_FUNCTIONS = STDLIB | {"size", "has", "int", "string", "bool", "double"}
MACROS = {"all", "exists", "exists_one", "filter", "map"}
METHODS = MACROS | {"size", "contains", "startsWith", "endsWith", "matches"}

_ENV = celpy.Environment()

_ENTITY = "entity"
_PARAMS = "params"
_OPAQUE = "opaque"


@dataclass
class GuardIssue:
    code: str
    message: str


@dataclass
class GuardReport:
    issues: list[GuardIssue]
    stdlib_used: set[str]
    traversals: list[dict]

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass
class _Binding:
    kind: str                 # _ENTITY, _PARAMS, or _OPAQUE
    entity: str | None = None
    via_link: object = None   # model.Link or None
    depth: int = 0
    is_many: bool = False


def _hop_is_many(link, traversal_name: str) -> bool:
    """Whether traversing `traversal_name` yields a collection."""
    forward = traversal_name == link.name
    if link.cardinality == "one_to_one":
        return False
    if link.cardinality == "many_to_one":
        return not forward
    if link.cardinality == "one_to_many":
        return forward
    return True  # many_to_many


class _Scope:
    def __init__(self, bindings: dict[str, _Binding]):
        self.bindings = dict(bindings)


def _token(node) -> str | None:
    if isinstance(node, Token):
        return str(node)
    if isinstance(node, Tree) and len(node.children) == 1:
        return _token(node.children[0])
    return None


def _string_literal(node) -> str | None:
    """The unquoted value if node is a string literal, else None."""
    node_ = node
    while isinstance(node_, Tree) and len(node_.children) == 1:
        if node_.data == "literal":
            break
        node_ = node_.children[0]
    if isinstance(node_, Tree) and node_.data == "literal":
        tok = _token(node_)
        if tok and len(tok) >= 2 and tok[0] in "'\"" and tok[-1] == tok[0]:
            return tok[1:-1]
    return None


def _unwrap(node):
    """Descend through single-child wrapper nodes to the meaningful tree."""
    while (
        isinstance(node, Tree)
        and node.data not in (
            "member_dot", "member_dot_arg", "member_index", "ident", "ident_arg", "literal")
        and len(node.children) == 1
    ):
        node = node.children[0]
    return node


def analyze(expression: str, module: Module, root_var: str, root_entity: str,
            params: dict | None = None) -> GuardReport:
    issues: list[GuardIssue] = []
    stdlib_used: set[str] = set()
    traversals: list[dict] = []

    try:
        tree = _ENV.compile(expression)
    except Exception as exc:  # celpy raises CELParseError subclasses
        return GuardReport(
            issues=[GuardIssue("guard-syntax", f"does not parse as CEL: {exc}")],
            stdlib_used=set(), traversals=[],
        )

    roots: dict[str, _Binding] = {root_var: _Binding(_ENTITY, root_entity)}
    if params is not None:
        roots["params"] = _Binding(_PARAMS)

    def resolve_path(path: list[str], scope: _Scope) -> _Binding | None:
        head, rest = path[0], path[1:]
        binding = scope.bindings.get(head)
        if binding is None:
            issues.append(GuardIssue(
                "guard-unknown-name",
                f"'{head}' is not a known root or bound variable"))
            return None
        if binding.kind == _OPAQUE:
            return _Binding(_OPAQUE)  # accepted without further checks
        if binding.kind == _PARAMS:
            if len(rest) != 1 or rest[0] not in (params or {}):
                issues.append(GuardIssue(
                    "guard-unknown-name",
                    f"'{'.'.join(path)}' is not a declared parameter"))
                return None
            return _Binding(_OPAQUE)
        current, via_link, depth = binding.entity, binding.via_link, binding.depth
        is_many = binding.is_many
        for i, seg in enumerate(rest):
            if current is None:
                issues.append(GuardIssue(
                    "guard-unknown-name",
                    f"'{seg}' follows a scalar property in '{'.'.join(path)}'"))
                return None
            entity = module.entities.get(current)
            info = module.traversal_info(current)
            link_props = getattr(via_link, "properties", None) or {}
            if entity and (seg in entity.properties or seg in link_props):
                current, via_link = None, None  # terminal scalar
            elif seg in info:
                depth += 1
                far, link = info[seg]
                hop_many = _hop_is_many(link, seg)
                is_many = is_many or hop_many
                traversals.append({
                    "path": ".".join([head] + rest[: i + 1]),
                    "link": link.name,
                    "direction": "forward" if seg == link.name else "reverse",
                    "to": far,
                    "many": hop_many,
                })
                if depth > 2:
                    issues.append(GuardIssue(
                        "guard-traversal-depth",
                        f"traversal '{'.'.join(path)}' exceeds the two-hop bound (ADR 0005)"))
                    return None
                current, via_link = far, link
            else:
                issues.append(GuardIssue(
                    "guard-unknown-name",
                    f"'{seg}' is neither a property nor a traversal of {current}"))
                return None
        return _Binding(_ENTITY, current, via_link, depth, is_many)

    def collect_path(node) -> list[str] | None:
        """member_dot / string-literal member_index chains -> dotted path."""
        node = _unwrap(node)
        if isinstance(node, Tree) and node.data == "member_dot":
            base = collect_path(node.children[0])
            name = _token(node.children[1])
            if base is None or name is None:
                return None
            return base + [name]
        if isinstance(node, Tree) and node.data == "member_index":
            base = collect_path(node.children[0])
            name = _string_literal(node.children[1])
            if base is None:
                return None
            if name is None:
                issues.append(GuardIssue(
                    "guard-index",
                    "bracket access with a non-literal index is not analyzable in v0.1"))
                return None
            return base + [name]
        if isinstance(node, Tree) and node.data == "ident":
            name = _token(node)
            return [name] if name else None
        return None

    def walk(node, scope: _Scope):
        if not isinstance(node, Tree):
            return
        if node.data == "ident_arg":
            fname = _token(node.children[0])
            if fname:
                if fname in STDLIB:
                    stdlib_used.add(fname)
                elif fname not in GLOBAL_FUNCTIONS:
                    issues.append(GuardIssue(
                        "guard-unknown-function",
                        f"'{fname}()' is not in the v0.1 stdlib or allowed built-ins"))
            for child in node.children[1:]:
                walk(child, scope)
            return
        if node.data == "member_dot_arg":
            base_node, name_node = node.children[0], node.children[1]
            mname = _token(name_node)
            if mname and mname not in METHODS:
                issues.append(GuardIssue(
                    "guard-unknown-function", f"'.{mname}()' is not an allowed method or macro"))
            if mname in MACROS:
                args = node.children[2] if len(node.children) > 2 else None
                arg_children = list(args.children) if isinstance(args, Tree) else []
                if len(arg_children) != 2:
                    issues.append(GuardIssue(
                        "guard-macro-arity",
                        f"'.{mname}(var, expr)' takes exactly two arguments"))
                    for child in node.children:
                        walk(child, scope)
                    return
                bound = _token(arg_children[0])
                path = collect_path(base_node)
                if path is not None:
                    resolved = resolve_path(path, scope)
                    if (resolved is not None and resolved.kind == _ENTITY
                            and not resolved.is_many):
                        issues.append(GuardIssue(
                            "guard-macro-base",
                            f"'.{mname}()' requires a collection; "
                            f"'{'.'.join(path)}' yields a single value"))
                else:
                    # Base is itself a macro/method result (or unanalyzable):
                    # walk it for its own issues, then bind opaquely.
                    walk(base_node, scope)
                    resolved = _Binding(_OPAQUE)
                inner = _Scope(scope.bindings)
                # On failed resolution bind opaquely too, so one root cause
                # does not cascade into unknown-variable noise. The bound
                # variable is one ELEMENT of the collection, never a
                # collection itself.
                if resolved and resolved.kind == _ENTITY:
                    element = _Binding(_ENTITY, resolved.entity,
                                       resolved.via_link, resolved.depth, False)
                else:
                    element = _Binding(_OPAQUE)
                inner.bindings[bound or "_"] = element
                walk(arg_children[1], inner)
                return
            for child in node.children:
                walk(child, scope)
            return
        if node.data in ("member_dot", "member_index"):
            path = collect_path(node)
            if path:
                resolve_path(path, scope)
            elif node.data == "member_index":
                # collect_path already recorded guard-index for non-literal;
                # still walk the base for its own issues.
                walk(node.children[0], scope)
            return
        if node.data == "ident":
            name = _token(node)
            if name and name not in scope.bindings:
                # Function names are only legal in call position (ident_arg).
                issues.append(GuardIssue(
                    "guard-unknown-name", f"'{name}' is not a known root or bound variable"))
            return
        for child in node.children:
            walk(child, scope)

    walk(tree, _Scope(roots))
    deduped: list[GuardIssue] = []
    seen: set[tuple[str, str]] = set()
    for issue in issues:
        key = (issue.code, issue.message)
        if key not in seen:
            seen.add(key)
            deduped.append(issue)
    return GuardReport(issues=deduped, stdlib_used=stdlib_used, traversals=traversals)
