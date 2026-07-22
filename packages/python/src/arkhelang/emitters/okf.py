"""The OKF emitter: a module and its contracts -> an Open Knowledge Format bundle.

OKF (Open Knowledge Format v0.1, Google, June 2026) is a directory of markdown
files, one concept per file, each with YAML frontmatter and a body, cross-linked
by ordinary relative markdown links. The file path is the concept identity.
This emitter projects an Arkhe module into that shape: one file per entity, link,
action, role, and invariant, plus an `index.md` per section for progressive
disclosure and a root `index.md` for the module.

Determinism. OKF's frontmatter admits an optional `timestamp` field, and its
examples set it to the authoring time. A wall-clock timestamp would make the
golden files churn on every run, so this emitter omits `timestamp` entirely
rather than invent a value. That is a deliberate, documented deviation from the
OKF example set: the file path plus the module provenance in the contracts is
the identity and version signal here, not a timestamp. Every other axis of
output is sorted, so two runs over the same module are byte-identical.

Prose is assembled from the module's annotations and its contracts. The emitter
adds only structural scaffolding (headings, table headers, and generic framing
lines that describe the mechanism, never the domain); it invents no
domain-specific description.
"""

from __future__ import annotations

import posixpath
import re

import yaml

# The manifest file the okf emitter owns in an output directory: a sorted list
# of the bundle-relative paths it wrote, so a later emit can prune only the
# files it is responsible for and never touch anything else in the directory.
MANIFEST_NAME = ".arkhe-okf-manifest"

# The schema patterns for the two name classes that become path segments. The
# emitter re-checks them so a malformed name can never escape into a path,
# independent of whether the caller validated the module.
_TYPE_NAME = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_MEMBER_NAME = re.compile(r"^[a-z][a-z0-9_]*$")

# Markdown-significant characters that a cell value must not carry literally,
# with backslash first so the escaping stays reversible.
_CELL_ESCAPES = {
    "\\": "\\\\",
    "`": "\\`",
    "[": "\\[",
    "]": "\\]",
    "|": "\\|",
}


class EmitError(ValueError):
    """The module cannot be emitted as a coherent OKF bundle."""


def _guard_segment(name: str, pattern: re.Pattern, kind: str) -> None:
    """Refuse a name that cannot become a safe, unambiguous path segment.

    Two failure modes: a name the schema pattern rejects (defense in depth,
    independent of caller validation), and a name that case-folds to the
    reserved word `index`, which would collide with the generated section
    index page (index.md) on any case-insensitive filesystem.
    """
    if not pattern.match(name):
        raise EmitError(
            f"cannot emit OKF: {kind} name {name!r} is not a valid path "
            f"segment (must match {pattern.pattern})")
    if name.casefold() == "index":
        raise EmitError(
            f"cannot emit OKF: {kind} named {name!r} collides with the "
            "generated section index page (index.md); any name that "
            "case-folds to 'index' is reserved, so rename it")


def _fold(text: str | None) -> str:
    """Collapse a scalar's whitespace to single spaces and strip the ends."""
    return " ".join((text or "").split())


def _unq(qualified: str) -> str:
    """Drop the leading `module.` from a qualified name."""
    return qualified.split(".", 1)[1] if "." in qualified else qualified


def _rel(from_path: str, to_path: str) -> str:
    """A relative markdown link from one bundle file to another."""
    base = posixpath.dirname(from_path)
    return posixpath.relpath(to_path, base or ".")


def _cell(value: object) -> str:
    """A table cell or inline value.

    Flatten any newline to a single space so a value cannot break a table
    row, and backslash-escape the markdown-significant characters (backtick,
    square brackets, pipe) so a value can neither open a code span or link nor
    start a new column.
    """
    text = str(value)
    for newline in ("\r\n", "\n", "\r"):
        text = text.replace(newline, " ")
    return "".join(_CELL_ESCAPES.get(ch, ch) for ch in text)


def _fenced(content: str, info: str = "text") -> list[str]:
    """A fenced code block whose fence is guaranteed to enclose the content.

    Per CommonMark a fenced block ends at a line of at least as many backticks
    as the opening fence, so a backtick run inside the content could close a
    fixed three-backtick fence early. Counting the longest run of backticks in
    the content and opening with one more (never fewer than three) keeps the
    content inside the fence whatever it contains.
    """
    longest = 0
    run = 0
    for ch in content:
        if ch == "`":
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    bar = "`" * max(3, longest + 1)
    return [f"{bar}{info}", content, bar]


