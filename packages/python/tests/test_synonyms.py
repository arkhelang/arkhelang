"""Synonyms annotations: validation, contract carriage, and emitter surfacing.

The `synonyms` annotation is a comma-separated list of alternate labels on a
declaration. The validator parses and checks it; contracts carry the parsed
list as structured data; the pylib and OKF emitters surface it as prose.
The okf_edge catalogue fixture declares synonyms across every kind, so these
tests read from it rather than inventing a second module.
"""

import copy
from pathlib import Path

import yaml

from arkhelang.contracts import generate
from arkhelang.emitters import okf, pylib
from arkhelang.model import parse_synonyms
from arkhelang.validate import validate

CATALOGUE = (Path(__file__).resolve().parent / "fixtures" / "okf_edge"
             / "catalogue.arkhe.yaml")


def _doc() -> dict:
    return yaml.safe_load(CATALOGUE.read_text())


# --- Parsing ----------------------------------------------------------------

def test_parse_synonyms_trims_and_keeps_empties_for_the_validator():
    assert parse_synonyms("a, b ,c") == ["a", "b", "c"]
    assert parse_synonyms("a,,b") == ["a", "", "b"]
    assert parse_synonyms(None) == []
    assert parse_synonyms("") == []


# --- Validation -------------------------------------------------------------

def test_catalogue_with_synonyms_is_valid():
    assert validate(_doc()).ok


def _codes(doc: dict) -> set[str]:
    return {f.code for f in validate(doc).findings}


def test_empty_synonym_is_rejected():
    doc = _doc()
    doc["entities"]["Book"]["annotations"]["synonyms"] = "volume,,tome"
    assert "synonym-empty" in _codes(doc)


def test_duplicate_synonym_within_a_declaration_is_rejected():
    doc = _doc()
    doc["entities"]["Book"]["annotations"]["synonyms"] = "volume, volume"
    assert "synonym-duplicate" in _codes(doc)


def test_synonym_colliding_with_a_declared_name_is_rejected():
    doc = _doc()
    doc["entities"]["Book"]["annotations"]["synonyms"] = "Author"
    assert "synonym-collision" in _codes(doc)


def test_synonym_colliding_with_another_declarations_synonym_is_rejected():
    doc = _doc()
    doc["entities"]["Book"]["annotations"]["synonyms"] = "shared"
    doc["entities"]["Author"].setdefault("annotations", {})["synonyms"] = "shared"
    assert "synonym-collision" in _codes(doc)


def test_property_synonym_scope_is_its_own_container():
    # A Book property synonym may equal an Author property name; different scope.
    doc = _doc()
    doc["entities"]["Book"]["properties"]["title"]["annotations"] = {
        "synonyms": "name"}
    assert validate(doc).ok


def test_property_synonym_colliding_with_a_sibling_property_is_rejected():
    doc = _doc()
    doc["entities"]["Book"]["properties"]["title"]["annotations"] = {
        "synonyms": "status"}
    assert "synonym-collision" in _codes(doc)


# --- Contract carriage ------------------------------------------------------

def test_action_and_parameter_synonyms_are_carried():
    c = generate(_doc())["catalogue.publish_book"]
    assert c["synonyms"] == ["release", "go live"]
    assert c["parameters"]["note"]["synonyms"] == ["comment", "remark"]


def test_entity_and_property_synonyms_are_carried_on_the_read_contract():
    c = generate(_doc())["catalogue.Book.get"]
    assert c["synonyms"] == ["volume", "tome"]
    assert c["properties"]["title"]["synonyms"] == ["name", "heading"]
    assert c["properties"]["status"]["synonyms"] == ["state", "phase"]


def test_link_synonyms_are_carried_on_the_traversal():
    c = generate(_doc())["catalogue.Book.get"]
    written_by = next(t for t in c["traversals"] if t["path"] == "written_by")
    assert written_by["synonyms"] == ["authored by", "by"]


def test_a_declaration_without_synonyms_omits_the_key():
    c = generate(_doc())["catalogue.Author.get"]
    assert "synonyms" not in c


# --- Emitter surfacing ------------------------------------------------------

def test_pylib_docstrings_mention_synonyms():
    doc = _doc()
    source = pylib.emit(doc, generate(doc))
    assert "Also known as: release, go live." in source
    assert "Also known as: volume, tome." in source


def test_okf_surfaces_synonyms_as_an_also_known_as_line():
    doc = _doc()
    bundle = okf.emit(doc, generate(doc))
    assert "Also known as: volume, tome." in bundle["entities/Book.md"]
    assert "Also known as: authored by, by." in bundle["links/written_by.md"]
    assert "Also known as: release, go live." in bundle["actions/publish_book.md"]
