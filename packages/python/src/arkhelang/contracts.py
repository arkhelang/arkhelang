"""Tool-contract generation: the Arkhe IR.

One JSON document per action carrying everything downstream emitters need:
the canonical guard with its evaluation context (target, traversals, stdlib),
authority and approval bindings, audit obligation, effects, the write
surface, a structured refusal shape, and provenance back to the module.

Read contracts (get-by-key per entity, traverse per declared traversal) are
generated alongside, so an agent's read surface is also derived rather than
hand-written.
"""

from __future__ import annotations

import hashlib
import json

from . import guards, model

CONTRACT_VERSION = "0.1"


def canonical_form(doc: dict) -> bytes:
    """The module's canonical byte form (ADR 0007).

    Defined on the schema-validated document: CEL expressions folded to
    single-space whitespace, then JSON with sorted keys, compact separators,
    UTF-8, no ASCII escaping.
    """
    canon = json.loads(json.dumps(doc))  # deep copy via JSON round trip
    for action in (canon.get("actions") or {}).values():
        action["guard"] = _fold(action.get("guard"))
        if "approval" in action:
            action["approval"]["when"] = _fold(action["approval"].get("when"))
    for invariant in (canon.get("invariants") or {}).values():
        invariant["check"] = _fold(invariant.get("check"))
    return json.dumps(
        canon, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _canonical_hash(doc: dict) -> str:
    return "sha256:" + hashlib.sha256(canonical_form(doc)).hexdigest()


def _fold(text: str | None) -> str:
    return " ".join((text or "").split())


def _qualified(module: model.Module, entity: str) -> str:
    return f"{module.name}.{entity}"


def _parameter(p: model.Property) -> dict:
    out: dict = {"type": p.type}
    if p.values is not None:
        out["values"] = p.values
    if p.optional:
        out["optional"] = True
    return out


def _authority(module: model.Module, role: str) -> dict:
    return {
        "role": f"{module.name}.{role}",
        "claims": (module.roles.get(role) or {}).get("claims") or {},
    }


def _guard_block(module: model.Module, action: model.Action) -> dict:
    """Guard block with an evaluation context covering the guard AND the
    approval clause, so a runtime holding only the contract can bind
    everything both expressions need."""
    report = guards.analyze(
        action.guard, module, "target", action.target, params=action.parameters)
    reports = [report]
    if action.approval is not None:
        reports.append(guards.analyze(
            action.approval.when, module, "target", action.target,
            params=action.parameters))
    traversals = []
    stdlib: set[str] = set()
    seen = set()
    for rep in reports:
        stdlib |= rep.stdlib_used
        for t in rep.traversals:
            key = (t["path"], t["link"])
            if key not in seen:
                seen.add(key)
                traversals.append({
                    "path": t["path"],
                    "link": f"{module.name}.{t['link']}",
                    "direction": t["direction"],
                    "to": _qualified(module, t["to"]),
                    "many": t["many"],
                })
    return {
        "language": "cel",
        "expression": _fold(action.guard),
        "context": {
            "target": _qualified(module, action.target),
            "traversals": traversals,
            "stdlib": sorted(stdlib),
        },
    }


def _write_surface(module: model.Module, action: model.Action) -> list[str]:
    touched = {action.target}
    info = module.traversal_info(action.target)
    for path, _ in action.effects:
        segs = path.split(".")[1:]
        if len(segs) == 2 and segs[0] in info:
            touched.add(info[segs[0]][0])
    return sorted(_qualified(module, e) for e in touched)


def action_contract(module: model.Module, action: model.Action,
                    source_hash: str, description: str | None) -> dict:
    return {
        "arkhe_contract": CONTRACT_VERSION,
        "kind": "action",
        "name": f"{module.name}.{action.name}",
        "description": _fold(description),
        "target": {
            "entity": _qualified(module, action.target),
            "keys": module.entities[action.target].keys,
        },
        "parameters": {
            name: _parameter(p) for name, p in action.parameters.items()},
        "guard": _guard_block(module, action),
        "authority": _authority(module, action.authority),
        "approval": (
            None if action.approval is None else {
                "when": _fold(action.approval.when),
                "authority": _authority(module, action.approval.authority),
            }),
        "audit": {
            "level": action.audit,
            "event": f"{module.name}.{action.name}.v1",
        },
        "effects": [
            {"path": path, "value": value} for path, value in action.effects],
        "write_surface": _write_surface(module, action),
        "refusal": {
            "shape": {
                "refused": True,
                "action": f"{module.name}.{action.name}",
                "failed_clause": "string",
                "explanation": "string",
            }
        },
        "provenance": {
            "module": module.name,
            "module_version": module.version,
            "arkhe_version": module.arkhe,
            "source_hash": source_hash,
        },
    }


def read_contract(module: model.Module, entity: model.Entity,
                  source_hash: str) -> dict:
    traversals = [
        {
            "path": name,
            "link": f"{module.name}.{link.name}",
            "direction": "forward" if name == link.name else "reverse",
            "to": _qualified(module, far),
            "cardinality": link.cardinality,
            "many": guards._hop_is_many(link, name),
        }
        for name, (far, link) in sorted(module.traversal_info(entity.name).items())
    ]
    return {
        "arkhe_contract": CONTRACT_VERSION,
        "kind": "read",
        "name": f"{module.name}.{entity.name}.get",
        "target": {
            "entity": _qualified(module, entity.name),
            "keys": entity.keys,
        },
        "properties": {
            name: _parameter(p) for name, p in entity.properties.items()},
        "traversals": traversals,
        "provenance": {
            "module": module.name,
            "module_version": module.version,
            "arkhe_version": module.arkhe,
            "source_hash": source_hash,
        },
    }


def generate(doc: dict) -> dict[str, dict]:
    """All contracts for a validated module document, keyed by contract name.

    The caller is responsible for validating first; generating contracts
    from an invalid module is undefined.
    """
    m = model.build(doc)
    source_hash = _canonical_hash(doc)
    out: dict[str, dict] = {}
    actions = doc.get("actions") or {}
    for name, action in m.actions.items():
        description = (actions[name].get("annotations") or {}).get("description")
        contract = action_contract(m, action, source_hash, description)
        out[contract["name"]] = contract
    for entity in m.entities.values():
        contract = read_contract(m, entity, source_hash)
        out[contract["name"]] = contract
    return out
