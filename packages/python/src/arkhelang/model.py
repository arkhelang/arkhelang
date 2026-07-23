"""In-memory model of an Arkhe module, built from parsed YAML.

Assumes the document already passed structural (JSON Schema) validation;
this layer resolves names and answers type questions for semantic checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field


SCALAR_TYPES = {"string", "int", "number", "bool", "date", "datetime", "document"}


def parse_synonyms(raw: str | None) -> list[str]:
    """Parse a `synonyms` annotation into its list of labels.

    The annotation is string-valued (per the schema), a comma-separated list.
    Each label is trimmed of surrounding whitespace; empty labels are kept in
    the returned list so the validator can flag them. On a valid module the
    list is clean (no empties, no duplicates), so contract and emitter code can
    use it directly.
    """
    if not raw:
        return []
    return [label.strip() for label in raw.split(",")]


def _node_synonyms(node: dict) -> list[str]:
    return parse_synonyms((node.get("annotations") or {}).get("synonyms"))


@dataclass
class Property:
    name: str
    type: str
    values: list | None = None
    initial: object | None = None
    optional: bool = False
    synonyms: list[str] = field(default_factory=list)

    @property
    def is_state(self) -> bool:
        return self.type == "state"


@dataclass
class Entity:
    name: str
    keys: list[str]
    properties: dict[str, Property]
    synonyms: list[str] = field(default_factory=list)


@dataclass
class Link:
    name: str
    from_entity: str
    to_entity: str
    cardinality: str
    reverse: str | None = None
    properties: dict[str, Property] = field(default_factory=dict)
    synonyms: list[str] = field(default_factory=list)


@dataclass
class Approval:
    when: str
    authority: str


@dataclass
class Action:
    name: str
    target: str
    guard: str
    authority: str
    audit: str
    effects: list[tuple[str, object]]
    parameters: dict[str, Property] = field(default_factory=dict)
    approval: Approval | None = None
    synonyms: list[str] = field(default_factory=list)


@dataclass
class Invariant:
    name: str
    over: str
    check: str


@dataclass
class Module:
    name: str
    version: str
    arkhe: str
    roles: dict[str, dict]
    entities: dict[str, Entity]
    links: dict[str, Link]
    actions: dict[str, Action]
    invariants: dict[str, Invariant]

    def traversals_from(self, entity_name: str) -> dict[str, str]:
        """Map of traversal name -> far entity name, from this entity.

        Forward link names traverse from `from_entity`; declared reverse
        names traverse from `to_entity`.
        """
        return {name: far for name, (far, _) in self.traversal_info(entity_name).items()}

    def traversal_info(self, entity_name: str) -> dict[str, tuple[str, "Link"]]:
        """Map of traversal name -> (far entity name, link)."""
        out: dict[str, tuple[str, Link]] = {}
        for link in self.links.values():
            if link.from_entity == entity_name:
                out[link.name] = (link.to_entity, link)
            if link.reverse and link.to_entity == entity_name:
                out[link.reverse] = (link.from_entity, link)
        return out


def _properties(raw: dict) -> dict[str, Property]:
    props = {}
    for pname, p in (raw or {}).items():
        props[pname] = Property(
            name=pname,
            type=p["type"],
            values=p.get("values"),
            initial=p.get("initial"),
            optional=p.get("optional", False),
            synonyms=_node_synonyms(p),
        )
    return props


def build(doc: dict) -> Module:
    entities = {
        name: Entity(
            name=name,
            keys=e["keys"],
            properties=_properties(e["properties"]),
            synonyms=_node_synonyms(e),
        )
        for name, e in doc["entities"].items()
    }
    links = {
        name: Link(
            name=name,
            from_entity=l["from"],
            to_entity=l["to"],
            cardinality=l["cardinality"],
            reverse=l.get("reverse"),
            properties=_properties(l.get("properties")),
            synonyms=_node_synonyms(l),
        )
        for name, l in (doc.get("links") or {}).items()
    }
    actions = {}
    for name, a in (doc.get("actions") or {}).items():
        effects = []
        for eff in a["effects"]:
            ((path, value),) = eff.items()
            effects.append((path, value))
        approval = None
        if "approval" in a:
            approval = Approval(when=a["approval"]["when"], authority=a["approval"]["authority"])
        actions[name] = Action(
            name=name,
            target=a["target"],
            guard=a["guard"],
            authority=a["authority"],
            audit=a["audit"],
            effects=effects,
            parameters=_properties(a.get("parameters")),
            approval=approval,
            synonyms=_node_synonyms(a),
        )
    invariants = {
        name: Invariant(name=name, over=i["over"], check=i["check"])
        for name, i in (doc.get("invariants") or {}).items()
    }
    return Module(
        name=doc["module"],
        version=doc["version"],
        arkhe=doc["arkhe"],
        roles=doc.get("roles") or {},
        entities=entities,
        links=links,
        actions=actions,
        invariants=invariants,
    )
