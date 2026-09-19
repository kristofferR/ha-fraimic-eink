"""Colour/icon morning strip over retained artwork (approved layout A)."""

from __future__ import annotations

import math

from ..icons import icon_path
from ..svg import truncate, wrap
from ..theme import PALETTE_HEX

LABELS = {
    "nb": {
        "agenda": "Dagen din",
        "tasks": "Husk",
        "focus": "Dagens fokus",
        "next": "Neste steg",
        "done": "Fullført",
        "finished": "Ferdig",
        "skipped": "hoppet over",
        "today": "I dag",
    },
    "en": {
        "agenda": "Your day",
        "tasks": "Remember",
        "focus": "Today's focus",
        "next": "Next step",
        "done": "Completed",
        "finished": "Finished",
        "skipped": "skipped",
        "today": "All day",
    },
}


def render_briefing(doc, rect, options, data, ctx, theme):
    if not data or data.get("empty") or "error" in data:
        return
    labels = LABELS[data["locale"]]
    ink, white = PALETTE_HEX["black"], PALETTE_HEX["white"]
    scale = rect.w / 100
    px = lambda n: round(n * scale)
    blocks = (
        [(block["type"], block) for block in data["blocks"]]
        if "blocks" in data
        else [
            (k, data[k]) for k in ("agenda", "routine", "tasks", "focus") if data.get(k)
        ]
    )
    overflow = blocks[4:]
    blocks = blocks[:4]
    progress = data.get("progress", [])
    height = px(24.2 if progress or overflow else 20.3 if len(blocks) >= 3 else 18)
    if progress and overflow:
        height += px(5.25)
    top = rect.y + rect.h - height
    left, right = rect.x + px(2.4), rect.x + rect.w - px(2.4)
    doc.rect(rect.x, top, rect.w, height, white)
    doc.rect(rect.x, top, rect.w, px(0.35), PALETTE_HEX["blue"])

    def text(x, y, value, size=1.35, weight=400, width=None, color=ink, anchor="start"):
        value = str(value)
        if width is not None:
            value = truncate(value, width, px(size), weight)
        doc.text(x, y, value, size=px(size), fill=color, weight=weight, anchor=anchor)

    def icon(name, x, y, size=2, color="blue", tile=False):
        fill = PALETTE_HEX[color]
        if tile:
            doc.rect(x, y, px(size), px(size), fill, rx=px(0.25))
            fg = ink if color == "yellow" else white
            doc.icon(
                icon_path(name),
                x + px(size * 0.17),
                y + px(size * 0.17),
                px(size * 0.66),
                fg,
            )
        else:
            doc.icon(icon_path(name), x, y, px(size), fill)

    def tag(x, y, title, color, width):
        doc.rect(x, y - px(0.85), px(0.45), px(0.9), PALETTE_HEX[color])
        text(x + px(1), y, title.upper(), 1.02, 700, width - px(1))

    weather = data.get("weather")
    date_right = right
    if weather:
        value = f"{weather['temperature']:g}{weather['unit']}"
        text(right, top + px(3.65), value, 1.75, 600, anchor="end")
        icon(weather["icon"], right - px(9.2), top + px(1.45), 2.5, "black")
        date_right -= px(11)
    text(left, top + px(3.7), data["greeting"], 2.55, 700, px(48))
    text(
        date_right, top + px(3.55), data["date_label"], 1.25, width=px(32), anchor="end"
    )
    y = top + px(6.25)
    gap = px(2.1)
    count = max(1, len(blocks))
    width = (right - left - gap * (count - 1)) / count
    for index, (kind, value) in enumerate(blocks):
        x = round(left + index * (width + gap))
        w = round(width)
        if kind == "agenda":
            ordered = isinstance(value, dict)
            color = value["color"] if ordered else "blue"
            tag(x, y, value["label"] if ordered else labels["agenda"], color, w)
            for n, item in enumerate(value["items"] if ordered else value):
                row = y + px(1.2 + n * 3.35)
                icon(item["icon"], x, row, 2.85, color, tile=True)
                time = labels["today"] if item["all_day"] else item["time"]
                text(x + px(3.6), row + px(1.65), time, 1.05, 600, px(4))
                text(x + px(7.9), row + px(1.65), item["title"], 1.3, width=w - px(7.9))
        elif kind == "tasks":
            ordered = isinstance(value, dict)
            color = value["color"] if ordered else "yellow"
            tag(x, y, value["label"] if ordered else labels["tasks"], color, w)
            for n, item in enumerate(value["items"] if ordered else value):
                row = y + px(1.2 + n * 3.05)
                icon(item["icon"], x, row, 2.35, color, tile=True)
                text(x + px(3), row + px(1.65), item["title"], 1.35, width=w - px(3))
        elif kind == "routine":
            tag(x, y, value["label"], "green", w)
            cx, cy, r = x + px(3.9), y + px(5.6), px(3.1)
            doc.circle(cx, cy, r, stroke=ink, stroke_width=px(0.08))
            doc.circle(cx, cy, r - px(0.65), stroke=ink, stroke_width=px(0.08))
            radius = r - px(0.32)
            ratio = value["completed"] / value["total"]
            if ratio >= 1:
                doc.circle(
                    cx, cy, radius, stroke=PALETTE_HEX["green"], stroke_width=px(0.6)
                )
            elif ratio > 0:
                angle = 2 * math.pi * ratio - math.pi / 2
                endx, endy = (
                    cx + radius * math.cos(angle),
                    cy + radius * math.sin(angle),
                )
                doc.path(
                    f"M{cx} {cy - radius}A{radius} {radius} 0 {int(ratio > 0.5)} 1 {endx} {endy}",
                    "none",
                    stroke=PALETTE_HEX["green"],
                    stroke_width=px(0.6),
                )
            text(
                cx,
                cy + px(0.5),
                f"{value['completed']}/{value['total']}",
                1.85,
                700,
                anchor="middle",
            )
            text(cx, cy + px(1.7), labels["done"].lower(), 0.8, anchor="middle")
            tx = x + px(8.8)
            icon(value["icon"], tx, y + px(1.25), 3.1, "green", tile=True)
            next_step = value["next_step"] or labels["finished"]
            for n, line in enumerate(wrap(next_step, w - px(8.8), px(1.35), 600)[:2]):
                text(tx, y + px(6 + n * 1.55), line, 1.35, 600)
            sub = (
                f"{value['skipped']} {labels['skipped']}"
                if value["skipped"]
                else labels["next"]
                if value["next_step"]
                else ""
            )
            text(tx, y + px(9.4), sub, 1.0, width=w - px(8.8))
        else:
            color = value["color"]
            tag(x, y, value["label"] or labels["focus"], color, w)
            icon(value["icon"], x, y + px(1.25), 3.3, color, tile=True)
            for n, line in enumerate(wrap(value["title"], w, px(1.65), 700)[:2]):
                text(x, y + px(6.5 + n * 1.8), line, 1.65, 700)
            text(x, y + px(10.25), value["detail"], 1.05, width=w)
    if overflow:
        # Lower-ranked content uses the mockup's compact footer, preserving the
        # complete ordered prefix without squeezing the four main columns.
        footer = rect.y + rect.h - px(10.5 if progress else 5.25)
        doc.line(left, footer, right, footer, ink, max(1, px(0.08)))
        width = (right - left - px(3) * (len(overflow) - 1)) / len(overflow)
        for i, (kind, value) in enumerate(overflow):
            x = round(left + i * (width + px(3)))
            color = value.get("color", "green")
            name = value.get("icon", "mdi:check")
            title = value.get("title", value.get("next_step", ""))
            if kind == "routine" and not title:
                title = labels["finished"]
            if kind in ("agenda", "tasks"):
                title = " · ".join(
                    (
                        (labels["today"] if row.get("all_day") else row.get("time", ""))
                        + " "
                        + row["title"]
                    ).strip()
                    for row in value["items"]
                )
                name = value["items"][0]["icon"]
            icon(name, x, footer + px(1), 2, color)
            text(
                x + px(2.7),
                footer + px(1.65),
                value["label"] or labels["focus"],
                1.0,
                600,
                round(width) - px(10 if kind == "routine" else 2.7),
            )
            text(
                x + px(2.7), footer + px(3.4), title, 1.35, 600, round(width) - px(2.7)
            )
            if kind == "routine":
                text(
                    round(x + width),
                    footer + px(1.65),
                    f"{value['completed']}/{value['total']}",
                    1.05,
                    anchor="end",
                )
                doc.rect(x, footer + px(4.15), round(width), px(0.45), ink)
                filled = round(width * value["completed"] / value["total"])
                if filled:
                    doc.rect(
                        x, footer + px(4.15), filled, px(0.45), PALETTE_HEX["green"]
                    )
    if progress:
        footer = rect.y + rect.h - px(5.25)
        doc.line(left, footer, right, footer, ink, max(1, px(0.08)))
        width = (right - left - px(3) * (len(progress) - 1)) / len(progress)
        for i, item in enumerate(progress):
            x = round(left + i * (width + px(3)))
            icon(item["icon"], x, footer + px(1), 2, item["color"])
            text(
                x + px(2.7),
                footer + px(2.65),
                item["label"],
                1.25,
                width=round(width * 0.53) - px(2.7),
            )
            text(
                round(x + width),
                footer + px(2.65),
                f"{item['value']:g} / {item['max']:g} {item['unit']}".strip(),
                1.15,
                600,
                anchor="end",
            )
            doc.rect(x, footer + px(3.6), round(width), px(0.65), ink)
            doc.rect(
                x + 1,
                footer + px(3.6) + 1,
                round(width) - 2,
                max(1, px(0.65) - 2),
                white,
            )
            filled = round((width - 2) * min(1, item["value"] / item["max"]))
            if filled:
                doc.rect(
                    x + 1,
                    footer + px(3.6) + 1,
                    filled,
                    max(1, px(0.65) - 2),
                    PALETTE_HEX[item["color"]],
                )
