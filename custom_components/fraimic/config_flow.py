"""Config flow for the Fraimic E-Ink Canvas integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import FraimicClient, FraimicError, normalize_host
from .const import (
    CONF_HEIGHT,
    CONF_SCAN_INTERVAL,
    CONF_WIDTH,
    DEFAULT_HEIGHT,
    DEFAULT_HOST,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WIDTH,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .coordinator import normalize_info

_LOGGER = logging.getLogger(__name__)


async def _async_probe(hass, host: str) -> dict[str, Any] | None:
    """Return the frame's normalized info, or ``None`` if unreachable."""
    client = FraimicClient(host, async_get_clientsession(hass))
    try:
        return normalize_info(await client.get_info())
    except FraimicError as err:
        _LOGGER.debug("Probe failed for %s: %s", host, err)
        return None


class FraimicConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI config flow for Fraimic."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._info: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual setup initiated by the user."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = normalize_host(user_input[CONF_HOST])
            info = await _async_probe(self.hass, host)
            if info is None:
                errors["base"] = "cannot_connect"
            else:
                await self._async_set_unique_id(host, info)
                self._host = host
                self._info = info
                return await self.async_step_resolution()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST, default=DEFAULT_HOST): str}
            ),
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a frame discovered via mDNS/zeroconf."""
        host = normalize_host(discovery_info.host or str(discovery_info.ip_address))
        info = await _async_probe(self.hass, host)
        if info is None:
            return self.async_abort(reason="cannot_connect")

        await self._async_set_unique_id(host, info, updates={CONF_HOST: host})
        self._host = host
        self._info = info
        self.context["title_placeholders"] = {"name": _title(host)}
        return await self.async_step_resolution()

    async def async_step_resolution(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the frame's display resolution (auto-filled when reported)."""
        assert self._host is not None
        if user_input is not None:
            return self.async_create_entry(
                title=_title(self._host),
                data={
                    CONF_HOST: self._host,
                    CONF_WIDTH: user_input[CONF_WIDTH],
                    CONF_HEIGHT: user_input[CONF_HEIGHT],
                },
            )

        display = self._info.get("display") or {}
        width = display.get("width") or DEFAULT_WIDTH
        height = display.get("height") or DEFAULT_HEIGHT
        return self.async_show_form(
            step_id="resolution",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_WIDTH, default=width): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=4096)
                    ),
                    vol.Required(CONF_HEIGHT, default=height): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=4096)
                    ),
                }
            ),
            description_placeholders={"host": self._host},
        )

    async def _async_set_unique_id(
        self, host: str, info: dict[str, Any], updates: dict | None = None
    ) -> None:
        """Use the device_id as the unique id when available, else the host."""
        unique = info.get("device_id") or host.lower()
        await self.async_set_unique_id(str(unique))
        self._abort_if_unique_id_configured(updates=updates or {CONF_HOST: host})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> FraimicOptionsFlow:
        """Return the options flow handler."""
        return FraimicOptionsFlow()


class FraimicOptionsFlow(OptionsFlow):
    """Handle the Fraimic options (poll interval)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)
                    )
                }
            ),
        )


def _title(host: str) -> str:
    """Human-friendly entry title."""
    if host.lower() in (DEFAULT_HOST, "fraimic"):
        return "Fraimic E-Ink Canvas"
    return f"Fraimic E-Ink Canvas ({host})"
