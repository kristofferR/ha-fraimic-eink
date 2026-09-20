"""Selectable Veileder-led layouts over the same briefing snapshot and artwork."""

from __future__ import annotations

import io
import math

from ..icons import icon_path
from ..svg import truncate, wrap
from ..theme import PALETTE_HEX


def render_briefing_layout(doc, rect, options, data):
    nb = data["locale"] == "nb"
    ink, white = PALETTE_HEX["black"], PALETTE_HEX["white"]
    green, blue = PALETTE_HEX["green"], PALETTE_HEX["blue"]
    side = options["layout"] == "side_panel"
    unit = rect.w / 100
    px = lambda value: max(1, round(value * unit))

    def text(x, y, value, size, width, weight=400, color=ink):
        doc.text(
            round(x),
            round(y),
            truncate(str(value), round(width), px(size), weight),
            size=px(size),
            fill=color,
            weight=weight,
        )

    def lines(x, y, value, size, width, height, weight=400):
        step = px(size * 1.35)
        rows = wrap(value, width, px(size), weight)
        limit = max(0, int(height / step))
        for index, row in enumerate(rows[:limit]):
            if index == limit - 1 and len(rows) > limit:
                row = truncate(row + " …", width, px(size), weight)
            text(x, y + index * step, row, size, width, weight)
        return min(len(rows), limit) * step

    def artwork(x, y, width, height):
        raw = data.get("_artwork_png")
        if not raw:
            return
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(raw)) as image:
            crop = ImageOps.fit(image.convert("RGB"), (round(width), round(height)))
            encoded = io.BytesIO()
            crop.save(encoded, format="PNG")
        doc.image(encoded.getvalue(), round(x), round(y), round(width), round(height))

    def label(x, y, value, width, color=green):
        text(x, y, value.upper(), 1.15, width, 700, color)

    def block(value, x, y, width, height):
        kind = value["type"]
        color = PALETTE_HEX[
            value.get("color", "green" if kind == "routine" else "blue")
        ]
        label(
            x,
            y,
            value.get("label") or ("Dagens fokus" if nb else "Today's focus"),
            width,
            color,
        )
        y += px(2.5)
        if kind == "routine":
            if height < px(10):
                text(
                    x,
                    y,
                    f"{value['completed']}/{value['total']} · {value['next_step'] or ('Ferdig' if nb else 'Finished')}",
                    1.6,
                    width,
                    600,
                )
                return
            radius = px(3)
            cx, cy = x + radius, y + radius
            doc.circle(round(cx), round(cy), radius, stroke=ink, stroke_width=px(0.12))
            ratio = value["completed"] / value["total"]
            if ratio >= 1:
                doc.circle(
                    round(cx), round(cy), radius, stroke=green, stroke_width=px(0.4)
                )
            elif ratio > 0:
                angle = ratio * 2 * math.pi - math.pi / 2
                doc.path(
                    f"M{cx} {cy - radius}A{radius} {radius} 0 {int(ratio > 0.5)} 1 {cx + radius * math.cos(angle)} {cy + radius * math.sin(angle)}",
                    "none",
                    stroke=green,
                    stroke_width=px(0.4),
                )
            doc.text(
                round(cx),
                round(cy + px(0.5)),
                f"{value['completed']}/{value['total']}",
                size=px(1.6),
                fill=ink,
                weight=600,
                anchor="middle",
            )
            lines(
                x + px(7.5),
                y + px(1.8),
                value["next_step"] or ("Ferdig" if nb else "Finished"),
                1.65,
                width - px(7.5),
                height - px(3),
                600,
            )
        elif kind in ("tasks", "agenda"):
            capacity = max(1, int((height - px(2.5)) / px(3)) + 1)
            for index, item in enumerate(value["items"][:capacity]):
                row = y + index * px(3)
                doc.icon(
                    icon_path(item["icon"]),
                    round(x),
                    round(row - px(1.6)),
                    px(1.8),
                    color,
                )
                title = item["title"]
                if kind == "agenda" and not item["all_day"]:
                    title = f"{item['time']} · {title}"
                if index == capacity - 1 and len(value["items"]) > capacity:
                    title += f" (+{len(value['items']) - capacity})"
                text(x + px(2.4), row, title, 1.6, width - px(2.4), 600)
        else:
            remaining = height - px(2.5)
            used = lines(x, y, value["title"], 1.7, width, remaining, 600)
            lines(
                x,
                y + used + px(0.8),
                value["detail"],
                1.3,
                width,
                remaining - used - px(0.8),
            )

    blocks = list(data.get("blocks", []))
    if "blocks" not in data:
        if data.get("agenda"):
            blocks.append(
                {
                    "type": "agenda",
                    "label": "Dagen din" if nb else "Your day",
                    "items": data["agenda"],
                }
            )
        if data.get("routine"):
            blocks.append({"type": "routine", **data["routine"]})
        if data.get("tasks"):
            blocks.append(
                {
                    "type": "tasks",
                    "label": "Husk" if nb else "Remember",
                    "items": data["tasks"],
                }
            )
        if data.get("focus"):
            blocks.append({"type": "focus", **data["focus"]})

    doc.rect(rect.x, rect.y, rect.w, rect.h, white)
    margin = px(2.6)
    left = rect.x + (round(rect.w * 0.4) + margin if side else margin)
    right = rect.x + rect.w - margin
    width = right - left
    if side:
        artwork(rect.x, rect.y, round(rect.w * 0.4), rect.h)
    top = rect.y + margin
    text(left, top + px(2.5), data["greeting"], 2.8, width, 700)
    weather = data.get("weather")
    date = data["date_label"]
    text(left, top + px(5.3), date, 1.35, width * 0.7)
    if weather:
        doc.icon(
            icon_path(weather["icon"]),
            round(right - px(10)),
            round(top + px(2.6)),
            px(2.4),
            ink,
        )
        text(
            right - px(7),
            top + px(4.5),
            f"{weather['temperature']:g}{weather['unit']}",
            1.65,
            px(7),
            600,
        )
    doc.line(
        round(left), round(top + px(7)), round(right), round(top + px(7)), ink, px(0.1)
    )
    main_top = top + px(10)
    footer_top = rect.y + rect.h * (
        0.58 if side and len(blocks) > 2 else 0.66 if len(blocks) > 3 else 0.72
    )
    guide_width = width if side else width * 0.64
    guidance = data.get("guidance")
    if guidance:
        label(left, main_top, "Veileder" if nb else "Guidance", guide_width)
        y = main_top + px(3.7)
        used = (
            lines(
                left,
                y,
                guidance["title"],
                3.1 if not side else 2.7,
                guide_width,
                px(9),
                700,
            )
            if guidance["title"]
            else 0
        )
        y += used + px(1)
        body_space = footer_top - y - px(3.5 if guidance["action"] else 1)
        body_size = 1.8 if not side else 1.65
        while (
            body_size > 1.35
            and len(wrap(guidance["body"], guide_width, px(body_size)))
            * px(body_size * 1.35)
            > body_space
        ):
            body_size -= 0.1
        lines(left, y, guidance["body"], body_size, guide_width, body_space)
        if guidance["action"]:
            text(
                left,
                footer_top - px(1.6),
                guidance["action"],
                1.45,
                guide_width,
                600,
                green,
            )
    else:
        # Sparse mornings still use the available content at a readable size.
        text(left, main_top, "Dagen din" if nb else "Your day", 3, guide_width, 700)
        if blocks:
            block(
                blocks.pop(0),
                left,
                main_top + px(5),
                guide_width,
                footer_top - main_top - px(7),
            )

    if not side:
        art_x = left + width * 0.69
        art_w = right - art_x
        art_h = (footer_top - main_top) * 0.55
        artwork(art_x, main_top - px(1), art_w, art_h)
        routine_index = next(
            (index for index, value in enumerate(blocks) if value["type"] == "routine"),
            None,
        )
        if routine_index is not None:
            block(
                blocks.pop(routine_index),
                art_x,
                main_top + art_h + px(1.7),
                art_w,
                px(10),
            )

    doc.line(
        round(left), round(footer_top), round(right), round(footer_top), ink, px(0.1)
    )
    columns = 2 if side else 3
    rows = math.ceil(len(blocks) / columns) or 1
    progress = data.get("progress", [])
    bottom_inset = data.get("_bottom_inset", 0)
    available = (
        rect.y + rect.h - bottom_inset - footer_top - px(3.5 + (4 if progress else 0))
    )
    gap = px(2)
    cell_width = (width - gap * (columns - 1)) / columns
    for index, value in enumerate(blocks):
        x = left + (index % columns) * (cell_width + gap)
        y = footer_top + px(2.5) + (index // columns) * available / rows
        block(value, x, y, cell_width, available / rows - px(1))
    for index, value in enumerate(progress):
        progress_width = width / len(progress)
        x = left + index * progress_width
        y = rect.y + rect.h - bottom_inset - px(2.5)
        text(
            x,
            y,
            f"{value['label']} · {value['value']:g}/{value['max']:g} {value['unit']}",
            1.25,
            progress_width - gap,
            600,
            PALETTE_HEX[value["color"]],
        )


def render_dense_briefing(doc, rect, options, data):
    """Expand tasks without replacing agenda, focus cards, or progress diagrams."""
    nb = data["locale"] == "nb"
    side = options.get("layout") == "side_panel"
    strip = options.get("layout", "strip") == "strip"
    unit = rect.w / 100
    px = lambda value: max(1, round(value * unit))
    ink, white, green, blue = (
        PALETTE_HEX[key] for key in ("black", "white", "green", "blue")
    )
    top = rect.y + (rect.h * 0.16 if strip else 0)
    left = rect.x + (rect.w * 0.35 if side else 0)
    doc.rect(
        round(left),
        round(top),
        round(rect.x + rect.w - left),
        round(rect.y + rect.h - top),
        white,
    )

    def artwork(x, y, width, height):
        if not data.get("_artwork_png"):
            return
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(data["_artwork_png"])) as source:
            crop = ImageOps.fit(source.convert("RGB"), (round(width), round(height)))
            encoded = io.BytesIO()
            crop.save(encoded, format="PNG")
        doc.image(encoded.getvalue(), round(x), round(y), round(width), round(height))

    if side:
        artwork(rect.x, rect.y, rect.w * 0.35, rect.h)
    margin = px(2.4)
    left += margin
    right = rect.x + rect.w - margin
    width = right - left

    def text(x, y, value, size, width, weight=400, color=ink):
        doc.text(
            round(x),
            round(y),
            truncate(str(value), round(width), px(size), weight),
            size=px(size),
            fill=color,
            weight=weight,
        )

    def lines(x, y, value, size, width, count, weight=400):
        rows = wrap(value, width, px(size), weight)
        for index, row in enumerate(rows[:count]):
            if index == count - 1 and len(rows) > count:
                row = truncate(row + " …", width, px(size), weight)
            text(x, y + px(size * 1.3) * index, row, size, width, weight)
        return min(len(rows), count) * px(size * 1.3)

    def label(x, y, value, width, color=green):
        doc.rect(round(x), round(y - px(0.8)), px(0.3), px(0.85), color)
        text(x + px(0.8), y, value.upper(), 1, width - px(0.8), 700, ink)

    y = top + px(3.7)
    text(left, y, data["greeting"], 2.3, width * 0.54, 700)
    weather = data.get("weather")
    date = data["date_label"]
    text(left + width * 0.56, y - px(1), date, 1.05, width * 0.44)
    if weather:
        doc.icon(
            icon_path(weather["icon"]),
            round(right - px(8)),
            round(y - px(0.5)),
            px(1.8),
            ink,
        )
        text(
            right - px(5.5),
            y + px(1),
            f"{weather['temperature']:g}{weather['unit']}",
            1.2,
            px(5.5),
            600,
        )
    y += px(3.3)
    guidance = data.get("guidance")
    guide_width = width if side or strip else width * 0.7
    if guidance:
        label(left, y, "Veileder" if nb else "Guidance", guide_width)
        y += px(2.5)
        y += lines(left, y, guidance["title"], 1.9, guide_width, 1, 700)
        y += lines(left, y, guidance["body"], 1.25, guide_width, 2)
        if guidance["action"]:
            text(left, y, guidance["action"], 1.2, guide_width, 600, green)
            y += px(1.8)
    if not side and not strip:
        artwork(right - width * 0.25, top + px(6), width * 0.25, px(8))
    y = max(y + px(1.5), top + px(16) if not side and not strip else y + px(1.5))
    doc.line(round(left), round(y), round(right), round(y), ink, px(0.08))
    y += px(2.5)

    blocks = list(data.get("blocks", []))
    if "blocks" not in data:
        for kind in ("agenda", "tasks"):
            if data.get(kind):
                blocks.append(
                    {
                        "type": kind,
                        "label": ("Dagen din" if kind == "agenda" else "Husk")
                        if nb
                        else kind.title(),
                        "items": data[kind],
                    }
                )
        for kind in ("routine", "focus"):
            if data.get(kind):
                blocks.append({"type": kind, **data[kind]})
    tasks = [block for block in blocks if block["type"] == "tasks"]
    supporting = [block for block in blocks if block["type"] != "tasks"]
    progress = data.get("progress", [])
    bottom = rect.y + rect.h - data.get("_bottom_inset", 0) - px(1.5)
    content_bottom = bottom - (px(5.5) if progress else 0)
    gap = px(2.5)
    support_width = width * (0.4 if side else 0.33) if supporting else 0
    task_left = left + support_width + (gap if supporting else 0)
    task_width = right - task_left

    # Supporting cards keep their original meaning, color, detail, and timing.
    weights = []
    for value in supporting:
        if value["type"] == "agenda":
            weights.append(3 + 2.1 * len(value["items"]))
        else:
            title = value.get("title", value.get("next_step", ""))
            title_rows = min(2, len(wrap(title, support_width, px(1.35), 700)))
            weights.append(
                3
                + title_rows * 1.8
                + (1.4 if value.get("detail") or value["type"] == "routine" else 0)
            )
    total_weight = sum(weights) or 1
    support_scale = min(1, (content_bottom - y) / px(total_weight))
    support_y = y
    for value, weight in zip(supporting, weights):
        height = (content_bottom - y) * weight / total_weight
        color = PALETTE_HEX[value.get("color", "blue")]
        label(left, support_y, value["label"], support_width, color)
        cursor = support_y + px(2 * support_scale)
        if value["type"] == "agenda":
            for item in value["items"]:
                doc.icon(
                    icon_path(item["icon"]),
                    round(left),
                    round(cursor - px(1.1 * support_scale)),
                    px(1.5 * support_scale),
                    color,
                )
                time = ("I dag" if nb else "Today") if item["all_day"] else item["time"]
                text(
                    left + px(2),
                    cursor,
                    f"{time} · {item['title']}",
                    1.15 * support_scale,
                    support_width - px(2),
                    600,
                )
                cursor += px(2.1 * support_scale)
        else:
            title = value.get("title", value.get("next_step", ""))
            detail = value.get("detail", "")
            if value["type"] == "routine":
                detail = f"{value['completed']}/{value['total']}"
            used = lines(
                left, cursor, title, 1.35 * support_scale, support_width, 2, 700
            )
            text(left, cursor + used, detail, 1.05 * support_scale, support_width)
        support_y += height

    rows = [(value, item) for value in tasks for item in value["items"]]
    columns = 2 if len(rows) > 6 else 1
    count = math.ceil(len(rows) / columns) or 1
    cell_width = (task_width - gap * (columns - 1)) / columns
    step = min(px(4), (content_bottom - y) / count)
    for index, (value, item) in enumerate(rows):
        x = task_left + (index // count) * (cell_width + gap)
        row_y = y + (index % count) * step
        color = PALETTE_HEX[value.get("color", "blue")]
        if index % count == 0 or rows[index - 1][0]["label"] != value["label"]:
            label(x, row_y, value["label"], cell_width, color)
        doc.icon(
            icon_path(item["icon"]),
            round(x),
            round(row_y + px(0.6)),
            px(1.6),
            ink if value.get("color") == "yellow" else color,
        )
        text(
            x + px(2),
            row_y + px(2),
            item["title"],
            1.1 if side else 1.25,
            cell_width - px(2),
            600,
        )

    if progress:
        footer_y = bottom - px(3.5)
        doc.line(
            round(left),
            round(footer_y - px(1.5)),
            round(right),
            round(footer_y - px(1.5)),
            ink,
            px(0.08),
        )
        cell_width = (width - gap * (len(progress) - 1)) / len(progress)
        for index, item in enumerate(progress):
            x = left + index * (cell_width + gap)
            color = PALETTE_HEX[item["color"]]
            text(
                x,
                footer_y,
                f"{item['label']}  {item['value']:g}/{item['max']:g} {item['unit']}".strip(),
                1.1,
                cell_width,
                600,
            )
            doc.rect(round(x), round(footer_y + px(1)), round(cell_width), px(0.7), ink)
            doc.rect(
                round(x + 1),
                round(footer_y + px(1) + 1),
                round(cell_width - 2),
                max(1, px(0.7) - 2),
                white,
            )
            fill = round((cell_width - 2) * min(1, item["value"] / item["max"]))
            if fill:
                doc.rect(
                    round(x + 1),
                    round(footer_y + px(1) + 1),
                    fill,
                    max(1, px(0.7) - 2),
                    color,
                )
