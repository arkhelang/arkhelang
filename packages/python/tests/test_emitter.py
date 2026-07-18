"""The lib emitter and runtime: the demo scenario as conformance tests."""

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from arkhelang import runtime
from arkhelang.contracts import generate
from arkhelang.emitters import pylib

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
MODULE = FIXTURES / "model_risk" / "model-risk.arkhe.yaml"
GOLDEN_LIB = FIXTURES / "model_risk" / "expected" / "model_risk_lib.py"


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    doc = yaml.safe_load(MODULE.read_text())
    source = pylib.emit(doc, generate(doc))
    path = tmp_path_factory.mktemp("lib") / "model_risk_lib.py"
    path.write_text(source)
    spec = importlib.util.spec_from_file_location("model_risk_lib", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def world(lib):
    return (
        lib.new_world()
        .add("TradingDesk", "rates", name="Rates", business_line="Markets")
        .add("FinancialModel", "m1", name="M1", purpose="pricing", tier=1,
             status="validated", commissioned_date="2024-02-01",
             last_validated="2026-06-30")
        .add("ValidationReview", "r1", scope="full", outcome="approved",
             review_date="2026-06-30")
        .add("Finding", "f1", severity="high", raised_date="2026-06-30")
        .link("owned_by", "m1", "rates")
        .link("assesses", "r1", "m1")
        .link("raised_in", "f1", "r1")
    )


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    import datetime
    monkeypatch.setattr(runtime, "_TODAY", datetime.date(2026, 7, 17))


def test_emitted_lib_matches_golden():
    doc = yaml.safe_load(MODULE.read_text())
    assert pylib.emit(doc, generate(doc)) == GOLDEN_LIB.read_text()


def test_authority_refusal(lib, world):
    d = lib.grant_production_use(world, "m1", actor={"claims": {"groups": ["interns"]}})
    assert not d and d.refusal["failed_clause"] == "authority"


def test_guard_refusal_names_the_failing_clause(lib, world):
    d = lib.grant_production_use(world, "m1", actor={"claims": {"groups": ["mrm/head"]}})
    assert not d
    assert "findings.all" in d.refusal["failed_clause"]


def test_high_findings_are_structurally_unwaivable(lib, world):
    d = lib.waive_finding(world, "f1", justification="deadline",
                          actor={"claims": {"groups": ["mrm/officers"]}})
    assert not d and 'severity != "high"' in d.refusal["failed_clause"]


def test_promotion_after_remediation_applies_effect_and_audits(lib, world):
    world.entities["Finding"]["f1"]["status"] = "remediated"
    d = lib.grant_production_use(world, "m1", actor={"claims": {"groups": ["mrm/head"]}})
    assert d
    assert world.entities["FinancialModel"]["m1"]["status"] == "production"
    assert world.audit_log[-1]["event"] == "model_risk.grant_production_use.v1"


def test_stale_validation_is_refused(lib, world):
    world.entities["Finding"]["f1"]["status"] = "remediated"
    world.entities["FinancialModel"]["m1"]["last_validated"] = "2025-01-01"
    d = lib.grant_production_use(world, "m1", actor={"claims": {"groups": ["mrm/head"]}})
    assert not d and "months_since" in d.refusal["failed_clause"]


def test_tier1_change_requires_second_approval(lib, world):
    world.add("ModelChange", "c1", category="methodology",
              submitted_date="2026-07-01").link("applies_to", "c1", "m1")
    officer = {"claims": {"groups": ["mrm/officers"]}}
    d = lib.approve_model_change(world, "c1", actor=officer)
    assert not d and d.refusal["failed_clause"] == "approval"
    d = lib.approve_model_change(world, "c1", actor=officer,
                                 approver={"claims": {"groups": ["mrm/head"]}})
    assert d and world.entities["ModelChange"]["c1"]["status"] == "approved"


def test_cross_link_effect_writes_far_entity(lib, world):
    world.entities["ValidationReview"]["r1"]["outcome"] = "in_progress"
    d = lib.record_validation_outcome(world, "r1", outcome="approved",
                                      actor={"claims": {"groups": ["mrm/validation"]}})
    assert d
    assert world.entities["FinancialModel"]["m1"]["last_validated"] == "2026-06-30"
    assert world.entities["FinancialModel"]["m1"]["status"] == "validated"


def test_missing_target_refuses(lib, world):
    d = lib.retire_model(world, "ghost", reason="cleanup",
                         actor={"claims": {"groups": ["mrm/head"]}})
    assert not d and d.refusal["failed_clause"] == "target"


def test_read_function_materializes_neighbourhood(lib, world):
    m = lib.get_financial_model(world, "m1")
    assert m["reviewed_by"][0]["findings"][0]["severity"] == "high"


# Adversarial cases from the pre-commit review.

def test_mixed_or_and_guard_decides_by_precedence(lib, world):
    """A || B && C must evaluate as CEL binds it, never clause-split."""
    import copy
    contract = copy.deepcopy(lib._CONTRACTS["model_risk.retire_model"])
    contract["guard"]["expression"] = (
        'target.status == "production" || target.tier == 1 && target.purpose == "aml"')
    world.entities["FinancialModel"]["m1"]["status"] = "production"
    d = runtime.execute(contract, world, "m1",
                        actor={"claims": {"groups": ["mrm/head"]}},
                        params={"reason": "eol"})
    assert d  # first disjunct true; naive conjunct-splitting would refuse


def test_quoted_and_inside_guard_string_is_safe(lib, world):
    import copy
    contract = copy.deepcopy(lib._CONTRACTS["model_risk.retire_model"])
    contract["guard"]["expression"] = (
        'target.name != "A && B (unbalanced" && target.status == "production"')
    d = runtime.execute(contract, world, "m1",
                        actor={"claims": {"groups": ["mrm/head"]}},
                        params={"reason": "eol"})
    assert not d
    assert d.refusal["failed_clause"]  # labelled, not crashed


def test_fanout_effect_contract_is_refused_before_any_write(lib, world):
    import copy
    contract = copy.deepcopy(lib._CONTRACTS["model_risk.submit_for_validation"])
    contract["target"] = {"entity": "model_risk.TradingDesk", "keys": ["desk_id"]}
    contract["guard"]["expression"] = 'target.name != ""'
    contract["effects"] = [{"path": "target.models.status", "value": "draft"}]
    before = dict(world.entities["FinancialModel"]["m1"])
    d = runtime.execute(contract, world, "rates",
                        actor={"claims": {"groups": ["mrm/model-owners"]}})
    assert not d and "many" in d.refusal["explanation"]
    assert world.entities["FinancialModel"]["m1"] == before  # nothing applied


def test_approval_when_error_refuses_not_raises(lib, world):
    import copy
    contract = copy.deepcopy(lib._CONTRACTS["model_risk.retire_model"])
    contract["approval"] = {
        "when": "target.ghost_property > 1",
        "authority": {"role": "model_risk.head_of_model_risk",
                      "claims": {"groups": "mrm/head"}}}
    world.entities["FinancialModel"]["m1"]["status"] = "production"
    d = runtime.execute(contract, world, "m1",
                        actor={"claims": {"groups": ["mrm/head"]}},
                        params={"reason": "eol"})
    assert not d and d.refusal["failed_clause"] == "approval.when"


def test_self_approval_is_refused(lib, world):
    world.add("ModelChange", "c2", category="methodology",
              submitted_date="2026-07-01").link("applies_to", "c2", "m1")
    both = {"name": "otto", "claims": {"groups": ["mrm/officers", "mrm/head"]}}
    d = lib.approve_model_change(world, "c2", actor=both, approver=both)
    assert not d and "four-eyes" in d.refusal["explanation"]


def test_hostile_description_cannot_break_generated_source():
    doc = yaml.safe_load(MODULE.read_text())
    doc["actions"]["retire_model"]["annotations"]["description"] = (
        '"""\nimport os  # smuggled\n"""')
    source = pylib.emit(doc, generate(doc))
    compile(source, "<probe>", "exec")
    assert "smuggled" not in source.split("json.loads")[0]  # not top-level code


def test_colliding_action_and_accessor_names_refuse_to_emit():
    doc = yaml.safe_load(MODULE.read_text())
    doc["actions"]["get_financial_model"] = {
        "target": "FinancialModel", "guard": 'target.status == "draft"',
        "authority": "model_owner", "audit": "none",
        "effects": [{"target.status": "in_validation"}]}
    with pytest.raises(pylib.EmitError):
        pylib.emit(doc, generate(doc))


def test_optional_params_are_emitted_after_required():
    doc = yaml.safe_load(MODULE.read_text())
    doc["actions"]["retire_model"]["parameters"] = {
        "note": {"type": "string", "optional": True},
        "reason": {"type": "string"}}
    source = pylib.emit(doc, generate(doc))
    compile(source, "<probe>", "exec")
    assert "reason, note=None" in source
