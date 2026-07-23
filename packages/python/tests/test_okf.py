"""The OKF emitter: the generated bundle is a golden, and it is internally sound.

Golden equality is checked file by file, with a parity check that the generated
set and the golden set match exactly, across two fixtures: model_risk (the full
domain) and okf_edge (a small module that exercises the branches model_risk
does not). Beyond the goldens, three properties hold for any emitted bundle: it
is deterministic, every relative markdown link resolves to another file in the
bundle, and every file's frontmatter parses as YAML with the OKF-required
`type`. A final group covers the safety fixes: reserved-name refusal, fence
breakout, and cell escaping.
"""

import copy
import posixpath
import re
from pathlib import Path

import pytest
import yaml

from arkhelang.contracts import generate
from arkhelang.emitters import okf

TESTS = Path(__file__).resolve().parent
REPO_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"

MODEL_RISK = REPO_FIXTURES / "model_risk" / "model-risk.arkhe.yaml"
MODEL_RISK_OKF = REPO_FIXTURES / "model_risk" / "expected" / "okf"
OKF_EDGE = TESTS / "fixtures" / "okf_edge" / "catalogue.arkhe.yaml"
OKF_EDGE_OKF = TESTS / "fixtures" / "okf_edge" / "expected" / "okf"

FIXTURES = {
    "model_risk": (MODEL_RISK, MODEL_RISK_OKF),
    "okf_edge": (OKF_EDGE, OKF_EDGE_OKF),
}

_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_FENCE = re.compile(r"```.*?```", re.DOTALL)


def _emit(module: Path) -> dict[str, str]:
    doc = yaml.safe_load(module.read_text())
    return okf.emit(doc, generate(doc))


def _golden_files(golden: Path) -> list[str]:
    return sorted(p.relative_to(golden).as_posix() for p in golden.rglob("*.md"))


def _golden_cases() -> list[tuple[str, str]]:
    cases = []
    for name, (_, golden) in FIXTURES.items():
        for rel in _golden_files(golden):
            cases.append((name, rel))
    return cases


@pytest.mark.parametrize("fixture,rel", _golden_cases())
def test_generated_file_matches_golden(fixture, rel):
    module, golden = FIXTURES[fixture]
    bundle = _emit(module)
    assert rel in bundle, f"{rel} is a golden but was not generated"
    assert bundle[rel] == (golden / rel).read_text()


@pytest.mark.parametrize("fixture", FIXTURES)
def test_generated_set_equals_golden_set(fixture):
    module, golden = FIXTURES[fixture]
    assert set(_emit(module)) == set(_golden_files(golden))


@pytest.mark.parametrize("fixture", FIXTURES)
def test_emission_is_deterministic(fixture):
    module, _ = FIXTURES[fixture]
    assert _emit(module) == _emit(module)


@pytest.mark.parametrize("fixture", FIXTURES)
def test_every_relative_link_resolves_to_a_generated_file(fixture):
    module, _ = FIXTURES[fixture]
    bundle = _emit(module)
    files = set(bundle)
    for rel, content in bundle.items():
        prose = _FENCE.sub("", content)
        base = posixpath.dirname(rel)
        for target in _LINK.findall(prose):
            assert "://" not in target and not target.startswith("#"), (
                f"{rel}: unexpected non-relative link {target}")
            resolved = posixpath.normpath(posixpath.join(base, target))
            assert resolved in files, (
                f"{rel}: link {target} resolves to {resolved}, not in bundle")


@pytest.mark.parametrize("fixture", FIXTURES)
def test_every_frontmatter_parses_as_yaml_with_type(fixture):
    module, _ = FIXTURES[fixture]
    for rel, content in _emit(module).items():
        assert content.startswith("---\n"), f"{rel}: no frontmatter"
        _, front, _ = content.split("---\n", 2)
        meta = yaml.safe_load(front)
        assert isinstance(meta, dict), f"{rel}: frontmatter is not a mapping"
        assert meta.get("type"), f"{rel}: OKF requires a type"


