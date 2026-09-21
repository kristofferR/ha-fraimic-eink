"""Real snapshot -> entity fetch -> SVG -> panel pixels, including live changes."""

import asyncio
import io
import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
from conftest import load
from PIL import Image
from test_render_display import _install_ha_stubs

NOW = datetime(2026, 9, 19, 7, 0, tzinfo=timezone.utc)


def snapshot():
    return {
        "generated_at": NOW.isoformat(),
        "valid_until": (NOW + timedelta(seconds=120)).isoformat(),
        "locale": "nb",
        "greeting": "God morgen, Kris",
        "date_label": "Lørdag 19. september",
        "agenda": [
            {"title": "Styrketrening", "all_day": True},
            {"title": "Prosjektmøte", "time": "09:30"},
        ],
        "routine": {
            "label": "Morgenrutinen",
            "completed": 2,
            "total": 6,
            "next_step": "Dusj og stell",
        },
        "tasks": [{"title": "Hent pakken"}, {"title": "Bestill tannlegetime"}],
        "focus": {"title": "25 min med prosjektet", "detail": "Din valgte prioritet"},
        "weather": {"temperature": 12},
        "progress": [
            {"label": "Morgenrutine", "value": 2, "max": 6},
            {"label": "Dagens vaner", "value": 1, "max": 4, "color": "blue"},
        ],
    }


def test_empty_ordered_blocks_do_not_validate_hidden_legacy_content():
    raw = snapshot()
    raw.update(blocks=[], progress=[])
    raw.pop("weather")
    assert load("render.briefing").validate_briefing(raw, NOW) is None
    # HA can legitimately enrich an empty shared brief with weather alone.
    raw["weather"] = {"temperature": 12}
    assert load("render.briefing").validate_briefing(raw, NOW) is not None


@pytest.mark.parametrize("locale,finished", [("en", "Finished"), ("nb", "Ferdig")])
def test_overflow_routine_without_next_step_shows_finished(locale, finished):
    raw = ordered_snapshot()
    routine = raw["blocks"].pop(1)
    routine.pop("next_step")
    raw["blocks"].append(routine)
    raw["locale"] = locale
    data = load("render.briefing").validate_briefing(raw, NOW)
    doc = load("render.svg").SvgDoc(2560, 1440, "#ffffff")
    load("render.widgets.briefing").render_briefing(
        doc, load("render.layout").Rect(0, 0, 2560, 1440), {}, data, None, None
    )
    assert f">{finished}</text>" in doc.to_string()


@pytest.mark.parametrize(
    "locale,label", [("en", "Today's focus"), ("nb", "Dagens fokus")]
)
def test_overflow_focus_without_label_uses_localized_default(locale, label):
    raw = ordered_snapshot()
    raw["blocks"][-1].pop("label")
    raw["locale"] = locale
    data = load("render.briefing").validate_briefing(raw, NOW)
    doc = load("render.svg").SvgDoc(2560, 1440, "#ffffff")
    load("render.widgets.briefing").render_briefing(
        doc, load("render.layout").Rect(0, 0, 2560, 1440), {}, data, None, None
    )
    assert f">{label}</text>" in doc.to_string()


def ordered_snapshot():
    source = snapshot()
    return {
        **{
            key: source[key]
            for key in (
                "generated_at",
                "valid_until",
                "locale",
                "greeting",
                "date_label",
            )
        },
        "blocks": [
            {
                "type": "tasks",
                "label": "Din prioritet",
                "color": "blue",
                "items": [{"title": "Priority first"}],
            },
            {"type": "routine", **source["routine"]},
            {
                "type": "agenda",
                "label": "Avtaler",
                "items": [{"title": "Appointment third", "all_day": True}],
            },
            {
                "type": "agenda",
                "label": "Trening",
                "color": "green",
                "items": [
                    {"title": "Workout fourth", "time": "10:30", "icon": "mdi:dumbbell"}
                ],
            },
            {
                "type": "focus",
                "label": "Fra i går",
                "title": "Achievement fifth",
                "icon": "mdi:trophy-outline",
                "color": "green",
            },
            {
                "type": "focus",
                "label": "Søvn",
                "title": "Sleep sixth",
                "icon": "mdi:weather-night",
            },
        ],
    }


