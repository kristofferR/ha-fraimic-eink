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
PANEL_FALLBACK_URL_PATH = "fraimic_panel"

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
        try:
            _register_panel(hass, version, PANEL_URL_PATH)
            domain_data[DATA_PANEL_REGISTERED] = PANEL_URL_PATH
        except ValueError:
            _LOGGER.warning(
                "The /%s panel path is already in use; registering /%s instead",
                PANEL_URL_PATH,
                PANEL_FALLBACK_URL_PATH,
            )
            try:
                _register_panel(hass, version, PANEL_FALLBACK_URL_PATH)
            except ValueError:
                _LOGGER.exception("Could not register the Fraimic sidebar panel")
            else:
                domain_data[DATA_PANEL_REGISTERED] = PANEL_FALLBACK_URL_PATH


def _register_panel(hass: HomeAssistant, version: str, url_path: str) -> None:
    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="Fraimic",
        sidebar_icon="mdi:image-frame",
        frontend_url_path=url_path,
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
    url_path = domain_data.pop(DATA_PANEL_REGISTERED, None)
    if url_path:
        async_remove_panel(hass, url_path)
