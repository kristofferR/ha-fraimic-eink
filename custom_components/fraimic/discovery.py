"""Local subnet scanning for Fraimic frames.

One probe/scan helper serves two callers: the coordinator's IP-change
self-healing (looks for one known device_key) and the periodic sweep below,
which feeds unconfigured frames into Home Assistant's Discovered card. The
sweep complements zeroconf/DHCP, which miss frames on networks without mDNS
reflection or DHCP snooping.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import time
from collections.abc import Iterable, Mapping
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.components import network
from homeassistant.config_entries import (
    SOURCE_INTEGRATION_DISCOVERY,
    ConfigEntry,
    ConfigEntryState,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import discovery_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.start import async_at_started

from .const import CONF_NETWORK_SCAN, DEFAULT_NETWORK_SCAN, DOMAIN
from .coordinator import normalize_info

_LOGGER = logging.getLogger(__name__)

SCAN_CONCURRENCY = 32
PROBE_TIMEOUT = 1.0  # per-host /api/info probe
RESOLVE_TIMEOUT = 2.0  # per configured hostname
SWEEP_INTERVAL = timedelta(minutes=20)
# Entry reloads restart the sweep; don't rescan the LAN for each one.
SWEEP_MIN_GAP = 300  # seconds
DATA_DISCOVERY_SWEEP = "discovery_sweep"
DATA_LAST_SWEEP = "discovery_last_sweep"

type ScanResult = dict[str, tuple[str, dict[str, Any]]]


async def async_scan_subnet(
    hass: HomeAssistant,
    subnet: ipaddress.IPv4Network,
    *,
    timeout: float = PROBE_TIMEOUT,
) -> ScanResult:
    """Probe every host's ``/api/info``; map device_key -> (ip, normalized info)."""
    session = async_get_clientsession(hass)
    semaphore = asyncio.Semaphore(SCAN_CONCURRENCY)

    async def probe(ip: str) -> tuple[str, dict[str, Any]] | None:
        async with semaphore:
            try:
                async with session.get(
                    f"http://{ip}/api/info",
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    if resp.status != 200:
                        return None
                    raw = await resp.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                return None
        if not isinstance(raw, dict):
            return None
        info = normalize_info(raw)
        return (ip, info) if info.get("device_key") else None

    results = await asyncio.gather(*(probe(str(ip)) for ip in subnet.hosts()))
    return {str(info["device_key"]): (ip, info) for ip, info in filter(None, results)}


def local_subnets(adapters: Iterable[Mapping[str, Any]]) -> list[ipaddress.IPv4Network]:
    """Private IPv4 /24s (or smaller) of Home Assistant's enabled adapters.

    Capped at /24 so a /16 LAN never turns into a 65k-host sweep. Loopback,
    link-local, CGNAT/Tailscale and public ranges are skipped.
    """
    subnets: list[ipaddress.IPv4Network] = []
    for adapter in adapters:
        if not adapter.get("enabled"):
            continue
        for addr in adapter.get("ipv4") or ():
            try:
                ip = ipaddress.IPv4Address(addr["address"])
                prefix = max(int(addr.get("network_prefix") or 24), 24)
            except (KeyError, TypeError, ValueError):
                continue
            if not ip.is_private or ip.is_loopback or ip.is_link_local:
                continue
            subnet = ipaddress.IPv4Network(f"{ip}/{prefix}", strict=False)
            if subnet not in subnets:
                subnets.append(subnet)
    return subnets


def unconfigured_frames(
    found: ScanResult,
    entries: Iterable[ConfigEntry],
    resolved_hosts: Iterable[str] = (),
) -> ScanResult:
    """Drop frames that already have an entry, including ignored/disabled ones.

    Hosts are matched too: pre-device_key entries keep a host-based unique_id
    until their first successful poll backfills it. ``resolved_hosts`` adds
    the IPs that hostname-configured entries (fraimic.local) resolve to.
    """
    known_ids: set[str] = set()
    known_hosts: set[str] = set(resolved_hosts)
    for entry in entries:
        if entry.unique_id:
            known_ids.add(entry.unique_id)
        if host := entry.data.get(CONF_HOST):
            known_hosts.add(str(host).lower())
    return {
        key: (ip, info)
        for key, (ip, info) in found.items()
        if key not in known_ids and ip not in known_hosts
    }


def sweep_enabled(entries: Iterable[ConfigEntry]) -> bool:
    """The sweep is global and needs a loaded frame; any one can opt out."""
    active = [entry for entry in entries if entry.state is ConfigEntryState.LOADED]
    return bool(active) and all(
        entry.options.get(CONF_NETWORK_SCAN, DEFAULT_NETWORK_SCAN) for entry in active
    )


@callback
def async_start_sweep(hass: HomeAssistant) -> CALLBACK_TYPE:
    """Sweep once Home Assistant has started, then every ``SWEEP_INTERVAL``."""

    task: asyncio.Task[None] | None = None

    @callback
    def _run(_arg: Any = None) -> None:
        nonlocal task
        if task is not None and not task.done():
            return
        task = hass.async_create_background_task(
            _async_sweep(hass), "fraimic-discovery-sweep"
        )

    cancel_started = async_at_started(hass, _run)
    cancel_interval = async_track_time_interval(
        hass, _run, SWEEP_INTERVAL, cancel_on_shutdown=True
    )

    @callback
    def _stop() -> None:
        cancel_started()
        cancel_interval()
        if task is not None:
            task.cancel()

    return _stop


async def _async_sweep(hass: HomeAssistant) -> None:
    domain_data = hass.data.setdefault(DOMAIN, {})
    now = time.monotonic()
    last = domain_data.get(DATA_LAST_SWEEP)
    if last is not None and now - last < SWEEP_MIN_GAP:
        return
    entries = hass.config_entries.async_entries(DOMAIN)
    if not sweep_enabled(entries):
        return
    subnets = local_subnets(await network.async_get_adapters(hass))
    if not subnets:
        _LOGGER.debug("No private IPv4 subnet found; skipping frame sweep")
        return
    domain_data[DATA_LAST_SWEEP] = now
    for subnet in subnets:
        found = await async_scan_subnet(hass, subnet)
        # Re-read entries: one may have been added, unloaded, or opted out
        # while the scan ran.
        entries = hass.config_entries.async_entries(DOMAIN)
        if not sweep_enabled(entries):
            return
        new = unconfigured_frames(found, entries, await _async_resolve_hosts(entries))
        for device_key, (ip, _info) in new.items():
            # device_key doubles as the frame's cloud credential; never log it.
            _LOGGER.debug("Sweep found an unconfigured frame at %s", ip)
            discovery_flow.async_create_flow(
                hass,
                DOMAIN,
                context={"source": SOURCE_INTEGRATION_DISCOVERY},
                data={CONF_HOST: ip, "device_key": device_key},
            )


async def _async_resolve_hosts(entries: Iterable[ConfigEntry]) -> set[str]:
    """IPv4 addresses of entries configured by hostname (best effort)."""
    loop = asyncio.get_running_loop()
    hostnames = set()
    for entry in entries:
        host = str(entry.data.get(CONF_HOST) or "")
        try:
            ipaddress.IPv4Address(host)
        except ValueError:
            if host:
                hostnames.add(host)

    async def resolve(host: str) -> set[str]:
        try:
            infos = await asyncio.wait_for(
                loop.getaddrinfo(host, None, family=socket.AF_INET), RESOLVE_TIMEOUT
            )
        except (OSError, TimeoutError):
            return set()
        return {str(info[4][0]) for info in infos}

    resolved = await asyncio.gather(*(resolve(host) for host in hostnames))
    return set().union(*resolved)
