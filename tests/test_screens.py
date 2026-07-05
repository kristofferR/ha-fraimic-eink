"""Tests for the subentry-backed screen store (pure, duck-typed entries)."""

from __future__ import annotations

from types import SimpleNamespace

from conftest import load

screens = load("screens")


def _subentry(subentry_id: str, title: str, data: dict, subentry_type: str = "screen"):
    return SimpleNamespace(
        subentry_id=subentry_id, title=title, data=data, subentry_type=subentry_type
    )


def _entry(*subentries):
    return SimpleNamespace(subentries={s.subentry_id: s for s in subentries})


VALID = {
    "layout": "full",
    "widgets": [{"type": "clock", "slot": "main"}],
    "interval": 900,
}


def test_screens_from_entry_parses_valid_and_skips_invalid() -> None:
    entry = _entry(
        _subentry("id1", "Hallway", dict(VALID)),
        _subentry("id2", "Broken", {"layout": "full", "widgets": [{"type": "nope", "slot": "main"}]}),
        _subentry("id3", "Other type", {"anything": 1}, subentry_type="something_else"),
        _subentry("id4", "Picture", {"kind": "picture", "url": "http://example.com/x.png"}),
    )
    result = screens.screens_from_entry(entry)
    assert [s.screen_id for s in result] == ["id1", "id4"]
    hallway = result[0]
    assert hallway.name == "Hallway"  # subentry title wins over data name
    assert hallway.interval == 900
    assert result[1].kind == "picture"


def test_screen_by_key_matches_id_then_name_case_insensitive() -> None:
    entry = _entry(_subentry("abc123", "Gangen", dict(VALID)))
    assert screens.screen_by_key(entry, "abc123").screen_id == "abc123"
    assert screens.screen_by_key(entry, "gangen").screen_id == "abc123"
    assert screens.screen_by_key(entry, "GANGEN").screen_id == "abc123"
    assert screens.screen_by_key(entry, "missing") is None


def test_entry_without_subentries_attribute() -> None:
    assert screens.screens_from_entry(SimpleNamespace()) == []
