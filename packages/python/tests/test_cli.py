"""CLI behaviour: help, version, source locations in findings."""

from pathlib import Path

from arkhelang.cli import main
from arkhelang.validate import validate_file

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


def test_bare_invocation_prints_help(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "examples:" in out and "exit codes:" in out and "finding codes:" in out


def test_version_flag(capsys):
    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    assert capsys.readouterr().out.startswith("arkhe ")


def test_findings_carry_source_locations():
    result = validate_file(FIXTURES / "invalid" / "state_without_initial.arkhe.yaml")
    assert not result.ok
    finding = result.findings[0]
    assert finding.line is not None and finding.column is not None
    assert "missing required field 'initial'" in finding.message


def test_valid_module_exit_zero(capsys):
    path = str(FIXTURES / "model_risk" / "model-risk.arkhe.yaml")
    assert main(["validate", path]) == 0
    assert "valid" in capsys.readouterr().out
