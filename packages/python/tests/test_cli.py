"""CLI behaviour: help, version, source locations in findings, okf emit."""

from pathlib import Path

import yaml

from arkhelang.cli import main
from arkhelang.emitters import okf
from arkhelang.validate import validate_file

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
CATALOGUE = (Path(__file__).resolve().parent / "fixtures" / "okf_edge"
             / "catalogue.arkhe.yaml")


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


# --- okf emit: manifest-guarded pruning and EmitError -----------------------

def _emit_okf(out_dir, module=CATALOGUE):
    return main(["emit", str(module), "--target=okf", "--out", str(out_dir)])


def test_okf_emit_writes_bundle_and_manifest(tmp_path, capsys):
    out = tmp_path / "bundle"
    assert _emit_okf(out) == 0
    assert (out / "index.md").exists()
    assert (out / okf.MANIFEST_NAME).exists()
    manifest = [line for line in (out / okf.MANIFEST_NAME).read_text().splitlines()
                if line]
    on_disk = sorted(
        p.relative_to(out).as_posix() for p in out.rglob("*.md"))
    assert manifest == on_disk


def test_okf_emit_prunes_only_files_it_owns(tmp_path):
    out = tmp_path / "bundle"
    assert _emit_okf(out) == 0
    assert (out / "roles" / "auditor.md").exists()

    # A file the manifest does not list must survive a re-emit.
    keeper = out / "notes.md"
    keeper.write_text("hand-written, not ours\n")

    # Drop a role so its file is no longer in the bundle, then re-emit.
    doc = yaml.safe_load(CATALOGUE.read_text())
    del doc["roles"]["auditor"]
    trimmed = tmp_path / "trimmed.arkhe.yaml"
    trimmed.write_text(yaml.safe_dump(doc))
    assert _emit_okf(out, trimmed) == 0

    assert not (out / "roles" / "auditor.md").exists()
    assert keeper.exists()


def test_okf_emit_refuses_unmanaged_directory(tmp_path, capsys):
    out = tmp_path / "bundle"
    out.mkdir()
    stray = out / "stray.md"
    stray.write_text("someone else owns this\n")
    assert _emit_okf(out) == 1
    err = capsys.readouterr().err
    assert "cannot emit" in err and okf.MANIFEST_NAME in err
    assert stray.read_text() == "someone else owns this\n"


def test_okf_emit_exit_one_on_reserved_name(tmp_path, capsys):
    doc = yaml.safe_load(CATALOGUE.read_text())
    doc["entities"]["Index"] = {
        "keys": ["index_id"], "properties": {"index_id": {"type": "string"}}}
    module = tmp_path / "reserved.arkhe.yaml"
    module.write_text(yaml.safe_dump(doc))
    assert _emit_okf(tmp_path / "out", module) == 1
    assert "cannot emit" in capsys.readouterr().err
