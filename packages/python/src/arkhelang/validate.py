"""The Arkhe validator: structural schema check, then semantic checks.

Findings carry a stable code, a document path, and a message. Structural
findings use code 'struct'; semantic codes are named for their rule.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from importlib import resources
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from . import guards, model


@dataclass
class Finding:
    code: str
    path: str
    message: str
    line: int | None = None
    column: int | None = None


@dataclass
class Result:
    findings: list[Finding]

    @property
    def ok(self) -> bool:
        return not self.findings

    def to_json(self) -> str:
        return json.dumps(
            {"ok": self.ok, "findings": [asdict(f) for f in self.findings]}, indent=2
        )


def _line_index(text: str) -> dict[tuple, tuple[int, int]]:
    """Map document paths to 1-based (line, column) source positions."""
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError:
        return {}
    index: dict[tuple, tuple[int, int]] = {}

    def walk(node, path: tuple):
        index[path] = (node.start_mark.line + 1, node.start_mark.column + 1)
        if isinstance(node, yaml.MappingNode):
            for key_node, value_node in node.value:
                walk(value_node, path + (str(key_node.value),))
                # the key's own mark reads better for "missing field" findings
                index[path + (str(key_node.value),)] = (
                    key_node.start_mark.line + 1, key_node.start_mark.column + 1)
        elif isinstance(node, yaml.SequenceNode):
            for i, item in enumerate(node.value):
                walk(item, path + (str(i),))

    if root is not None:
        walk(root, ())
    return index


def _locate(findings: list[Finding], index: dict) -> None:
    """Attach the closest known source position to each finding."""
    if not index:
        return
    for f in findings:
        if f.path in ("(root)", "(file)"):
            f.line, f.column = index.get((), (None, None))
            continue
        segs = tuple(f.path.split("/"))
        while segs and segs not in index:
            segs = segs[:-1]
        if segs in index:
            f.line, f.column = index[segs]


def _schema() -> dict:
    with resources.files("arkhelang").joinpath("arkhe-0.1.schema.json").open() as fh:
        return json.load(fh)


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys instead of merging them."""


def _no_duplicates(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise yaml.YAMLError(
                f"duplicate key '{key}' at line {key_node.start_mark.line + 1}")
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates)


def validate_file(path: str | Path) -> Result:
    try:
        text = Path(path).read_text()
        doc = yaml.load(text, Loader=_StrictLoader)
    except yaml.YAMLError as exc:
        return Result([Finding("yaml", "(file)", f"not parseable as YAML: {exc}")])
    except UnicodeDecodeError as exc:
        return Result([Finding("yaml", "(file)", f"not readable as UTF-8 text: {exc}")])
    if not isinstance(doc, dict):
        return Result([Finding("yaml", "(file)", "document is not a mapping")])
    result = validate(doc)
    _locate(result.findings, _line_index(text))
    return result


def _clarify(err) -> str:
    """Reword the clumsiest jsonschema messages; pass others through."""
    if err.validator == "required":
        missing = ", ".join(f"'{p}'" for p in err.validator_value if p not in err.instance)
        return f"missing required field {missing}"
    if err.validator == "additionalProperties":
        known = set(err.schema.get("properties", {}))
        unknown = [k for k in err.instance if k not in known]
        if unknown:
            return "unknown field " + ", ".join(f"'{k}'" for k in unknown)
    if err.validator == "const" and list(err.absolute_path)[-1:] == ["arkhe"]:
        return f"this validator implements Arkhe spec '{err.validator_value}'; " \
               f"the module declares '{err.instance}'"
    if err.validator == "enum":
        allowed = ", ".join(map(str, err.validator_value))
        return f"'{err.instance}' is not one of: {allowed}"
    return err.message


def validate(doc: dict) -> Result:
    findings: list[Finding] = []

    validator = Draft202012Validator(_schema())
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        findings.append(Finding(
            "struct", "/".join(map(str, err.absolute_path)) or "(root)", _clarify(err)))
    if findings:
        return Result(findings)  # semantic checks need a well-formed document

    m = model.build(doc)
    findings.extend(_semantic(m))
    return Result(findings)