def _values(decl: dict) -> str:
    values = decl.get("values")
    if not values:
        return ""
    return ", ".join(_cell(v) for v in values)


def _decl_table(header: str, decls: dict[str, dict]) -> list[str]:
    """A properties/parameters table; declaration order is preserved."""
    lines = [
        f"| {header} | Type | Values | Optional |",
        "| --- | --- | --- | --- |",
    ]
    for name, decl in decls.items():
        optional = "yes" if decl.get("optional") else "no"
        lines.append(
            f"| `{_cell(name)}` | {_cell(decl.get('type', ''))} "
            f"| {_values(decl)} | {optional} |")
    return lines


def _frontmatter(fields: dict) -> str:
    """Serialize OKF frontmatter deterministically (sorted keys)."""
    body = yaml.safe_dump(
        {k: v for k, v in fields.items() if v not in (None, "")},
        sort_keys=True, default_flow_style=False, allow_unicode=True,
        width=1 << 30)
    return f"---\n{body}---\n"


def _document(frontmatter: dict, body_lines: list[str]) -> str:
    lines = (body_lines[:-1]
             if body_lines and body_lines[-1] == "" else body_lines)
    return _frontmatter(frontmatter) + "\n" + "\n".join(lines) + "\n"


def _link(text: str, target: str) -> str:
    return f"[{text}]({target})"


