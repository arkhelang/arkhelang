"""Conformance tests: the golden files are the spec.

Runs the validator against fixture one (must pass), every module in
fixtures/invalid (must fail), and a battery of semantic and guard probes
built by mutating fixture one.
"""

import copy
from pathlib import Path

import pytest
import yaml

from arkhelang.validate import validate, validate_file

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "fixtures"


@pytest.fixture()
def base():
    return yaml.safe_load(
        (FIXTURES / "model_risk" / "model-risk.arkhe.yaml").read_text())


def test_fixture_one_is_valid(base):
    result = validate(base)
    assert result.ok, [f.__dict__ for f in result.findings]


@pytest.mark.parametrize(
    "path", sorted((FIXTURES / "invalid").glob("*.arkhe.yaml")),
    ids=lambda p: p.stem)
def test_invalid_fixtures_are_rejected(path):
    assert not validate_file(path).ok, f"{path.name} must fail validation"


def expect(base, code, mutate):
    doc = copy.deepcopy(base)
    mutate(doc)
    result = validate(doc)
    codes = {f.code for f in result.findings}
    assert code in codes, f"expected {code}, got {codes or 'VALID'}"


SEMANTIC_CASES = {
    "key-ref": lambda d: d["entities"]["TradingDesk"].update({"keys": ["nope"]}),
    "key-type": lambda d: d["entities"]["TradingDesk"]["properties"]["desk_id"].update(
        {"optional": True}),
    "state-initial": lambda d: d["entities"]["FinancialModel"]["properties"]["status"].update(
        {"initial": "zzz"}),
    "link-ref": lambda d: d["links"]["owned_by"].update({"to": "Ghost"}),
    "name-collision": lambda d: d["links"]["assesses"].update({"reverse": "status"}),
    "action-ref": lambda d: d["actions"]["retire_model"].update({"authority": "nobody"}),
    "effect-path": lambda d: d["actions"]["retire_model"].update(
        {"effects": [{"target.ghost": "x"}]}),
    "effect-value": lambda d: d["actions"]["retire_model"].update(
        {"effects": [{"target.status": "zombie"}]}),
    "effect-duplicate": lambda d: d["actions"]["retire_model"].update(
        {"effects": [{"target.status": "retired"}, {"target.status": "draft"}]}),
    "effect-cardinality": lambda d: d["actions"]["submit_for_validation"].update(
        {"target": "TradingDesk", "guard": 'target.name != ""',
         "effects": [{"target.models.status": "draft"}]}),
    "effect-value-optional-param": lambda d: d["actions"]["waive_finding"].update(
        {"parameters": {"justification": {"type": "string"},
                        "sev": {"type": "enum", "values": ["low"], "optional": True}},
         "effects": [{"target.severity": "params.sev"}]}),
}

GUARD_CASES = {
    "guard-unknown-name": lambda d: d["actions"]["retire_model"].update(
        {"guard": "target.ghost == 1"}),
    "guard-unknown-name-bare-fn": lambda d: d["actions"]["retire_model"].update(
        {"guard": "today == target.commissioned_date"}),
    "guard-unknown-name-bracket": lambda d: d["actions"]["retire_model"].update(
        {"guard": "target['ghost'] == 'x'"}),
    "guard-unknown-function": lambda d: d["actions"]["retire_model"].update(
        {"guard": 'sha256(target.model_id) == "x"'}),
    "guard-traversal-depth": lambda d: d["invariants"].update(
        {"deep": {"over": "Finding",
                  "check": 'entity.raised_in.assesses.owned_by.name == "x"'}}),
    "guard-index": lambda d: d["actions"]["retire_model"].update(
        {"guard": "target[params.reason] == 'x'"}),
    "guard-macro-arity": lambda d: d["actions"]["retire_model"].update(
        {"guard": "target.reviewed_by.exists(r)"}),
    "guard-syntax": lambda d: d["actions"]["retire_model"].update(
        {"guard": "target.status == =="}),
    "guard-macro-base": lambda d: d["invariants"].update(
        {"bad": {"over": "FinancialModel",
                 "check": 'entity.owned_by.all(d, d.name != "")'}}),
}


def _expected_code(name: str) -> str:
    for suffix in ("-bare-fn", "-bracket", "-optional-param"):
        name = name.split(suffix)[0]
    return name


@pytest.mark.parametrize("code,mutate", SEMANTIC_CASES.items(), ids=SEMANTIC_CASES.keys())
def test_semantic_negatives(base, code, mutate):
    expect(base, _expected_code(code), mutate)


@pytest.mark.parametrize("name,mutate", GUARD_CASES.items(), ids=GUARD_CASES.keys())
def test_guard_negatives(base, name, mutate):
    expect(base, _expected_code(name), mutate)


def test_link_property_collision(base):
    expect(base, "name-collision",
           lambda d: d["links"]["consumes"]["properties"].update(
               {"provider": {"type": "string"}}))


def test_macro_over_macro_is_accepted(base):
    doc = copy.deepcopy(base)
    doc["actions"]["retire_model"]["guard"] = (
        "target.reviewed_by.map(r, r.outcome).exists(o, o == 'approved')")
    assert validate(doc).ok


def test_enum_subset_parameter_into_state_is_accepted(base):
    doc = copy.deepcopy(base)
    doc["actions"]["retire_model"]["parameters"] = {
        "st": {"type": "enum", "values": ["retired"]}}
    doc["actions"]["retire_model"]["effects"] = [{"target.status": "params.st"}]
    assert validate(doc).ok


def test_duplicate_yaml_keys_are_rejected(tmp_path):
    doc = (
        "module: m\nversion: 0.1.0\narkhe: '0.1'\n"
        "entities:\n"
        "  A:\n    keys: [x]\n    properties:\n      x: {type: string}\n"
        "  A:\n    keys: [y]\n    properties:\n      y: {type: string}\n"
    )
    p = tmp_path / "dup.arkhe.yaml"
    p.write_text(doc)
    result = validate_file(p)
    assert not result.ok and result.findings[0].code == "yaml"
