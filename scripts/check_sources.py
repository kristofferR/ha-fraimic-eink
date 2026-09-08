# /// script
# requires-python = ">=3.13"
# dependencies = ["aiohttp", "pillow"]
# ///
"""Exercise live providers; retry failures once after a 30-minute cooldown.

Run with ``uv run scripts/check_sources.py``. These checks deliberately live
outside pytest so ordinary tests never depend on external service availability.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import quote, quote_plus

# Load the HA-free provider package without running the integration entry point.
if "fraimic" not in sys.modules:
    package = types.ModuleType("fraimic")
    package.__path__ = [
        str(Path(__file__).resolve().parents[1] / "custom_components" / "fraimic")
    ]
    sys.modules["fraimic"] = package

from fraimic.const import MAX_SOURCE_PIXELS
from fraimic.providers import PROVIDERS
from fraimic.providers.base import ArtProvider, FetchRequest
from fraimic.providers.cache import ProviderCache
from fraimic.providers.engine import async_pick_and_download

PROVIDER_TIMEOUT = 180
RETRY_DELAY = 30 * 60


@dataclass(frozen=True)
class CheckResult:
    status: Literal["passed", "recovered", "failed", "skipped"]
    detail: str


def image_dimensions(data: bytes) -> tuple[int, int]:
    """Decode the image, rejecting HTML error pages and corrupt image bodies."""
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        if image.width * image.height > MAX_SOURCE_PIXELS:
            raise ValueError("Image exceeds the integration's pixel limit")
        image.load()
        return image.size


async def check_provider(provider: ArtProvider, api_key: str | None) -> str:
    import aiohttp

    async def dimensions(data: bytes) -> tuple[int, int]:
        return await asyncio.to_thread(image_dimensions, data)

    # Every attempt gets a fresh session/cache so the retry reaches the service.
    async with asyncio.timeout(PROVIDER_TIMEOUT), aiohttp.ClientSession() as session:
        image = await async_pick_and_download(
            provider,
            session,
            ProviderCache(),
            FetchRequest(target_width=1600, target_height=1200, api_key=api_key),
            dims_of=dimensions,
        )
    return f"Metadata parsed and image decoded ({len(image.data)} bytes)"


def redact(message: str, api_keys: dict[str, str]) -> str:
    for key in api_keys.values():
        if key:
            for value in (key, quote(key, safe=""), quote_plus(key)):
                message = message.replace(value, "[redacted]")
    return " ".join(message.splitlines())


async def run_checks(
    providers: dict[str, ArtProvider], api_keys: dict[str, str], retry_delay: float
) -> dict[str, CheckResult]:
    results: dict[str, CheckResult] = {}
    semaphore = asyncio.Semaphore(4)

    async def attempt(key: str, *, retry: bool = False) -> None:
        provider = providers[key]
        api_key = api_keys.get(provider.key_option or "") or None
        if provider.requires_key and not api_key:
            result = CheckResult(
                "skipped", f"Missing {(provider.key_option or key).upper()} secret"
            )
        else:
            try:
                async with semaphore:
                    detail = await check_provider(provider, api_key)
                result = CheckResult("recovered" if retry else "passed", detail)
            except Exception as error:
                detail = redact(f"{type(error).__name__}: {error}", api_keys)
                result = CheckResult("failed", detail)
        results[key] = result
        print(f"{key}: {result.status.upper()} — {result.detail}", flush=True)

    await asyncio.gather(*(attempt(key) for key in providers))
    failed = [key for key in providers if results[key].status == "failed"]
    if failed:
        print(
            f"Retrying {', '.join(failed)} once in {retry_delay / 60:g} minutes.",
            flush=True,
        )
        await asyncio.sleep(retry_delay)
        await asyncio.gather(*(attempt(key, retry=True) for key in failed))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--providers", nargs="+", choices=sorted(PROVIDERS))
    parser.add_argument("--retry-delay", type=float, default=RETRY_DELAY)
    args = parser.parse_args()
    if not 0 <= args.retry_delay <= RETRY_DELAY:
        parser.error("--retry-delay must be between 0 and 1800 seconds")
    providers = {key: PROVIDERS[key] for key in (args.providers or PROVIDERS)}
    api_keys = {
        provider.key_option: os.environ.get(provider.key_option.upper(), "")
        for provider in providers.values()
        if provider.key_option
    }
    results = asyncio.run(run_checks(providers, api_keys, args.retry_delay))
    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
        rows = ["## Daily source checks", "", "| Source | Result | Details |", "|---|---|---|"]
        for key in providers:
            result = results[key]
            detail = result.detail.replace("|", "\\|").replace("<", "&lt;")
            rows.append(f"| {key} | {result.status} | {detail} |")
        with Path(summary_path).open("a", encoding="utf-8") as summary:
            summary.write("\n".join(rows) + "\n")
    return int(any(result.status == "failed" for result in results.values()))


if __name__ == "__main__":
    raise SystemExit(main())
