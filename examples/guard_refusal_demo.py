"""The guard-refusal demo: an agent asks, the contract answers.

Run from the repo root after `arkhe emit`:

    arkhe emit fixtures/model_risk/model-risk.arkhe.yaml --out /tmp/model_risk_lib.py
    PYTHONPATH=/tmp python examples/guard_refusal_demo.py

A model with an open high-severity finding is proposed for production. The
guard refuses and names the failing clause. The finding is remediated, the
model revalidated, and the same call succeeds; the state transitions and the
audit event is on the record. Nothing here is prompt engineering; every
refusal is the contract executing.
"""

import json

import model_risk_lib as lib

HEAD = {"name": "maria", "claims": {"groups": ["mrm/head"]}}
VALIDATOR = {"name": "sam", "claims": {"groups": ["mrm/validation"]}}
INTERN = {"name": "kim", "claims": {"groups": ["interns"]}}


def show(title, decision):
    print(f"\n== {title}")
    if decision:
        print("ALLOWED; effects:", json.dumps(decision.effects))
    else:
        r = decision.refusal
        print("REFUSED")
        print("  failed_clause:", r["failed_clause"])
        print("  explanation:  ", r["explanation"])


world = (
    lib.new_world()
    .add("TradingDesk", "rates", name="Rates", business_line="Markets")
    .add("FinancialModel", "irs-pricer", name="IRS Pricer", purpose="pricing",
         tier=1, status="validated", commissioned_date="2024-02-01",
         last_validated="2026-06-30")
    .add("ValidationReview", "rev-7", scope="full", outcome="approved",
         review_date="2026-06-30")
    .add("Finding", "f-42", severity="high", raised_date="2026-06-30")
    .link("owned_by", "irs-pricer", "rates")
    .link("assesses", "rev-7", "irs-pricer")
    .link("raised_in", "f-42", "rev-7")
)

# An intern may not promote a model, whatever the model's state.
show("intern attempts promotion",
     lib.grant_production_use(world, "irs-pricer", actor=INTERN))

# The head of model risk may, but the guard sees the open high finding.
show("head of model risk attempts promotion (open high finding)",
     lib.grant_production_use(world, "irs-pricer", actor=HEAD))

# High findings cannot be waived; the contract structurally refuses.
show("attempt to waive the high finding",
     lib.waive_finding(world, "f-42", justification="deadline pressure",
                       actor={"name": "otto", "claims": {"groups": ["mrm/officers"]}}))

# Remediate properly instead, then promote.
world.entities["Finding"]["f-42"]["status"] = "remediated"
show("promotion after remediation",
     lib.grant_production_use(world, "irs-pricer", actor=HEAD))

print("\nmodel status:", world.entities["FinancialModel"]["irs-pricer"]["status"])
print("audit log:")
for event in world.audit_log:
    print(" ", json.dumps(event))
