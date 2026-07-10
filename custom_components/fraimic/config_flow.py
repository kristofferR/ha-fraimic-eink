"""Config flow for the Fraimic E-Ink Canvas integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import FraimicClient, FraimicError, normalize_host
from .const import (
    ATTR_CONTRAST,
    ATTR_FIT,
    ATTR_MODE,
    ATTR_SATURATION,
    ATTR_SHARPEN,
    ATTR_TONE,
    CONF_CAMERA_INTERVAL,
    CONF_AUTO_SLEEP,
    CONF_DEFAULT_PROVIDER,
    CONF_FRAME_MODEL,
    CONF_HEIGHT,
    CONF_NASA_API_KEY,
    CONF_PEXELS_KEY,
    CONF_ROTATION,
    CONF_POWER_MODE,
    CONF_SCAN_INTERVAL,
    CONF_SMITHSONIAN_KEY,
    CONF_UNSPLASH_KEY,
    CONF_WIDTH,
    DEFAULT_CAMERA_INTERVAL,
    DEFAULT_AUTO_SLEEP,
    DEFAULT_CONTRAST,
    DEFAULT_HOST,
    DEFAULT_ROTATION,
    DEFAULT_POWER_MODE,
    DEFAULT_SATURATION,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SHARPEN,
    DEFAULT_TONE,
    DITHER_MODES,
    DOMAIN,
    FIT_COVER,
    FIT_MODES,
    FRAME_MODELS,
    MAX_BIN_SIZE,
    MIN_CAMERA_INTERVAL,
    MIN_SCAN_INTERVAL,
    MODE_AUTO,
    MODEL_CUSTOM,
    PROVIDER_KEYS,
    PROVIDER_SHUFFLE,
    POWER_MODES,
    ROTATION_OPTIONS,
)
from .coordinator import normalize_info
from .providers import PROVIDERS

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

    VERSION = 2

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
                return await self._async_resolution_or_create()

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
        return await self._async_resolution_or_create()

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Handle a frame discovered via its DHCP lease (Fraimic MAC OUIs).

        Also self-heals an existing entry: if the device_key matches a
        configured frame, the stored host is rewritten to the new lease IP.
        """
        host = discovery_info.ip
        info = await _async_probe(self.hass, host)
        if info is None:
            return self.async_abort(reason="cannot_connect")

        await self._async_set_unique_id(host, info, updates={CONF_HOST: host})
        self._host = host
        self._info = info
        self.context["title_placeholders"] = {"name": _title(host)}
        return await self._async_resolution_or_create()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the host of an existing entry without removing it."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = normalize_host(user_input[CONF_HOST])
            info = await _async_probe(self.hass, host)
            if info is None:
                errors["base"] = "cannot_connect"
            else:
                probed = info.get("device_key") or info.get("device_id")
                old_host = str(entry.data.get(CONF_HOST, "")).lower()
                if probed and entry.unique_id not in (None, "", old_host, str(probed)):
                    # The probed frame is a different physical device than the
                    # one this entry represents.
                    return self.async_abort(reason="not_same_device")
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=str(probed) if probed else entry.unique_id,
                    data_updates={CONF_HOST: host},
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST, default=entry.data.get(CONF_HOST, DEFAULT_HOST)
                    ): str
                }
            ),
            errors=errors,
        )

    async def _async_resolution_or_create(self) -> ConfigFlowResult:
        """Auto-create the entry if the frame's resolution can be detected,
        otherwise fall back to asking the user."""
        detected = _detect_resolution(self._info)
        if detected is not None:
            width, height = detected
            return self.async_create_entry(
                title=_title(self._host or ""),
                data={CONF_HOST: self._host, CONF_WIDTH: width, CONF_HEIGHT: height},
            )
        return await self.async_step_resolution()

    async def async_step_resolution(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which Fraimic model this frame is (no silent size default).

        Reached only when the resolution can't be auto-detected. The user must
        pick Standard / Large, or Custom and supply width + height.
        """
        assert self._host is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            model = user_input[CONF_FRAME_MODEL]
            if model in FRAME_MODELS:
                width, height = FRAME_MODELS[model]
                return self.async_create_entry(
                    title=_title(self._host),
                    data={CONF_HOST: self._host, CONF_WIDTH: width, CONF_HEIGHT: height},
                )
            width = user_input.get(CONF_WIDTH)
            height = user_input.get(CONF_HEIGHT)
            if not width or not height:
                errors["base"] = "custom_resolution_required"
            elif height % 4:
                # The native layout packs two vertically-adjacent pixels per
                # byte within each half-panel, so height must divide by 4.
                errors["base"] = "odd_resolution"
            elif width * height // 2 > MAX_BIN_SIZE:
                # Buffer would be too big to render/upload — reject up front.
                errors["base"] = "resolution_too_large"
            else:
                return self.async_create_entry(
                    title=_title(self._host),
                    data={CONF_HOST: self._host, CONF_WIDTH: width, CONF_HEIGHT: height},
                )

        return self.async_show_form(
            step_id="resolution",
            data_schema=vol.Schema(
                {
                    # No default — force an explicit choice so a frame is never
                    # silently given the wrong size.
                    vol.Required(CONF_FRAME_MODEL): vol.In([*FRAME_MODELS, MODEL_CUSTOM]),
                    vol.Optional(CONF_WIDTH): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=8192)
                    ),
                    vol.Optional(CONF_HEIGHT): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=8192)
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"host": self._host},
        )

    async def _async_set_unique_id(
        self, host: str, info: dict[str, Any], updates: dict | None = None
    ) -> None:
        """Use the frame's stable id as the unique id when available, else the host.

        ``device_key`` is the frame's stable per-device identifier (it also
        authenticates the frame against the Fraimic cloud), so re-adding a
        frame whose IP changed updates the stored host in place instead of
        creating a duplicate entry.
        """
        unique = info.get("device_key") or info.get("device_id") or host.lower()
        await self.async_set_unique_id(str(unique))
        self._abort_if_unique_id_configured(updates=updates or {CONF_HOST: host})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> FraimicOptionsFlow:
        """Return the options flow handler."""
        return FraimicOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Dashboard screens are managed as subentries of a frame."""
        from .screens import SUBENTRY_TYPE_SCREEN
        from .subentry_flow import ScreenSubentryFlowHandler

        return {SUBENTRY_TYPE_SCREEN: ScreenSubentryFlowHandler}