def _semantic(m: model.Module) -> list[Finding]:
    f: list[Finding] = []

    # Keys reference declared, non-optional, non-state properties.
    for e in m.entities.values():
        for key in e.keys:
            where = f"entities/{e.name}/keys"
            prop = e.properties.get(key)
            if prop is None:
                f.append(Finding("key-ref", where, f"key '{key}' is not a declared property"))
            elif prop.is_state:
                f.append(Finding("key-type", where, f"key '{key}' may not be a state property"))
            elif prop.optional:
                f.append(Finding("key-type", where, f"key '{key}' may not be optional"))

    # State initial values are members of the declared value set.
    for e in m.entities.values():
        for p in e.properties.values():
            if p.is_state and p.initial not in (p.values or []):
                f.append(Finding(
                    "state-initial", f"entities/{e.name}/properties/{p.name}",
                    f"initial '{p.initial}' is not among declared values"))

    # Link endpoints exist; traversal names do not collide per entity.
    for l in m.links.values():
        for end, label in ((l.from_entity, "from"), (l.to_entity, "to")):
            if end not in m.entities:
                f.append(Finding("link-ref", f"links/{l.name}/{label}",
                                 f"'{end}' is not a declared entity"))
    # Link properties may not collide with far-entity properties (ADR 0006).
    for l in m.links.values():
        far_ends = [l.to_entity] + ([l.from_entity] if l.reverse else [])
        for far in far_ends:
            far_entity = m.entities.get(far)
            if far_entity is None:
                continue
            for pname in l.properties:
                if pname in far_entity.properties:
                    f.append(Finding(
                        "name-collision", f"links/{l.name}/properties/{pname}",
                        f"link property '{pname}' collides with a property of {far}"))

    for e in m.entities.values():
        seen: dict[str, str] = {p: "property" for p in e.properties}
        for l in m.links.values():
            names = []
            if l.from_entity == e.name:
                names.append((l.name, f"link '{l.name}'"))
            if l.reverse and l.to_entity == e.name:
                names.append((l.reverse, f"reverse of link '{l.name}'"))
            for name, what in names:
                if name in seen:
                    f.append(Finding(
                        "name-collision", f"entities/{e.name}",
                        f"'{name}' ({what}) collides with {seen[name]} on {e.name}"))
                seen[name] = what

    # Actions: references, effects, guards.
    for a in m.actions.values():
        where = f"actions/{a.name}"
        target = m.entities.get(a.target)
        if target is None:
            f.append(Finding("action-ref", f"{where}/target",
                             f"'{a.target}' is not a declared entity"))
            continue
        if a.authority not in m.roles:
            f.append(Finding("action-ref", f"{where}/authority",
                             f"'{a.authority}' is not a declared role"))
        if a.approval and a.approval.authority not in m.roles:
            f.append(Finding("action-ref", f"{where}/approval/authority",
                             f"'{a.approval.authority}' is not a declared role"))

        seen_paths: set[str] = set()
        for path, value in a.effects:
            if path in seen_paths:
                f.append(Finding("effect-duplicate", f"{where}/effects/{path}",
                                 "the same path is assigned more than once"))
            seen_paths.add(path)
            f.extend(_effect(m, a, target, path, value))

        report = guards.analyze(a.guard, m, "target", a.target, params=a.parameters)
        f.extend(Finding(i.code, f"{where}/guard", i.message) for i in report.issues)
        if a.approval:
            rep = guards.analyze(a.approval.when, m, "target", a.target, params=a.parameters)
            f.extend(Finding(i.code, f"{where}/approval/when", i.message) for i in rep.issues)

    # Invariants.
    for inv in m.invariants.values():
        where = f"invariants/{inv.name}"
        if inv.over not in m.entities:
            f.append(Finding("invariant-ref", f"{where}/over",
                             f"'{inv.over}' is not a declared entity"))
            continue
        report = guards.analyze(inv.check, m, "entity", inv.over)
        f.extend(Finding(i.code, f"{where}/check", i.message) for i in report.issues)

    return f


def _to_one(link: model.Link, traversal_name: str) -> bool:
    """Whether traversing `traversal_name` follows the link toward one object."""
    forward = traversal_name == link.name
    if link.cardinality == "one_to_one":
        return True
    if link.cardinality == "many_to_one":
        return forward       # from-side sees one; reverse sees many
    if link.cardinality == "one_to_many":
        return not forward   # reverse sees one; forward sees many
    return False             # many_to_many: never to-one


def _effect(m: model.Module, a: model.Action, target: model.Entity,
            path: str, value: object) -> list[Finding]:
    f: list[Finding] = []
    where = f"actions/{a.name}/effects/{path}"
    segs = path.split(".")[1:]  # drop 'target'
    if len(segs) == 1:
        prop = target.properties.get(segs[0])
        if prop is None:
            f.append(Finding("effect-path", where,
                             f"'{segs[0]}' is not a property of {target.name}"))
            return f
    else:  # two segments: one hop then property (schema bounds the length)
        info = m.traversal_info(target.name)
        hop = info.get(segs[0])
        if hop is None:
            f.append(Finding("effect-path", where,
                             f"'{segs[0]}' is not a traversal from {target.name}"))
            return f
        far, link = hop
        if not _to_one(link, segs[0]):
            f.append(Finding(
                "effect-cardinality", where,
                f"'{segs[0]}' traverses toward many {far} objects; an effect "
                f"must address exactly one"))
            return f
        prop = m.entities[far].properties.get(segs[1])
        if prop is None:
            f.append(Finding("effect-path", where,
                             f"'{segs[1]}' is not a property of {far}"))
            return f

    closed = prop.type in ("enum", "state")
    if isinstance(value, str) and value.startswith("params."):
        pname = value.split(".", 1)[1]
        param = a.parameters.get(pname)
        if param is None:
            f.append(Finding("effect-value", where,
                             f"'{value}' is not a declared parameter"))
        elif param.optional:
            f.append(Finding(
                "effect-value", where,
                f"optional parameter '{pname}' may not drive an effect; "
                f"the write would be undefined when it is omitted"))
        elif closed and (param.type != "enum"
                         or not set(param.values or []) <= set(prop.values or [])):
            f.append(Finding(
                "effect-value", where,
                f"parameter '{pname}' may carry values outside '{prop.name}''s "
                f"declared value set"))
    elif isinstance(value, str) and value.startswith("target."):
        ref = value.split(".")[1:]
        src = target.properties.get(ref[0]) if len(ref) == 1 else None
        if src is None:
            f.append(Finding("effect-value", where,
                             f"'{value}' does not reference a property of {target.name}"))
        elif closed and (src.type not in ("enum", "state")
                         or not set(src.values or []) <= set(prop.values or [])):
            f.append(Finding(
                "effect-value", where,
                f"'{value}' may carry values outside '{prop.name}''s declared value set"))
    elif closed and value not in (prop.values or []):
        f.append(Finding("effect-value", where,
                         f"'{value}' is not among declared values of '{prop.name}'"))
    return f