def emit(module_doc: dict, contracts: dict[str, dict]) -> dict[str, str]:
    """An OKF bundle for a validated Arkhe module: {relative_path: content}.

    `module_doc` supplies annotations (the source of all prose) and the raw
    declarations; `contracts` supplies the resolved traversals, guard context,
    and write surfaces that the read and action contracts already computed.
    """
    module = module_doc["module"]
    tags = [module]
    entities = module_doc.get("entities") or {}
    links = module_doc.get("links") or {}
    roles = module_doc.get("roles") or {}
    invariants = module_doc.get("invariants") or {}

    action_contracts = {
        name: c for name, c in contracts.items() if c["kind"] == "action"}
    read_contracts = {
        _unq(c["target"]["entity"]): c
        for c in contracts.values() if c["kind"] == "read"}

    # Refuse any name that cannot become a safe path segment, before a single
    # file is built. This covers the schema patterns and the reserved `index`
    # collision for every section that generates an index page.
    for entity_name in entities:
        _guard_segment(entity_name, _TYPE_NAME, "entity")
    for link_name in links:
        _guard_segment(link_name, _MEMBER_NAME, "link")
    for full_name in action_contracts:
        _guard_segment(_unq(full_name), _MEMBER_NAME, "action")
    for role_name in roles:
        _guard_segment(role_name, _MEMBER_NAME, "role")
    for inv_name in invariants:
        _guard_segment(inv_name, _MEMBER_NAME, "invariant")

    def annotation(node: dict) -> str:
        return _fold((node.get("annotations") or {}).get("description"))

    bundle: dict[str, str] = {}

    def path_entity(name: str) -> str:
        return f"entities/{name}.md"

    def path_link(name: str) -> str:
        return f"links/{name}.md"

    def path_action(name: str) -> str:
        return f"actions/{name}.md"

    def path_role(name: str) -> str:
        return f"roles/{name}.md"

    def path_invariant(name: str) -> str:
        return f"invariants/{name}.md"

    # --- Entities -----------------------------------------------------------
    for name in sorted(entities):
        entity = entities[name]
        here = path_entity(name)
        desc = annotation(entity)
        body = [f"# {name}", ""]
        if desc:
            body += [desc, ""]

        body += ["## Keys", ""]
        for key in entity["keys"]:
            body.append(f"- `{_cell(key)}`")
        body.append("")

        props = entity.get("properties") or {}
        body += ["## Properties", ""]
        body += _decl_table("Property", props)
        body.append("")

        states = [
            (pname, p) for pname, p in props.items() if p.get("type") == "state"]
        if states:
            body += ["## Lifecycle", ""]
            for pname, p in states:
                values = ", ".join(_cell(v) for v in (p.get("values") or []))
                line = (f"The `{_cell(pname)}` property is a lifecycle state "
                        f"with values: {values}.")
                if p.get("initial") is not None:
                    line += f" Initial state: {_cell(p['initial'])}."
                body.append(line)
            body.append("")

        read = read_contracts.get(name)
        traversals = (read or {}).get("traversals") or []
        if traversals:
            body += ["## Traversals", ""]
            for t in traversals:
                far = _unq(t["to"])
                link_name = _unq(t["link"])
                arity = "many" if t.get("many") else "one"
                body.append(
                    f"- {_link(t['path'], _rel(here, path_link(link_name)))} "
                    f"to {_link(far, _rel(here, path_entity(far)))} ({arity})")
            body.append("")

        targeting = sorted(
            _unq(n) for n, c in action_contracts.items()
            if _unq(c["target"]["entity"]) == name)
        if targeting:
            body += ["## Actions", "", "Actions targeting this entity:", ""]
            for action in targeting:
                body.append(f"- {_link(action, _rel(here, path_action(action)))}")
            body.append("")

        bundle[here] = _document(
            {"type": "Arkhe Entity", "title": name,
             "description": desc, "tags": tags}, body)

    # --- Links --------------------------------------------------------------
    for name in sorted(links):
        link = links[name]
        here = path_link(name)
        desc = annotation(link)
        from_e, to_e = link["from"], link["to"]
        body = [f"# {name}", ""]
        if desc:
            body += [desc, ""]

        body += ["## Endpoints", ""]
        body.append(f"- From: {_link(from_e, _rel(here, path_entity(from_e)))}")
        body.append(f"- To: {_link(to_e, _rel(here, path_entity(to_e)))}")
        body += ["", "## Cardinality", "", _cell(link["cardinality"]), ""]

        if link.get("reverse"):
            body += ["## Reverse", ""]
            body.append(
                f"`{_cell(link['reverse'])}` traverses from "
                f"{_link(to_e, _rel(here, path_entity(to_e)))} back to "
                f"{_link(from_e, _rel(here, path_entity(from_e)))}.")
            body.append("")

        link_props = link.get("properties") or {}
        if link_props:
            body += ["## Properties", ""]
            body += _decl_table("Property", link_props)
            body.append("")

        bundle[here] = _document(
            {"type": "Arkhe Link", "title": name,
             "description": desc, "tags": tags},
            body)

    # --- Actions ------------------------------------------------------------
    for full_name in sorted(action_contracts):
        c = action_contracts[full_name]
        name = _unq(full_name)
        here = path_action(name)
        desc = _fold(c.get("description"))
        target = _unq(c["target"]["entity"])
        body = [f"# {name}", ""]
        if desc:
            body += [desc, ""]

        body += ["## Target", "",
                 _link(target, _rel(here, path_entity(target))), ""]

        body += ["## Guard", "",
                 "This action is permitted only when the following condition "
                 "holds:", ""]
        body += _fenced(c["guard"]["expression"])
        body.append("")

        authority = _unq(c["authority"]["role"])
        body += ["## Authority", "",
                 f"Role: {_link(authority, _rel(here, path_role(authority)))}", ""]

        approval = c.get("approval")
        if approval:
            approver = _unq(approval["authority"]["role"])
            body += ["## Approval", "",
                     "A second approval from "
                     f"{_link(approver, _rel(here, path_role(approver)))} is "
                     "required when:", ""]
            body += _fenced(_fold(approval["when"]))
            body.append("")

        body += ["## Audit", "", _cell(c["audit"]["level"]), ""]

        params = c.get("parameters") or {}
        if params:
            body += ["## Parameters", ""]
            body += _decl_table("Parameter", params)
            body.append("")

        effects = c.get("effects") or []
        if effects:
            body += ["## Effects", "",
                     "| Path | Value |", "| --- | --- |"]
            for eff in effects:
                body.append(f"| `{_cell(eff['path'])}` | {_cell(eff['value'])} |")
            body.append("")

        surface = c.get("write_surface") or []
        if surface:
            body += ["## Write surface", ""]
            for qualified in surface:
                ent = _unq(qualified)
                body.append(f"- {_link(ent, _rel(here, path_entity(ent)))}")
            body.append("")

        bundle[here] = _document(
            {"type": "Arkhe Action", "title": name,
             "description": desc, "tags": tags},
            body)

    # --- Roles --------------------------------------------------------------
    for name in sorted(roles):
        role = roles[name]
        here = path_role(name)
        desc = annotation(role)
        body = [f"# {name}", ""]
        if desc:
            body += [desc, ""]

        claims = role.get("claims") or {}
        if claims:
            body += ["## Claims", "", "| Claim | Pattern |", "| --- | --- |"]
            for claim in sorted(claims):
                body.append(f"| `{_cell(claim)}` | {_cell(claims[claim])} |")
            body.append("")

        authorizes = sorted(
            _unq(n) for n, c in action_contracts.items()
            if _unq(c["authority"]["role"]) == name)
        if authorizes:
            body += ["## Authorizes", "", "Actions this role authorizes:", ""]
            for action in authorizes:
                body.append(f"- {_link(action, _rel(here, path_action(action)))}")
            body.append("")

        approves = sorted(
            _unq(n) for n, c in action_contracts.items()
            if c.get("approval")
            and _unq(c["approval"]["authority"]["role"]) == name)
        if approves:
            body += ["## Approves", "", "Actions this role may approve:", ""]
            for action in approves:
                body.append(f"- {_link(action, _rel(here, path_action(action)))}")
            body.append("")

        bundle[here] = _document(
            {"type": "Arkhe Role", "title": name,
             "description": desc, "tags": tags},
            body)

    # --- Invariants ---------------------------------------------------------
    for name in sorted(invariants):
        inv = invariants[name]
        here = path_invariant(name)
        desc = annotation(inv)
        over = inv["over"]
        body = [f"# {name}", ""]
        if desc:
            body += [desc, ""]

        body += ["## Scope", "",
                 _link(over, _rel(here, path_entity(over))), ""]
        body += ["## Constraint", "",
                 f"This constraint must hold for every {over}:", ""]
        body += _fenced(_fold(inv["check"]))
        body.append("")

        bundle[here] = _document(
            {"type": "Arkhe Invariant", "title": name,
             "description": desc, "tags": tags},
            body)

    # --- Section index files (progressive disclosure) -----------------------
    def section_index(dir_name: str, title: str, members: list[str],
                      path_of, describe) -> None:
        here = f"{dir_name}/index.md"
        body = [f"# {title}", "",
                f"{title} declared in the {module} module.", ""]
        for member in members:
            desc = describe(member)
            line = f"- {_link(member, _rel(here, path_of(member)))}"
            if desc:
                line += f": {desc}"
            body.append(line)
        bundle[here] = _document(
            {"type": "Arkhe Index", "title": title, "tags": tags},
            body)

    sections: list[tuple[str, str, int]] = []
    if entities:
        section_index(
            "entities", "Entities", sorted(entities), path_entity,
            lambda n: annotation(entities[n]))
        sections.append(("entities", "Entities", len(entities)))
    if links:
        section_index(
            "links", "Links", sorted(links), path_link,
            lambda n: annotation(links[n]))
        sections.append(("links", "Links", len(links)))
    if action_contracts:
        action_names = sorted(_unq(n) for n in action_contracts)
        section_index(
            "actions", "Actions", action_names, path_action,
            lambda n: _fold(action_contracts[f"{module}.{n}"].get("description")))
        sections.append(("actions", "Actions", len(action_contracts)))
    if roles:
        section_index(
            "roles", "Roles", sorted(roles), path_role,
            lambda n: annotation(roles[n]))
        sections.append(("roles", "Roles", len(roles)))
    if invariants:
        section_index(
            "invariants", "Invariants", sorted(invariants), path_invariant,
            lambda n: annotation(invariants[n]))
        sections.append(("invariants", "Invariants", len(invariants)))

    # --- Root index ---------------------------------------------------------
    module_ann = module_doc.get("annotations") or {}
    title = _fold(module_ann.get("title")) or module
    module_desc = _fold(module_ann.get("description"))
    root = "index.md"
    body = [f"# {title}", ""]
    if module_desc:
        body += [module_desc, ""]
    body += [
        f"Module `{module}`, version {module_doc['version']}, "
        f"Arkhe {module_doc['arkhe']}.", "",
        "## Contents", ""]
    for dir_name, label, count in sections:
        target = _rel(root, f"{dir_name}/index.md")
        body.append(f"- {_link(label, target)} ({count})")
    bundle[root] = _document(
        {"type": "Arkhe Module", "title": title, "description": module_desc,
         "tags": tags}, body)

    return bundle
