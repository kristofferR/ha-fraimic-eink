"""Selectable Veileder-led layouts over the same briefing snapshot and artwork."""

from __future__ import annotations

import io
import math

from ..icons import icon_path
from ..svg import measure, truncate, wrap
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
    body, title, small = p(32), p(52), p(25)
    leading, title_leading = p(44), p(64)
    pad, gap = p(64), p(56)
    blocks = [dict(block) for block in data.get("blocks", [])]
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
    omitted_tasks = max(0, len(task_rows) - 12)
    task_rows = task_rows[:12]
    for block in supporting:
        if block["type"] == "routine":
            done = "fullført" if nb else "complete"
            skipped = "hoppet over" if nb else "skipped"
            block["detail"] = f"{block['completed']}/{block['total']} {done}"
            if block["skipped"]:
                block["detail"] += f" · {block['skipped']} {skipped}"
    progress = data.get("progress", [])
    panel_left = rect.x + (round(rect.w * 0.27) if mode == "side_panel" else 0)
    left, right = panel_left + pad, rect.x + rect.w - pad
    width = right - left
    guidance = data.get("guidance")
    weather = data.get("weather")
    weekdays = dict(
        zip(
            (
                "mandag",
                "tirsdag",
                "onsdag",
                "torsdag",
                "fredag",
                "lørdag",
                "søndag",
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            ),
            (
                "Man.",
                "Tir.",
                "Ons.",
                "Tor.",
                "Fre.",
                "Lør.",
                "Søn.",
                "Mon.",
                "Tue.",
                "Wed.",
                "Thu.",
                "Fri.",
                "Sat.",
                "Sun.",
            ),
        )
    )
    weekday, separator, rest = data["date_label"].partition(" ")
    date_label = weekdays.get(weekday.rstrip(",").lower(), weekday) + separator + rest
    date_width = min(p(300), math.ceil(measure(date_label, p(28))))
    metadata_width = date_width + (p(214) if weather else 0) + p(32)
    metadata_card = next_card or guidance
    feature_gap = p(80)
    guide_width = round((width - feature_gap) * 0.60) if next_card else width
    if next_card and guidance:
        guide_width = min(guide_width, width - feature_gap - metadata_width - p(420))
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
        if count is not None and len(result) > count:
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

    def progress_item(item, x, footer_top, cell_width):
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
            and float(item["value"]).is_integer()
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

    guidance_scale = 1.0

    def feature_metrics(value):
        scale = guidance_scale if value is guidance else 1.0
        return (
            title,
            title_leading,
            *(max(1, round(size * scale)) for size in (body, leading, p(30), p(42))),
        )

    def feature_height(value, width):
        if not value:
            return 0
        title_size, title_line, body_size, body_line, action_size, action_line = (
            feature_metrics(value)
        )
        unlimited = value is guidance
        title_width = width - p(44) - (metadata_width if value is metadata_card else 0)
        height = 0
        if value.get("title"):
            height += len(
                rows(
                    value["title"],
                    title_width,
                    title_size,
                    None if unlimited else 2,
                    600,
                )
            ) * title_line + p(16)
        prose = value.get("body", value.get("detail", ""))
        if not value.get("title"):
            width = title_width
        height += (
            len(rows(prose, width, body_size, None if unlimited else 3)) * body_line
        )
        if value.get("action"):
            height += (
                p(12)
                + len(rows(value["action"], width, action_size, None, 600))
                * action_line
            )
        return height

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

    def support_height():
        return max(
            (
                sum(support_heights[column::support_columns])
                + max(0, len(support_heights[column::support_columns]) - 1) * p(36)
                for column in range(support_columns)
            ),
            default=0,
        )

    # Use spare space beside tasks before allocating a separate progress row.
    progress_height = len(progress) * p(90)
    progress_agenda = None
    progress_column = False
    main_rows_height = max(support_height(), p(54) + task_count * p(58))
    if progress:
        for index, block in enumerate(supporting):
            column_heights = support_heights[index % support_columns :: support_columns]
            column_height = sum(column_heights) + max(0, len(column_heights) - 1) * p(
                36
            )
            if (
                block["type"] == "agenda"
                and column_height + progress_height <= main_rows_height
            ):
                progress_agenda = block
                support_heights[index] += progress_height
                break
        if progress_agenda is None and task_rows and support_columns == 1:
            progress_width = p(480)
            remaining = tasks_width - progress_width - gap
            if (remaining - gap * (task_columns - 1)) / task_columns >= p(600):
                progress_column = True
                tasks_width = remaining
                task_width = (tasks_width - gap * (task_columns - 1)) / task_columns
    footer_height = (
        p(126) if progress and progress_agenda is None and not progress_column else 0
    )
    weekly = data.get("weekly_focus")
    top_pad = p(40)
    header_height = p(56) if weekly else 0
    if not (guidance or next_card):
        header_height += p(64)
    # Give guidance the artwork's height first; only reduce its type when the
    # complete text would otherwise displace the agenda and task rows.
    feature_budget = max(
        p(200),
        rect.h
        - pad
        - top_pad
        - header_height
        - p(64)
        - footer_height
        - max(
            min(support_height(), p(402)),
            p(54) + task_count * p(58),
            p(54) + progress_height if progress_column else 0,
        ),
    )
    while (
        guidance_scale > 0.5 and feature_height(guidance, guide_width) > feature_budget
    ):
        guidance_scale = max(0.5, guidance_scale - 0.025)
    feature_height_px = max(
        feature_height(guidance, guide_width), feature_height(next_card, next_width)
    )
    fixed_height = (
        pad
        + top_pad
        + header_height
        + feature_height_px
        + (p(64) if feature_height_px else 0)
        + footer_height
    )
    main_budget = max(0, rect.h - fixed_height)

    omitted_support = 0
    while (
        support_heights
        and support_height() + (p(42) if omitted_support else 0) > main_budget
    ):
        support_heights.pop()
        removed = supporting.pop()
        if removed is progress_agenda:
            progress_agenda = None
            footer_height = p(126)
            fixed_height += footer_height
            main_budget = max(0, rect.h - fixed_height)
        omitted_support += 1
    supporting_height = support_height() + (p(42) if omitted_support else 0)
    main_height = max(
        supporting_height,
        p(54) + task_count * p(58),
        p(54) + progress_height if progress_column else 0,
    )
    required = fixed_height + main_height
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
    y = top + top_pad
    metadata_y = y + (p(56) if weekly else 0)
    date_right = right - (p(214) if weather else 0)
    text(
        date_right,
        metadata_y + title,
        date_label,
        p(28),
        date_width,
        anchor="end",
    )
    if weather:
        doc.icon(
            icon_path(weather["icon"]),
            round(right - p(176)),
            round(metadata_y + title - p(36)),
            p(36),
            ink,
        )
        text(
            right,
            metadata_y + title,
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
        text(left, y + p(30), value, p(30), width, 400, green)
    y += header_height

    def feature(value, x, top, width, color, icon):
        if not value:
            return
        title_size, title_line, body_size, body_line, action_size, action_line = (
            feature_metrics(value)
        )
        unlimited = value is guidance
        icon_size = min(p(28), title_size if value.get("title") else body_size)
        first_size = title_size if value.get("title") else body_size
        doc.icon(
            icon_path(icon),
            round(x),
            round(top + first_size - icon_size),
            icon_size,
            color,
        )
        title_width = width - p(44) - (metadata_width if value is metadata_card else 0)
        cursor = top
        if value.get("title"):
            cursor += paragraph(
                x + p(44),
                cursor,
                value["title"],
                title_width,
                title_size,
                title_line,
                None if unlimited else 2,
                600,
            ) + p(16)
        else:
            x += p(44)
            width = title_width
        cursor += paragraph(
            x,
            cursor,
            value.get("body", value.get("detail", "")),
            width,
            body_size,
            body_line,
            None if unlimited else 3,
        )
        if value.get("action"):
            for index, line in enumerate(
                rows(value["action"], width, action_size, None, 600)
            ):
                text(
                    x,
                    cursor + p(12) + action_size + index * action_line,
                    line,
                    action_size,
                    width,
                    600,
                    color,
                )

    feature(guidance, left, y, guide_width, green, "mdi:compass-outline")
    if next_card:
        feature(next_card, next_left, y, next_width, blue, next_card["icon"])
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
        if block is progress_agenda:
            for progress_index, item in enumerate(progress):
                progress_item(
                    item, support_x, cursor + progress_index * p(90), support_width
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
        if omitted_tasks and column == task_columns - 1:
            label += f" (+{omitted_tasks})"
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

    if omitted_support:
        label = f"+{omitted_support} flere" if nb else f"+{omitted_support} more"
        text(left, y + supporting_height - p(8), label, p(25), support_width)

    if progress_column:
        progress_x = right - progress_width
        for index, item in enumerate(progress):
            progress_item(item, progress_x, y + p(54) + index * p(90), progress_width)
    elif footer_height:
        footer_top = y + main_height + p(40)
        cell_width = (width - gap * (len(progress) - 1)) / len(progress)
        for index, item in enumerate(progress):
            progress_item(
                item, left + index * (cell_width + gap), footer_top, cell_width
            )

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