class FraimicOptionsFlow(OptionsFlow):
    """Handle the Fraimic options (poll interval, base rotation)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            provider_key = user_input.get(CONF_DEFAULT_PROVIDER)
            provider = PROVIDERS.get(provider_key)
            if (
                provider is not None
                and provider.requires_key
                and not user_input.get(provider.key_option or "")
            ):
                errors[CONF_DEFAULT_PROVIDER] = "provider_key_required"
            camera_interval = user_input.get(CONF_CAMERA_INTERVAL, 0)
            if 0 < camera_interval < MIN_CAMERA_INTERVAL:
                errors[CONF_CAMERA_INTERVAL] = "camera_interval_too_low"
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        o = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POWER_MODE,
                        default=o.get(CONF_POWER_MODE, DEFAULT_POWER_MODE),
                    ): vol.In(POWER_MODES),
                    vol.Required(
                        CONF_AUTO_SLEEP,
                        default=o.get(CONF_AUTO_SLEEP, DEFAULT_AUTO_SLEEP),
                    ): bool,
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=o.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
                    vol.Required(
                        CONF_ROTATION, default=o.get(CONF_ROTATION, DEFAULT_ROTATION)
                    ): vol.In(ROTATION_OPTIONS),
                    # How often a "playing" camera re-snapshots onto the frame.
                    # 0 disables the loop (snapshot once). Each update is a full
                    # E-Ink refresh, so a slow floor keeps battery/panel sane.
                    # The 0-or->=MIN rule is enforced in the handler above:
                    # vol.Any is not serializable for the frontend form.
                    vol.Required(
                        CONF_CAMERA_INTERVAL,
                        default=o.get(CONF_CAMERA_INTERVAL, DEFAULT_CAMERA_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0)),
                    # Per-frame image-processing defaults (overridable per upload).
                    vol.Required(
                        ATTR_MODE, default=o.get(ATTR_MODE, MODE_AUTO)
                    ): vol.In(DITHER_MODES),
                    vol.Required(
                        ATTR_FIT, default=o.get(ATTR_FIT, FIT_COVER)
                    ): vol.In(FIT_MODES),
                    vol.Required(
                        ATTR_SATURATION,
                        default=o.get(ATTR_SATURATION, DEFAULT_SATURATION),
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=3.0)),
                    vol.Required(
                        ATTR_CONTRAST, default=o.get(ATTR_CONTRAST, DEFAULT_CONTRAST)
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=3.0)),
                    vol.Required(
                        ATTR_SHARPEN, default=o.get(ATTR_SHARPEN, DEFAULT_SHARPEN)
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=100.0)),
                    vol.Required(
                        ATTR_TONE, default=o.get(ATTR_TONE, DEFAULT_TONE)
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=100.0)),
                    # Online artwork: default source for the "New artwork"
                    # button, plus optional API keys for keyed providers
                    # (leave a key empty to disable that provider).
                    vol.Required(
                        CONF_DEFAULT_PROVIDER,
                        default=o.get(CONF_DEFAULT_PROVIDER, PROVIDER_SHUFFLE),
                    ): vol.In((PROVIDER_SHUFFLE, *PROVIDER_KEYS)),
                    vol.Optional(
                        CONF_NASA_API_KEY,
                        description={"suggested_value": o.get(CONF_NASA_API_KEY)},
                    ): str,
                    vol.Optional(
                        CONF_SMITHSONIAN_KEY,
                        description={"suggested_value": o.get(CONF_SMITHSONIAN_KEY)},
                    ): str,
                    vol.Optional(
                        CONF_UNSPLASH_KEY,
                        description={"suggested_value": o.get(CONF_UNSPLASH_KEY)},
                    ): str,
                    vol.Optional(
                        CONF_PEXELS_KEY,
                        description={"suggested_value": o.get(CONF_PEXELS_KEY)},
                    ): str,
                }
            ),
            errors=errors,
        )


def _detect_resolution(info: dict[str, Any]) -> tuple[int, int] | None:
    """Work out the frame's pixel resolution from ``/api/info``, if possible.

    Tries, in order: explicit display dimensions, then model/firmware hints
    matched against the two known Fraimic models (Standard 13.3" -> 1600x1200,
    Large 31.5" -> 2560x1440). Returns ``None`` if it can't tell, so the config
    flow asks the user.
    """
    display = info.get("display") or {}
    width, height = display.get("width"), display.get("height")
    if width and height:
        try:
            return int(width), int(height)
        except (TypeError, ValueError):
            pass

    hints = " ".join(
        str(info.get(key) or "")
        for key in ("model", "firmware_version")
    ).lower()
    if any(tag in hints for tag in ("2560", "1440", "31.5", "31_5", '31"', "large")):
        return FRAME_MODELS["large"]
    if any(
        tag in hints for tag in ("1600", "1200", "13.3", "13_3", '13"', "standard")
    ):
        return FRAME_MODELS["standard"]
    return None


def _title(host: str) -> str:
    """Human-friendly entry title."""
    if host.lower() in (DEFAULT_HOST, "fraimic"):
        return "Fraimic E-Ink Canvas"
    return f"Fraimic E-Ink Canvas ({host})"
