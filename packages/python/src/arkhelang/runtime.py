"""A minimal in-memory runtime for Arkhe tool contracts.

This is the reference execution semantics for v0.1, sized for demos and
tests: an in-memory instance graph, contract-driven guard evaluation, claim
checks, approval escalation, effect application, and audit events. It is not
a production runtime; it is the executable meaning of a contract.

Refusals are structured and name the first failing guard clause, because a
refusal an operator cannot read is a bug in the refusal.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

import celpy
from celpy import celtypes

_ENV = celpy.Environment()
_TODAY = None  # test hook; None means date.today()


def _today() -> datetime.date:
    return _TODAY or datetime.date.today()


def _as_date(value) -> datetime.date:
    return datetime.date.fromisoformat(str(value))


def _stdlib():
    def months_since(d):
        today, dd = _today(), _as_date(d)
        return celtypes.IntType(
            (today.year - dd.year) * 12 + (today.month - dd.month)
            - (1 if today.day < dd.day else 0))

    def days_since(d):
        return celtypes.IntType((_today() - _as_date(d)).days)

    def today():
        return celtypes.StringType(_today().isoformat())

    return {"months_since": months_since, "days_since": days_since, "today": today}


@dataclass
class World:
    """An in-memory instance graph for one module.

    entities: {EntityName: {key_value: {prop: value}}}
    links: list of (link_name, from_key, to_key, link_props)
    """

    module: dict
    entities: dict = field(default_factory=dict)
    links: list = field(default_factory=list)
    audit_log: list = field(default_factory=list)

    def add(self, entity: str, key: str, **props):
        defaults = {
            name: p.get("initial")
            for name, p in self.module["entities"][entity]["properties"].items()
            if p.get("type") == "state"
        }
        self.entities.setdefault(entity, {})[key] = {**defaults, **props}
        return self

    def link(self, link_name: str, from_key: str, to_key: str, **props):
        self.links.append((link_name, from_key, to_key, props))
        return self

    def _link_decl(self, name: str) -> dict:
        return self.module["links"][name]

    def _traversals(self, entity: str) -> dict[str, tuple[str, str, str]]:
        """traversal name -> (link name, far entity, direction)."""
        out = {}
        for name, l in (self.module.get("links") or {}).items():
            if l["from"] == entity:
                out[name] = (name, l["to"], "forward")
            if l.get("reverse") and l["to"] == entity:
                out[l["reverse"]] = (name, l["from"], "reverse")
        return out

    def _is_many(self, link_name: str, direction: str) -> bool:
        cardinality = self._link_decl(link_name)["cardinality"]
        forward = direction == "forward"
        if cardinality == "one_to_one":
            return False
        if cardinality == "many_to_one":
            return not forward
        if cardinality == "one_to_many":
            return forward
        return True

    def neighbourhood(self, entity: str, key: str, depth: int = 2) -> dict:
        """Instance properties plus traversals materialized to `depth` hops,
        with link properties merged into the far object (ADR 0006)."""
        props = dict(self.entities.get(entity, {}).get(key) or {})
        if depth <= 0:
            return props
        for tname, (lname, far, direction) in self._traversals(entity).items():
            members = []
            for l_name, f_key, t_key, l_props in self.links:
                if l_name != lname:
                    continue
                far_key = t_key if direction == "forward" else f_key
                near_key = f_key if direction == "forward" else t_key
                if near_key != key:
                    continue
                member = self.neighbourhood(far, far_key, depth - 1)
                member.update(l_props)
                members.append(member)
            if self._is_many(lname, direction):
                props[tname] = members
            else:
                # To-one traversals are a single object in guard semantics.
                props[tname] = members[0] if members else {}
        return props


@dataclass
class Decision:
    allowed: bool
    action: str
    refusal: dict | None = None
    effects: list = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.allowed


def _split_conjuncts(expression: str) -> list[str]:
    """Top-level '&&' conjuncts, for labelling refusals only.

    Never used to decide allow/refuse (the whole expression decides; CEL
    precedence binds '&&' tighter than '||', so clause-wise conjunction is
    not equivalent when '||' appears at the top level). Quote-aware, and
    returns the whole expression unsplit if a top-level '||' is present or
    anything looks unbalanced, so the label degrades to the full guard
    rather than to a wrong fragment.
    """
    clauses, depth, start, i = [], 0, 0, 0
    top_level_or = False
    n = len(expression)
    while i < n:
        ch = expression[i]
        if ch in "'\"":
            quote = ch
            i += 1
            while i < n and expression[i] != quote:
                i += 2 if expression[i] == "\\" else 1
            if i >= n:
                return [expression.strip()]  # unbalanced quote: do not split
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
            if depth < 0:
                return [expression.strip()]
        elif depth == 0 and expression.startswith("||", i):
            top_level_or = True
        elif depth == 0 and expression.startswith("&&", i):
            clauses.append(expression[start:i].strip())
            i += 2
            start = i
            continue
        i += 1
    if depth != 0 or top_level_or:
        return [expression.strip()]
    clauses.append(expression[start:].strip())
    return [c for c in clauses if c] or [expression.strip()]


def _failing_clause(expression: str, bindings: dict) -> str:
    """The first false top-level conjunct, for the refusal label."""
    for clause in _split_conjuncts(expression):
        try:
            if not _evaluate(clause, bindings):
                return clause
        except Exception:
            return expression.strip()
    return expression.strip()


def _evaluate(expression: str, bindings: dict) -> bool:
    ast = _ENV.compile(expression)
    prog = _ENV.program(ast, functions=_stdlib())
    return bool(prog.evaluate(
        {k: celpy.json_to_cel(v) for k, v in bindings.items()}))


def _claims_satisfied(required: dict, actor: dict) -> bool:
    claims = actor.get("claims") or {}
    for key, value in (required or {}).items():
        held = claims.get(key)
        if isinstance(held, (list, tuple, set)):
            if value not in held:
                return False
        elif held != value:
            return False
    return True


def _refuse(contract: dict, failed_clause: str, explanation: str) -> Decision:
    shape = dict(contract["refusal"]["shape"])
    shape.update({"failed_clause": failed_clause, "explanation": explanation})
    return Decision(False, contract["name"], refusal=shape)


def execute(contract: dict, world: World, target_key: str, actor: dict,
            params: dict | None = None, approver: dict | None = None) -> Decision:
    """Attempt an action under its contract. Applies effects on success."""
    params = params or {}
    entity = contract["target"]["entity"].split(".", 1)[1]
    instance = world.entities.get(entity, {}).get(target_key)
    if instance is None:
        return _refuse(contract, "target",
                       f"no {entity} with key '{target_key}' exists")

    # Parameters: closed sets enforced at the boundary.
    for name, decl in contract["parameters"].items():
        if name not in params:
            if not decl.get("optional"):
                return _refuse(contract, f"params.{name}",
                               f"required parameter '{name}' was not supplied")
            continue
        if decl.get("values") is not None and params[name] not in decl["values"]:
            return _refuse(contract, f"params.{name}",
                           f"'{params[name]}' is not among declared values")

    # Authority.
    if not _claims_satisfied(contract["authority"]["claims"], actor):
        return _refuse(
            contract, "authority",
            f"actor lacks the claims of {contract['authority']['role']}")

    # Guard: the whole expression decides; conjunct splitting only labels.
    bindings = {
        "target": world.neighbourhood(entity, target_key),
        "params": params,
    }
    expression = contract["guard"]["expression"]
    try:
        allowed = _evaluate(expression, bindings)
    except Exception as exc:
        return _refuse(contract, expression.strip(),
                       f"guard evaluation failed: {exc}")
    if not allowed:
        return _refuse(contract, _failing_clause(expression, bindings),
                       "guard clause evaluated to false")

    # Approval escalation. Evaluation errors refuse; they never raise.
    approval = contract.get("approval")
    if approval is not None:
        try:
            needs_approval = _evaluate(approval["when"], bindings)
        except Exception as exc:
            return _refuse(contract, "approval.when",
                           f"approval condition failed to evaluate: {exc}")
        if needs_approval:
            if approver is None or not _claims_satisfied(
                    approval["authority"]["claims"], approver):
                return _refuse(
                    contract, "approval",
                    f"approval by {approval['authority']['role']} is required")
            if approver == actor:
                return _refuse(
                    contract, "approval",
                    "approver must be a different actor (four-eyes)")

    # Effects: check every path before applying any, so a refusal can never
    # leave a partial write behind.
    for effect in contract["effects"]:
        segs = effect["path"].split(".")[1:]
        if len(segs) == 2:
            tname = segs[0]
            hop = world._traversals(entity).get(tname)
            if hop is None:
                return _refuse(contract, f"effects.{effect['path']}",
                               f"'{tname}' is not a traversal from {entity}")
            lname, far, direction = hop
            if world._is_many(lname, direction):
                # Defence in depth: the validator bans this, but a contract
                # arriving by another path must not fan out writes.
                return _refuse(
                    contract, f"effects.{effect['path']}",
                    f"'{tname}' traverses toward many {far} objects; the "
                    f"contract is inconsistent with ADR 0005")

    applied = []
    for effect in contract["effects"]:
        segs = effect["path"].split(".")[1:]
        value = effect["value"]
        if isinstance(value, str) and value.startswith("params."):
            value = params[value.split(".", 1)[1]]
        elif isinstance(value, str) and value.startswith("target."):
            value = instance.get(value.split(".", 1)[1])
        if len(segs) == 1:
            instance[segs[0]] = value
            applied.append({"entity": entity, "key": target_key,
                            "property": segs[0], "value": value})
        else:
            tname, prop = segs
            lname, far, direction = world._traversals(entity)[tname]
            for l_name, f_key, t_key, _ in world.links:
                if l_name != lname:
                    continue
                near = f_key if direction == "forward" else t_key
                far_key = t_key if direction == "forward" else f_key
                if near == target_key:
                    world.entities[far][far_key][prop] = value
                    applied.append({"entity": far, "key": far_key,
                                    "property": prop, "value": value})

    if contract["audit"]["level"] != "none":
        world.audit_log.append({
            "event": contract["audit"]["event"],
            "target": target_key,
            "actor": actor.get("name") or actor.get("claims"),
            "params": params,
            "effects": applied,
        })

    return Decision(True, contract["name"], effects=applied)
