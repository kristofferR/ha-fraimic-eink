"""Selectable Veileder-led layouts over the same briefing snapshot and artwork."""

from __future__ import annotations

import io
import math

from ..icons import icon_path
from ..svg import truncate, wrap
from ..theme import PALETTE_HEX


def find_next_card(blocks):
    """Match the localized Next card consistently for routing and layout."""
    return next(
        (
            block
            for block in blocks
            if block["type"] == "focus" and block.get("label") in ("Neste", "Next")
        ),
        None,
    )


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
    available = rect.y + rect.h - footer_top - px(3.5 + (4 if progress else 0))
    gap = px(2)
    cell_width = (width - gap * (columns - 1)) / columns
    for index, value in enumerate(blocks):
        x = left + (index % columns) * (cell_width + gap)
        y = footer_top + px(2.5) + (index // columns) * available / rows
        block(value, x, y, cell_width, available / rows - px(1))
    for index, value in enumerate(progress):
        progress_width = width / len(progress)
        x = left + index * progress_width
        y = rect.y + rect.h - px(2.5)
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
    """A measured editorial grid: stable type sizes and space for every section."""
    nb = data["locale"] == "nb"
    mode = options.get("layout", "strip")
    unit = rect.w / 2560
    p = lambda value: max(1, round(value * unit))
    ink, white, blue, green = (
        PALETTE_HEX[key] for key in ("black", "white", "blue", "green")
    )
    body, title, small = p(32), p(42), p(25)
    leading, title_leading = p(44), p(54)
    pad, gap = p(64), p(56)
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
    next_card = find_next_card(blocks)
    supporting = [
        block for block in blocks if block["type"] != "tasks" and block is not next_card
    ]
    task_rows = [
        (block, item)
        for block in blocks
        if block["type"] == "tasks"
        for item in block["items"]
    ]
    progress = data.get("progress", [])
    panel_left = rect.x + (round(rect.w * 0.27) if mode == "side_panel" else 0)
    left, right = panel_left + pad, rect.x + rect.w - pad
    width = right - left
    guidance = data.get("guidance")
    feature_gap = p(80)
    guide_width = round((width - feature_gap) * 0.60) if next_card else width
    next_left = left + guide_width + feature_gap if guidance else left
    next_width = right - next_left
    support_columns = min(2, len(supporting)) if len(task_rows) <= 3 else 1
    if not task_rows:
        support_columns = min(3, len(supporting))
    support_columns = max(1, support_columns)
    if supporting and (support_columns > 1 or not task_rows):
        column_count = support_columns + bool(task_rows)
        support_width = (width - gap * (column_count - 1)) / column_count
    else:
        support_width = round((width - gap) * 0.28) if supporting else 0
    tasks_left = left + support_columns * (support_width + gap) if supporting else left
    tasks_width = right - tasks_left
    task_columns = 2 if len(task_rows) > 3 else 1
    task_width = (tasks_width - gap * (task_columns - 1)) / task_columns
    task_count = math.ceil(len(task_rows) / task_columns)

    def rows(value, width, size, count, weight=400):
        result = wrap(str(value), width, size, weight)
        if len(result) > count:
            result = result[:count]
            result[-1] = truncate(result[-1] + " …", width, size, weight)
        return result

    def text(x, baseline, value, size, width, weight=400, color=ink, anchor="start"):
        doc.text(
            round(x),
            round(baseline),
            truncate(str(value), width, size, weight),
            size=size,
            weight=weight,
            fill=color,
            anchor=anchor,
        )

    def paragraph(x, top, value, width, size=body, line=leading, limit=3, weight=400):
        lines = rows(value, width, size, limit, weight)
        for index, value in enumerate(lines):
            text(x, top + size + index * line, value, size, width, weight)
        return len(lines) * line

    def heading(x, top, label, width, color=blue, icon=None):
        if icon:
            doc.icon(icon_path(icon), round(x), round(top), p(28), color)
            x += p(40)
            width -= p(40)
        else:
            doc.rect(round(x), round(top + p(3)), p(5), p(22), color)
            x += p(18)
            width -= p(18)
        text(x, top + small, label.upper(), small, width, 600)

    def feature_height(value, width):
        if not value:
            return 0
        height = p(54)
        if value.get("title"):
            height += len(
                rows(value["title"], width, title, 2, 600)
            ) * title_leading + p(16)
        prose = value.get("body", value.get("detail", ""))
        height += len(rows(prose, width, body, 3)) * leading
        if value.get("action"):
            height += p(54)
        return height

    feature_height_px = max(
        feature_height(guidance, guide_width), feature_height(next_card, next_width)
    )
    support_heights = []
    for block in supporting:
        if block["type"] == "agenda":
            support_heights.append(p(54) + len(block["items"]) * p(60))
        else:
            block_title = block.get("title", block.get("next_step", ""))
            height = p(54) + len(rows(block_title, support_width, p(36), 2, 600)) * p(
                46
            )
            if block.get("detail"):
                height += p(12) + len(
                    rows(block["detail"], support_width, p(28), 2)
                ) * p(38)
            support_heights.append(height)
    supporting_height = max(
        (
            sum(support_heights[column::support_columns])
            + max(0, len(support_heights[column::support_columns]) - 1) * p(36)
            for column in range(support_columns)
        ),
        default=0,
    )
    main_height = max(supporting_height, p(54) + task_count * p(58))
    footer_height = p(126) if progress else 0
    weekly = data.get("weekly_focus")
    header_height = p(158) if weekly else p(100)
    required = (
        pad * 2
        + header_height
        + feature_height_px
        + (p(64) if feature_height_px else 0)
        + main_height
        + footer_height
    )
    top = max(rect.y, rect.y + rect.h - required) if mode == "strip" else rect.y
    doc.rect(
        round(panel_left),
        round(top),
        round(rect.x + rect.w - panel_left),
        round(rect.y + rect.h - top),
        white,
    )

    def artwork(x, y, width, height):
        if not data.get("_artwork_png") or width <= 0 or height <= 0:
            return
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(data["_artwork_png"])) as source:
            crop = ImageOps.fit(source.convert("RGB"), (round(width), round(height)))
            encoded = io.BytesIO()
            crop.save(encoded, format="PNG")
        doc.image(encoded.getvalue(), round(x), round(y), round(width), round(height))

    if mode == "side_panel":
        artwork(rect.x, rect.y, panel_left - rect.x, rect.h)
    elif mode == "strip":
        doc.rect(rect.x, round(top), rect.w, p(5), blue)
    # Give spare height to the artwork so the overview ends at the bottom padding.
    if mode == "overview":
        art_height = max(0, rect.h - required)
        if art_height:
            artwork(rect.x, rect.y, rect.w, art_height)
            top += art_height
    if mode == "side_panel":
        top += max(0, (rect.h - required) / 2)
    y = top + pad
    text(left, y + p(52), data["greeting"], p(52), width * 0.52, 600)
    weather = data.get("weather")
    date_right = right - (p(214) if weather else 0)
    text(
        date_right,
        y + p(43),
        data["date_label"],
        p(28),
        width * 0.44 - (p(214) if weather else 0),
        anchor="end",
    )
    if weather:
        doc.icon(
            icon_path(weather["icon"]),
            round(right - p(176)),
            round(y + p(12)),
            p(36),
            ink,
        )
        text(
            right,
            y + p(43),
            f"{weather['temperature']:g}{weather['unit']}",
            p(32),
            p(128),
            600,
            anchor="end",
        )
    if weekly:
        label = "Ukens fokus" if nb else "Weekly focus"
        value = f"{label}: {weekly['text']}"
        if weekly["done"]:
            value += " · Fullført" if nb else " · Done"
        text(left, y + p(112), value, p(30), width, 400, green)
    y += header_height

    def feature(value, x, top, width, label, color, icon):
        if not value:
            return
        heading(x, top, label, width, color, icon)
        cursor = top + p(54)
        if value.get("title"):
            cursor += paragraph(
                x, cursor, value["title"], width, title, title_leading, 2, 600
            ) + p(16)
        cursor += paragraph(
            x, cursor, value.get("body", value.get("detail", "")), width
        )
        if value.get("action"):
            text(x, cursor + p(46), value["action"], p(30), width, 600, color)

    feature(
        guidance,
        left,
        y,
        guide_width,
        "Veileder" if nb else "Guidance",
        green,
        "mdi:compass-outline",
    )
    if next_card:
        feature(
            next_card,
            next_left,
            y,
            next_width,
            next_card["label"],
            blue,
            next_card["icon"],
        )
    y += feature_height_px
    if feature_height_px:
        doc.line(
            round(left), round(y + p(30)), round(right), round(y + p(30)), ink, p(1)
        )
        y += p(64)
    support_cursors = [y] * support_columns
    for index, (block, height) in enumerate(zip(supporting, support_heights)):
        column = index % support_columns
        support_x = left + column * (support_width + gap)
        support_y = support_cursors[column]
        color = PALETTE_HEX[block.get("color", "blue")]
        heading(
            support_x,
            support_y,
            block.get("label") or ("Dagens fokus" if nb else "Today's focus"),
            support_width,
            color,
        )
        cursor = support_y + p(54)
        if block["type"] == "agenda":
            for item in block["items"]:
                doc.rect(
                    round(support_x), round(cursor + p(4)), p(36), p(36), color, rx=p(4)
                )
                doc.icon(
                    icon_path(item["icon"]),
                    round(support_x + p(6)),
                    round(cursor + p(10)),
                    p(24),
                    white,
                )
                time = ("I dag" if nb else "Today") if item["all_day"] else item["time"]
                text(support_x + p(52), cursor + p(30), time, p(26), p(92), 600)
                text(
                    support_x + p(150),
                    cursor + p(30),
                    item["title"],
                    p(30),
                    support_width - p(150),
                )
                cursor += p(60)
        else:
            cursor += paragraph(
                support_x,
                cursor,
                block.get("title", block.get("next_step", "")),
                support_width,
                p(36),
                p(46),
                2,
                600,
            )
            if block.get("detail"):
                paragraph(
                    support_x,
                    cursor + p(12),
                    block["detail"],
                    support_width,
                    p(28),
                    p(38),
                    2,
                )
        support_cursors[column] += height + p(36)

    for column in range(task_columns):
        column_rows = task_rows[column * task_count : (column + 1) * task_count]
        if not column_rows:
            continue
        x = tasks_left + column * (task_width + gap)
        labels = {block["label"] for block, _ in column_rows}
        label = (
            next(iter(labels)) if len(labels) == 1 else "Oppgaver" if nb else "Tasks"
        )
        heading(
            x, y, label, task_width, PALETTE_HEX[column_rows[0][0].get("color", "blue")]
        )
        for index, (block, item) in enumerate(column_rows):
            row = y + p(54) + index * p(58)
            color = (
                blue
                if item.get("priority")
                else PALETTE_HEX[block.get("color", "yellow")]
            )
            doc.rect(round(x), round(row + p(5)), p(32), p(32), color, rx=p(4))
            doc.icon(
                icon_path("mdi:flag" if item.get("priority") else item["icon"]),
                round(x + p(6)),
                round(row + p(11)),
                p(20),
                ink if color == PALETTE_HEX["yellow"] else white,
            )
            deadline = item.get("deadline", "")
            meta_width = p(144) if deadline else 0
            text(
                x + p(48),
                row + body,
                item["title"],
                body,
                task_width - p(48) - meta_width,
            )
            if deadline:
                text(
                    x + task_width,
                    row + body,
                    deadline,
                    p(24),
                    meta_width - p(12),
                    anchor="end",
                )

    if progress:
        footer_top = y + main_height + p(40)
        doc.line(
            round(left),
            round(footer_top - p(24)),
            round(right),
            round(footer_top - p(24)),
            ink,
            p(1),
        )
        cell_width = (width - gap * (len(progress) - 1)) / len(progress)
        for index, item in enumerate(progress):
            x = left + index * (cell_width + gap)
            color = PALETTE_HEX[item["color"]]
            doc.icon(icon_path(item["icon"]), round(x), round(footer_top), p(30), color)
            value = f"{item['value']:g}/{item['max']:g} {item['unit']}".strip()
            text(
                x + p(44),
                footer_top + p(28),
                item["label"],
                p(28),
                cell_width * 0.56 - p(44),
                600,
            )
            text(
                x + cell_width,
                footer_top + p(28),
                value,
                p(28),
                cell_width * 0.44,
                anchor="end",
            )
            bar_y = footer_top + p(52)
            if (
                not item["unit"]
                and float(item["max"]).is_integer()
                and 0 < item["max"] <= 12
            ):
                count = int(item["max"])
                segment_gap = p(10)
                segment_width = (cell_width - segment_gap * (count - 1)) / count
                for segment in range(count):
                    sx = x + segment * (segment_width + segment_gap)
                    doc.rect(round(sx), round(bar_y), round(segment_width), p(18), ink)
                    doc.rect(
                        round(sx + p(1)),
                        round(bar_y + p(1)),
                        max(1, round(segment_width - p(2))),
                        p(16),
                        color if segment < item["value"] else white,
                    )
            else:
                doc.rect(round(x), round(bar_y), round(cell_width), p(18), ink)
                doc.rect(
                    round(x + p(1)),
                    round(bar_y + p(1)),
                    round(cell_width - p(2)),
                    p(16),
                    white,
                )
                fill = round((cell_width - p(2)) * min(1, item["value"] / item["max"]))
                if fill:
                    doc.rect(round(x + p(1)), round(bar_y + p(1)), fill, p(16), color)

    if data.get("updated_time"):
        label = "Oppdatert" if nb else "Updated"
        text(
            rect.x + rect.w - p(8),
            rect.y + rect.h - p(18),
            f"{label} {data['updated_time']}",
            p(24),
            rect.w * 0.45,
            anchor="end",
        )