@pytest.mark.parametrize("with_progress", [False, True])
def test_ordered_blocks_keep_all_six_groups_and_do_not_extend_freshness(with_progress):
    raw = ordered_snapshot()
    if with_progress:
        raw["progress"] = snapshot()["progress"]
    data = load("render.briefing").validate_briefing(raw, NOW)
    assert data is not None
    svg = load("render.svg")
    doc = svg.SvgDoc(2560, 1440, "#ffffff")
    load("render.widgets.briefing").render_briefing(
        doc, load("render.layout").Rect(0, 0, 2560, 1440), {}, data, None, None
    )
    rendered = doc.to_string()
    titles = [
        "Priority first",
        "Dusj og stell",
        "Appointment third",
        "Workout fourth",
        "Achievement fifth",
        "Sleep sixth",
    ]
    positions = [rendered.index(title) for title in titles]
    assert positions == sorted(positions)
    assert "#5080b8" in rendered and "#608050" in rendered
    if with_progress:
        from xml.etree import ElementTree

        root = ElementTree.fromstring(rendered)
        text_y = {
            node.text: float(node.attrib["y"])
            for node in root.iter("{http://www.w3.org/2000/svg}text")
        }
        assert text_y["Achievement fifth"] < text_y["Dagens vaner"] < 1440
        assert text_y["Workout fourth"] < text_y["Achievement fifth"]
    assert (
        load("render.briefing").validate_briefing(
            ordered_snapshot(), NOW + timedelta(seconds=120)
        )
        is None
    )
    raw = ordered_snapshot()
    raw["blocks"][1]["skipped"] = 6
    assert load("render.briefing").validate_briefing(raw, NOW) is None


@pytest.mark.parametrize(
    "change",
    [
        {"valid_until": NOW.isoformat()},
        {"generated_at": "2026-09-19T07:00:00"},
        {"valid_until": (NOW + timedelta(hours=1)).isoformat()},
        {"routine": {"label": "Routine", "completed": 4, "skipped": 3, "total": 6}},
        {"weather": {"temperature": float("nan")}},
        {"tasks": [{"title": "x"}] * 13},
    ],
)
def test_invalid_or_expired_snapshots_are_omitted(change):
    assert (
        load("render.briefing").validate_briefing({**snapshot(), **change}, NOW) is None
    )


