"""Contract generation: the expected/ files are the golden outputs."""

import json
from pathlib import Path

import pytest
import yaml

from arkhelang.contracts import generate
from arkhelang.cli import main

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
MODULE = FIXTURES / "model_risk" / "model-risk.arkhe.yaml"
EXPECTED = FIXTURES / "model_risk" / "expected"


@pytest.fixture()
def contracts():
    return generate(yaml.safe_load(MODULE.read_text()))


@pytest.mark.parametrize("golden", sorted(EXPECTED.glob("*.contract.json")),
                         ids=lambda p: p.stem)
def test_golden_contracts(contracts, golden):
    name = golden.name.replace(".contract.json", "")
    assert contracts[f"model_risk.{name}"] == json.loads(golden.read_text())


def test_every_contract_has_a_golden(contracts):
    goldens = {g.name.replace(".contract.json", "")
               for g in EXPECTED.glob("*.contract.json")}
    generated = {n.replace("model_risk.", "", 1) for n in contracts}
    assert goldens == generated


def test_generation_is_deterministic():
    doc = yaml.safe_load(MODULE.read_text())
    assert json.dumps(generate(doc), sort_keys=True) == \
        json.dumps(generate(doc), sort_keys=True)


def test_one_contract_per_action_and_entity(contracts):
    kinds = [c["kind"] for c in contracts.values()]
    assert kinds.count("action") == 6 and kinds.count("read") == 6


def test_cross_link_write_surface(contracts):
    c = contracts["model_risk.record_validation_outcome"]
    assert c["write_surface"] == [
        "model_risk.FinancialModel", "model_risk.ValidationReview"]


def test_approval_escalation_is_carried(contracts):
    c = contracts["model_risk.approve_model_change"]
    assert c["approval"]["authority"]["role"] == "model_risk.head_of_model_risk"
    assert "tier == 1" in c["approval"]["when"]


def test_guard_expression_is_single_line(contracts):
    for c in contracts.values():
        if c["kind"] == "action":
            assert "\n" not in c["guard"]["expression"]


def test_cli_refuses_invalid_module(capsys, tmp_path):
    bad = FIXTURES / "invalid" / "state_without_initial.arkhe.yaml"
    assert main(["contracts", str(bad)]) == 1
    assert "refusing to generate" in capsys.readouterr().err


def test_cli_writes_contract_files(tmp_path):
    assert main(["contracts", str(MODULE), "--out", str(tmp_path)]) == 0
    written = list(tmp_path.glob("*.contract.json"))
    assert len(written) == 12


def test_canonical_hash_ignores_formatting():
    """ADR 0007: reformatting a module does not change its hash."""
    from arkhelang.contracts import _canonical_hash
    doc = yaml.safe_load(MODULE.read_text())
    reordered = dict(reversed(list(doc.items())))
    assert _canonical_hash(doc) == _canonical_hash(reordered)
    refolded = json.loads(json.dumps(doc))
    refolded["actions"]["grant_production_use"]["guard"] = " ".join(
        doc["actions"]["grant_production_use"]["guard"].split()) + "  "
    assert _canonical_hash(doc) == _canonical_hash(refolded)


def test_effect_carries_resolved_state_type(contracts):
    """ADR 0008 item 3: an effect inlines its destination property's type."""
    (eff,) = contracts["model_risk.retire_model"]["effects"]
    assert eff["type"] == "state"
    assert eff["values"] == [
        "draft", "in_validation", "validated", "production", "retired"]


def test_effect_on_scalar_destination_has_type_but_no_values(contracts):
    effects = contracts["model_risk.record_validation_outcome"]["effects"]
    scalar = next(e for e in effects if e["path"] == "target.assesses.last_validated")
    assert scalar["type"] == "date" and "values" not in scalar


def test_cross_link_effect_resolves_the_far_entitys_property_type(contracts):
    effects = contracts["model_risk.record_validation_outcome"]["effects"]
    far = next(e for e in effects if e["path"] == "target.assesses.status")
    assert far["type"] == "state"
    assert far["values"] == [
        "draft", "in_validation", "validated", "production", "retired"]


def test_enum_parameter_driven_effect_resolves_destination_type(contracts):
    effects = contracts["model_risk.record_validation_outcome"]["effects"]
    driven = next(e for e in effects if e["path"] == "target.outcome")
    assert driven["value"] == "params.outcome" and driven["type"] == "state"
    assert driven["values"] == [
        "in_progress", "approved", "approved_with_conditions", "rejected"]


def test_canonical_hash_tracks_content():
    from arkhelang.contracts import _canonical_hash
    doc = yaml.safe_load(MODULE.read_text())
    changed = json.loads(json.dumps(doc))
    changed["entities"]["FinancialModel"]["properties"]["tier"]["values"] = [1, 2]
    assert _canonical_hash(doc) != _canonical_hash(changed)
