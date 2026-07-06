"""The panel editor's field descriptors must track the widget schemas.

Run:  uv run --with pillow --with numpy --with voluptuous --with resvg-py --with pytest pytest
"""

from __future__ import annotations

from conftest import load

editor = load("screens_editor")
schema = load("render.schema")

FIELD_TYPES = {"text", "textarea", "number", "bool", "select", "entity", "entity_list"}


def test_every_widget_type_has_editor_fields() -> None:
    assert set(editor.WIDGET_FIELDS) == set(schema.WIDGET_OPTION_SCHEMAS), (
        "a widget type exists without editor form fields (or vice versa) — "
        "update screens_editor.WIDGET_FIELDS"
    )


def test_descriptor_shape() -> None:
    for wtype, meta in editor.WIDGET_FIELDS.items():
        assert meta["label"], wtype
        for field in meta["fields"]:
            assert field["key"], (wtype, field)
            assert field["type"] in FIELD_TYPES, (wtype, field)
            assert field["label"], (wtype, field)
            if field["type"] == "select":
                assert field["options"], (wtype, field)


def test_editor_field_keys_are_valid_widget_options() -> None:
    """Every editor field key must be accepted by the widget's schema.

    Builds a minimal widget dict per type using each field's default/sample
    value and validates it — catching a renamed or removed option.
    """
    samples = {
        "text": "x",
        "textarea": "{{ 1 }}",
        "number": 1,
        "bool": True,
        "entity": "sensor.test",
        "entity_list": ["sensor.test"],
    }
    for wtype, meta in editor.WIDGET_FIELDS.items():
        widget_schema = schema.WIDGET_OPTION_SCHEMAS[wtype]
        for field in meta["fields"]:
            if field["type"] == "select":
                value = field["options"][0]
            elif field["key"] == "url":
                value = "https://example.com/x.png"
            else:
                value = field.get("default", samples[field["type"]])
            # Field must at least be a known key: voluptuous raises "extra keys
            # not allowed" for unknown ones. Required co-fields are supplied
            # from the same descriptor set.
            payload = {}
            for other in meta["fields"]:
                if other.get("required"):
                    if other["type"] == "select":
                        payload[other["key"]] = other["options"][0]
                    else:
                        payload[other["key"]] = samples[other["type"]]
            payload[field["key"]] = value
            if wtype == "image":
                # The image widget requires exactly one of url/entity.
                if field["key"] == "entity":
                    payload = {"entity": "camera.test"}
                else:
                    payload.setdefault("url", "https://example.com/x.png")
            widget_schema(payload)
