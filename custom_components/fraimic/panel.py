"""Sidebar panel + Lovelace card registration.

Serves the bundled frontend (``frontend/``) from a static path and registers a
"Fraimic" sidebar panel plus the card as an extra frontend module. URLs carry
the integration version as a cache-buster so browsers pick up new releases.
"""

from __future__ import annotations

import logging

from pathlib import Path

from homeassistant.components.frontend import (
    add_extra_js_url,
    async_register_built_in_panel,
    async_remove_panel,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

URL_BASE = "/fraimic_static"
PANEL_URL_PATH = "fraimic"

DATA_STATIC_REGISTERED = "static_registered"
DATA_PANEL_REGISTERED = "panel_registered"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register static assets (once per HA run) and the sidebar panel."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    integration = await async_get_integration(hass, DOMAIN)
    version = integration.version or "0"

    if not domain_data.get(DATA_STATIC_REGISTERED):
        domain_data[DATA_STATIC_REGISTERED] = True
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    URL_BASE, str(Path(__file__).parent / "frontend"), cache_headers=True
                )
            ]
        )
        # Auto-loads the Lovelace card for every dashboard — no manual
        # resource registration step for users.
        add_extra_js_url(hass, f"{URL_BASE}/fraimic-card.js?v={version}")

    if not domain_data.get(DATA_PANEL_REGISTERED):
        domain_data[DATA_PANEL_REGISTERED] = True
        async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title="Fraimic",
            sidebar_icon="mdi:image-frame",
            frontend_url_path=PANEL_URL_PATH,
            require_admin=False,
            config={
                "_panel_custom": {
                    "name": "fraimic-panel",
                    "module_url": f"{URL_BASE}/fraimic-panel.js?v={version}",
                    "embed_iframe": False,
                    "trust_external": False,
                }
            },
        )


@callback
def async_unregister_panel(hass: HomeAssistant) -> None:
    """Remove the sidebar panel (static paths cannot be unregistered)."""
    domain_data = hass.data.get(DOMAIN, {})
    if domain_data.pop(DATA_PANEL_REGISTERED, None):
        async_remove_panel(hass, PANEL_URL_PATH)