@pytest.mark.parametrize("fixture", FIXTURES)
def test_no_em_dashes_in_generated_markdown(fixture):
    module, _ = FIXTURES[fixture]
    em_dash = chr(0x2014)
    for content in _emit(module).values():
        assert em_dash not in content


# --- Reserved-name refusal --------------------------------------------------

def _catalogue_doc() -> dict:
    return yaml.safe_load(OKF_EDGE.read_text())


def test_reserved_lowercase_index_name_is_refused():
    doc = _catalogue_doc()
    doc["links"]["index"] = {
        "from": "Book", "to": "Author", "cardinality": "many_to_one"}
    with pytest.raises(okf.EmitError) as exc:
        okf.emit(doc, generate(doc))
    assert "index" in str(exc.value)


def test_reserved_capitalized_index_name_is_refused():
    doc = _catalogue_doc()
    doc["entities"]["Index"] = {
        "keys": ["index_id"], "properties": {"index_id": {"type": "string"}}}
    with pytest.raises(okf.EmitError) as exc:
        okf.emit(doc, generate(doc))
    assert "Index" in str(exc.value)


# --- Fence breakout ---------------------------------------------------------

def _extract_fenced_block(action_md: str) -> str:
    """Recover the guard content from a rendered action, honouring a fence of
    any backtick length, so a naive three-backtick split cannot pass by
    accident."""
    lines = action_md.splitlines()
    open_at = next(
        i for i, line in enumerate(lines) if re.fullmatch(r"`{3,}text", line))
    fence_len = len(lines[open_at]) - len("text")
    close_at = next(
        i for i in range(open_at + 1, len(lines))
        if re.fullmatch(r"`{%d,}" % fence_len, lines[i]))
    return "\n".join(lines[open_at + 1:close_at])


def test_guard_with_backtick_run_stays_inside_a_longer_fence():
    doc = _catalogue_doc()
    contracts = generate(doc)
    payload = 'target.title == "a```b" && target.status == "draft"'
    contracts["catalogue.publish_book"]["guard"]["expression"] = payload
    bundle = okf.emit(doc, contracts)
    action = bundle["actions/publish_book.md"]
    # A run of three backticks forces a four-backtick fence.
    assert "````text" in action
    assert _extract_fenced_block(action) == payload


def test_fenced_helper_grows_the_fence_past_the_longest_run():
    assert okf._fenced("no ticks here") == ["```text", "no ticks here", "```"]
    assert okf._fenced("a `` b")[0] == "```text"
    assert okf._fenced("a ``` b")[0] == "````text"
    assert okf._fenced("`````")[0] == "``````text"


# --- Cell escaping ----------------------------------------------------------

def test_cell_escapes_markdown_significant_characters():
    assert okf._cell("a|b`c[d]e") == "a\\|b\\`c\\[d\\]e"


def test_cell_flattens_newlines_to_spaces():
    assert okf._cell("line one\nline two\r\nthree") == "line one line two three"


def test_cell_escapes_backslash_first():
    assert okf._cell("a\\b") == "a\\\\b"


def test_hostile_synonym_routes_through_cell_in_the_aka_line():
    doc = _catalogue_doc()
    doc["entities"]["Book"]["annotations"]["synonyms"] = "a|b`c[d]e"
    book = okf.emit(doc, generate(doc))["entities/Book.md"]
    assert "Also known as: a\\|b\\`c\\[d\\]e." in book


def test_hostile_synonym_routes_through_cell_in_the_property_table():
    doc = _catalogue_doc()
    doc["entities"]["Book"]["properties"]["title"]["annotations"] = {
        "synonyms": "a|b"}
    book = okf.emit(doc, generate(doc))["entities/Book.md"]
    title_row = next(
        line for line in book.splitlines() if line.startswith("| `title`"))
    # The pipe is escaped, so it cannot open a spurious table column.
    assert "a\\|b" in title_row
    assert "a|b" not in title_row.replace("a\\|b", "")
