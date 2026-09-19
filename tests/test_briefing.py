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


@pytest.mark.parametrize(
    "change",
    [
        {"valid_until": NOW.isoformat()},
        {"generated_at": "2026-09-19T07:00:00"},
        {"valid_until": (NOW + timedelta(hours=1)).isoformat()},
        {"routine": {"label": "Routine", "completed": 4, "skipped": 3, "total": 6}},
        {"weather": {"temperature": float("nan")}},
        {"tasks": [{"title": "x"}] * 4},
    ],
)
def test_invalid_or_expired_snapshots_are_omitted(change):
    assert (
        load("render.briefing").validate_briefing({**snapshot(), **change}, NOW) is None
    )


@pytest.mark.parametrize("locale", ["nb", "en"])
def test_real_compositor_refresh_preserves_artwork_and_deduplicates_timestamps(
    monkeypatch, tmp_path, locale
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
    data = snapshot()
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
    data["routine"].update(completed=3, next_step="Frokost")
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