@pytest.mark.parametrize("locale", ["nb", "en"])
@pytest.mark.parametrize("ordered", [False, True])
def test_real_compositor_refresh_preserves_artwork_and_deduplicates_timestamps(
    monkeypatch, tmp_path, locale, ordered
):
    _install_ha_stubs(monkeypatch)
    storage = ModuleType("homeassistant.helpers.storage")
    storage.Store = object
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.storage", storage)
    for name in ("fraimic.overlays", "fraimic.render.fetch"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    overlays = load("overlays")
    fetch = load("render.fetch")
    monkeypatch.setattr(fetch.dt_util, "now", lambda: NOW)
    monkeypatch.setattr(overlays.dt_util, "now", lambda: NOW)
    data = ordered_snapshot() if ordered else snapshot()
    data["locale"] = locale
    state = SimpleNamespace(state="ready", attributes={"brief": data})

    async def executor(fn, *args):
        return fn(*args)

    hass = SimpleNamespace(
        data={},
        config=SimpleNamespace(language=locale),
        states=SimpleNamespace(get=lambda _: state),
        async_add_executor_job=executor,
    )
    entry = SimpleNamespace(
        entry_id="large", data={"width": 1440, "height": 2560}, options={"rotation": 90}
    )
    base = Image.new("RGB", (2560, 1440), (80, 128, 184))
    out = io.BytesIO()
    base.save(out, format="PNG")
    spec = [
        overlays.normalize_overlay(
            {
                "id": "morning",
                "type": "briefing",
                "options": {"entity": "sensor.morning"},
            }
        )
    ]

    async def render():
        deadlines = []
        png, _ = await overlays.async_apply_frame_overlays(
            hass,
            entry,
            out.getvalue(),
            None,
            overlays=spec,
            snapshot_deadlines=deadlines,
        )
        return png, deadlines

    first, deadlines = asyncio.run(render())
    assert deadlines == [(NOW + timedelta(seconds=120)).timestamp()]
    data["generated_at"] = (NOW + timedelta(seconds=10)).isoformat()
    data["valid_until"] = (NOW + timedelta(seconds=130)).isoformat()
    assert asyncio.run(render())[0] == first
    (data["blocks"][1] if ordered else data["routine"]).update(
        completed=3, next_step="Frokost"
    )
    second, _ = asyncio.run(render())
    assert first != second
    before = np.array(Image.open(io.BytesIO(first)))[:800, :, :3]
    after = np.array(Image.open(io.BytesIO(second)))[:800, :, :3]
    assert np.array_equal(before, np.array(base)[:800])
    assert np.array_equal(before, after)
    converter = load("image_convert")
    packed, _, _ = converter.convert_image(
        second, width=1440, height=2560, rotate=90, mode="none", preprocess=False
    )
    assert len(packed) == 2304000
    decoded = converter.bin_to_png(packed, 1440, 2560, 270)
    assert np.array_equal(
        np.array(Image.open(io.BytesIO(decoded)))[:, :, :3],
        np.array(Image.open(io.BytesIO(second)))[:, :, :3],
    )
    state.attributes = {"brief": {**data, "valid_until": NOW.isoformat()}}
    clean, deadlines = asyncio.run(render())
    assert deadlines == []
    assert np.array_equal(
        np.array(Image.open(io.BytesIO(clean)))[:, :, :3], np.array(base)
    )
    state.state = "unavailable"
    assert asyncio.run(render())[0] == clean


@pytest.mark.parametrize("layout", ["strip", "overview", "side_panel"])
def test_selectable_layouts_render_the_supplied_guidance(layout):
    raw = ordered_snapshot()
    raw["guidance"] = {
        "title": "Start med ett steg",
        "body": "Gjør det viktigste først.",
        "action": "Gå en tur",
    }
    data = load("render.briefing").validate_briefing(raw, NOW)
    doc = load("render.svg").SvgDoc(2560, 1440, "#ffffff")
    load("render.widgets.briefing").render_briefing(
        doc,
        load("render.layout").Rect(0, 0, 2560, 1440),
        {"layout": layout},
        data,
        None,
        None,
    )
    svg = doc.to_string()
    assert "VEILEDER" not in svg
    assert "Start med ett steg" in svg
    assert "Gjør det viktigste først." in svg
    assert "Gå en tur" in svg
    assert "Priority first" in svg
    assert "Sleep sixth" in svg
    assert (
        load("render.briefing").validate_briefing(raw, NOW + timedelta(minutes=3))
        is None
    )


def test_guidance_can_be_headline_only_but_not_entirely_blank():
    raw = {
        **ordered_snapshot(),
        "blocks": [],
        "guidance": {"title": "Ett steg", "body": "  "},
    }
    data = load("render.briefing").validate_briefing(raw, NOW)
    assert data["guidance"]["title"] == "Ett steg"
    assert data["guidance"]["body"] == ""
    raw["guidance"]["title"] = " "
    assert load("render.briefing").validate_briefing(raw, NOW) is None


@pytest.mark.parametrize("layout", ["strip", "overview", "side_panel"])
def test_dense_layout_shows_twelve_tasks_and_next_with_guidance(layout):
    raw = ordered_snapshot()
    raw["blocks"] = [
        {
            "type": "focus",
            "label": "Neste",
            "title": "En konkret handling",
            "detail": "Fra Today",
        },
        {
            "type": "tasks",
            "label": "Oppgaver",
            "items": [{"title": f"Oppgave {index:02d}"} for index in range(1, 13)],
        },
    ]
    raw["guidance"] = {"title": "Ett steg", "body": "Gjør det viktigste først."}
    raw["blocks"].extend(
        [
            {
                "type": "agenda",
                "label": "Dagen din",
                "items": [
                    {"title": "Prosjektmøte", "time": "09:30"},
                    {"title": "Styrke", "all_day": True},
                ],
            },
            {
                "type": "focus",
                "label": "Dagens fokus",
                "title": "Les litt",
                "detail": "Din valgte bok",
            },
        ]
    )
    raw["progress"] = [
        {"label": "Vaner", "value": 2, "max": 5},
        {"label": "Læring", "value": 5, "max": 15, "unit": "min"},
    ]
    data = load("render.briefing").validate_briefing(raw, NOW)
    assert data is not None
    doc = load("render.svg").SvgDoc(2560, 1440, "#ffffff")
    load("render.widgets.briefing").render_briefing(
        doc,
        load("render.layout").Rect(0, 0, 2560, 1440),
        {"layout": layout},
        data,
        None,
        None,
    )
    svg = doc.to_string()
    for index in range(1, 13):
        assert f"Oppgave {index:02d}" in svg
    from xml.etree import ElementTree

    text_nodes = list(
        ElementTree.fromstring(svg).iter("{http://www.w3.org/2000/svg}text")
    )
    rendered_text = " ".join(node.text or "" for node in text_nodes)
    assert "NESTE" not in rendered_text and "VEILEDER" not in rendered_text
    assert "En konkret handling" in rendered_text
    date = next(node for node in text_nodes if (node.text or "").startswith("Lør."))
    next_title = next(
        node for node in text_nodes if (node.text or "").startswith("En konkret")
    )
    assert date.attrib["y"] == next_title.attrib["y"]
    for content in (
        "Prosjektmøte",
        "09:30",
        "Styrke",
        "Les litt",
        "Din valgte bok",
        "Fra Today",
        "Vaner",
        "2/5",
        "Læring",
        "5/15",
    ):
        assert content in svg
    raw["blocks"][1]["items"].append({"title": "Too many"})
    assert load("render.briefing").validate_briefing(raw, NOW) is None


@pytest.mark.parametrize("layout", ["strip", "overview", "side_panel"])
@pytest.mark.parametrize("task_count", [3, 12])
@pytest.mark.parametrize("overflow", [False, True])
@pytest.mark.parametrize("guidance_repeats", [1, 8])
def test_rich_briefing_text_stays_on_canvas_without_collisions(
    layout, task_count, overflow, guidance_repeats
):
    from xml.etree import ElementTree

    raw = ordered_snapshot()
    raw["weekly_focus"] = {"text": "Gjør plass til det viktigste", "done": False}
    raw["updated_time"] = "08:30"
    raw["guidance"] = {
        "title": "Gjør starten liten. La resten komme etterpå.",
        "body": "Velg ett konkret steg før du åpner resten av dagen. Du trenger ikke fullføre hele listen for å få en god start. Ta deg tid til å gjøre ferdig én ting før du går videre.",
        "action": "Ta ett konkret steg.",
    }
    raw["guidance"]["body"] = " ".join([raw["guidance"]["body"]] * guidance_repeats)
    raw["blocks"] = [
        {
            "type": "focus",
            "label": "Neste",
            "title": "Sett av 20 minutter til dagens viktigste oppgave",
            "detail": "Begynn med én oppgave og gjør den ferdig.",
        },
        {
            "type": "agenda",
            "label": "Dagen din",
            "items": [
                {"title": "Prosjektmøte", "time": "09:30"},
                {"title": "Styrketrening", "time": "17:30"},
            ],
        },
        {
            "type": "tasks",
            "label": "Dine oppgaver",
            "items": [
                {
                    "title": f"Avtal neste ukes aktivitet {index}",
                    "priority": index == 0,
                    "deadline": "I dag",
                }
                for index in range(task_count)
            ],
        },
        {
            "type": "focus",
            "label": "Dagens fokus",
            "title": "25 min med prosjektet",
            "detail": "Én uforstyrret økt",
        },
    ]
    if overflow:
        raw["blocks"] = [raw["blocks"][0], raw["blocks"][2]] + [
            {
                "type": "focus",
                "label": "Fokus",
                "title": "En lang overskrift som trenger to linjer med tekst",
                "detail": "Detaljer som også bruker god plass på skjermen og trenger flere linjer",
            }
            for _ in range(6)
        ]
    raw["progress"] = [
        {"label": "Mobilitet", "value": 4, "max": 9},
        {"label": "Læring", "value": 5, "max": 15, "unit": "min"},
        {"label": "Vaner", "value": 2, "max": 5},
    ]
    svg = load("render.svg")
    doc = svg.SvgDoc(2560, 1440, "#ffffff")
    load("render.widgets.briefing").render_briefing(
        doc,
        load("render.layout").Rect(0, 0, 2560, 1440),
        {"layout": layout},
        load("render.briefing").validate_briefing(raw, NOW),
        None,
        None,
    )
    rendered_text = " ".join(
        node.text or ""
        for node in ElementTree.fromstring(doc.to_string()).iter(
            "{http://www.w3.org/2000/svg}text"
        )
    )
    assert raw["guidance"]["body"] in rendered_text
    boxes = []
    for node in ElementTree.fromstring(doc.to_string()).iter(
        "{http://www.w3.org/2000/svg}text"
    ):
        content = node.text or ""
        if not content.strip():
            continue
        size, weight = (
            int(node.attrib["font-size"]),
            int(node.attrib.get("font-weight", 400)),
        )
        font = svg._pil_font(size, weight)
        x, y = float(node.attrib["x"]), float(node.attrib["y"])
        if node.attrib.get("text-anchor") == "end":
            x -= svg.measure(content, size, weight)
        left, top, right, bottom = font.getbbox(content, anchor="ls")
        box = (x + left, y + top, x + right, y + bottom)
        assert 0 <= box[0] < box[2] <= 2560 and 0 <= box[1] < box[3] <= 1440, content
        for other, other_content in boxes:
            assert min(box[2], other[2]) <= max(box[0], other[0]) or min(
                box[3], other[3]
            ) <= max(box[1], other[1]), (content, other_content)
        boxes.append((box, content))


def test_rich_routine_counts_and_fractional_progress_are_preserved():
    from xml.etree import ElementTree

    raw = snapshot()
    raw["updated_time"] = "09:00"
    raw["routine"]["skipped"] = 1
    raw["progress"] = [{"label": "Delvis", "value": 2.5, "max": 5}]
    doc = load("render.svg").SvgDoc(2560, 1440, "#ffffff")
    load("render.widgets.briefing").render_briefing(
        doc,
        load("render.layout").Rect(0, 0, 2560, 1440),
        {"layout": "strip"},
        load("render.briefing").validate_briefing(raw, NOW),
        None,
        None,
    )
    svg = doc.to_string()
    assert "2/6 fullført · 1 hoppet over" in svg
    assert "2.5/5" in svg
    rects = list(ElementTree.fromstring(svg).iter("{http://www.w3.org/2000/svg}rect"))
    # The final meter is continuous, and its inner fill is exactly half its track.
    track, fill = rects[-2:]
    assert abs(float(fill.attrib["width"]) * 2 - float(track.attrib["width"])) <= 1


@pytest.mark.parametrize("layout", ["strip", "overview", "side_panel"])
@pytest.mark.parametrize("agenda_count", [1, 3])
def test_progress_uses_agenda_space_or_a_readable_right_column(layout, agenda_count):
    from xml.etree import ElementTree

    raw = ordered_snapshot()
    raw["updated_time"] = "08:30"
    raw["blocks"] = [
        {
            "type": "agenda",
            "label": "I dag",
            "items": [
                {"title": f"Avtale {index}", "time": "09:30"}
                for index in range(agenda_count)
            ],
        },
        {
            "type": "tasks",
            "label": "Oppgaver",
            "items": [{"title": f"Oppgave {index}"} for index in range(3)],
        },
    ]
    raw["progress"] = [{"label": "Vaner", "value": 0, "max": 2}]
    doc = load("render.svg").SvgDoc(2560, 1440, "#ffffff")
    load("render.widgets.briefing").render_briefing(
        doc,
        load("render.layout").Rect(0, 0, 2560, 1440),
        {"layout": layout},
        load("render.briefing").validate_briefing(raw, NOW),
        None,
        None,
    )
    nodes = {
        node.text: node.attrib
        for node in ElementTree.fromstring(doc.to_string()).iter(
            "{http://www.w3.org/2000/svg}text"
        )
    }
    habits, task = nodes["Vaner"], nodes["Oppgave 0"]
    # A short agenda has room underneath; a full agenda uses the right column.
    assert (float(habits["x"]) < float(task["x"])) == (agenda_count == 1)
    assert float(habits["y"]) <= float(nodes["Oppgave 2"]["y"])
    assert all(f"Oppgave {index}" in nodes for index in range(3))
    if agenda_count == 1:
        assert float(habits["y"]) > float(nodes["Avtale 0"]["y"])
