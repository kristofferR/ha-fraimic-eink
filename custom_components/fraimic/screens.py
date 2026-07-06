"""Screen store: config subentries <-> ScreenConfig.

Screens created in the UI are stored as config subentries (type "screen")
whose ``data`` is exactly the ``fraimic.render_screen`` service payload shape
— one schema, two front doors, so a screen built in YAML can be recreated in
the UI and vice versa.

Deliberately free of Home Assistant imports (entries are duck-typed) so the
headless test suite can exercise it.
"""

from __future__ import annotations

import logging

import voluptuous as vol

from .render.schema import SCREEN_SCHEMA, ScreenConfig, screen_from_dict

_LOGGER = logging.getLogger(__name__)

SUBENTRY_TYPE_SCREEN = "screen"


class AmbiguousScreenNameError(ValueError):
    """Raised when a name lookup matches more than one stored screen."""

    def __init__(self, name: str, screen_ids: list[str]) -> None:
        joined = ", ".join(screen_ids)
        super().__init__(
            f"Stored screen name {name!r} is ambiguous; use a screen id instead "
            f"({joined})"
        )


def screens_from_entry(entry) -> list[ScreenConfig]:
    """All valid screen subentries of a config entry, in creation order."""
    screens: list[ScreenConfig] = []
    for subentry in getattr(entry, "subentries", {}).values():
        if subentry.subentry_type != SUBENTRY_TYPE_SCREEN:
            continue
        try:
            data = SCREEN_SCHEMA(dict(subentry.data))
        except vol.Invalid as err:
            _LOGGER.warning(
                "Screen %r (%s) has invalid stored data and is skipped: %s",
                subentry.title,
                subentry.subentry_id,
                err,
            )
            continue
        # The subentry title is the user-visible name; keep them in sync.
        data["name"] = subentry.title or data["name"]
        screens.append(screen_from_dict(data, subentry.subentry_id))
    return screens


def screen_by_key(entry, key: str) -> ScreenConfig | None:
    """Find a stored screen by subentry id or (case-insensitive) name."""
    screens = screens_from_entry(entry)
    for screen in screens:
        if screen.screen_id == key:
            return screen
    lowered = key.casefold()
    matches = [screen for screen in screens if screen.name.casefold() == lowered]
    if len(matches) > 1:
        raise AmbiguousScreenNameError(key, [screen.screen_id for screen in matches])
    if matches:
        return matches[0]
    return None
