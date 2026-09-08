"""Offline tests for live-check retry and reporting behavior."""

import asyncio
import importlib.util
import io
import sys
from pathlib import Path

import pytest
from PIL import Image

spec = importlib.util.spec_from_file_location(
    "source_checks", Path(__file__).resolve().parents[1] / "scripts" / "check_sources.py"
)
checks = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = checks
spec.loader.exec_module(checks)


def test_only_failures_retry_after_cooldown(monkeypatch) -> None:
    calls = []
    sleeps = []

    async def check(provider, api_key):
        calls.append(provider.key)
        if provider.key == "met":
            raise ValueError("broken response")
        if provider.key == "reframed" and calls.count("reframed") == 1:
            raise TimeoutError("temporary outage")
        return "Image decoded"

    async def sleep(delay):
        sleeps.append(delay)
        assert set(calls) == {"met", "reframed", "bing"}
        assert len(calls) == 3

    monkeypatch.setattr(checks, "check_provider", check)
    monkeypatch.setattr(checks.asyncio, "sleep", sleep)
    providers = {key: checks.PROVIDERS[key] for key in ("met", "reframed", "bing")}
    results = asyncio.run(checks.run_checks(providers, {}, checks.RETRY_DELAY))

    assert sleeps == [1800]
    assert calls.count("bing") == 1
    assert calls.count("met") == calls.count("reframed") == 2
    assert {key: result.status for key, result in results.items()} == {
        "met": "failed", "reframed": "recovered", "bing": "passed"
    }


def test_successes_and_missing_keys_do_not_wait(monkeypatch) -> None:
    async def check(provider, api_key):
        assert provider.key == "bing"
        return "Image decoded"

    async def sleep(delay):
        pytest.fail("No failed checks to retry")

    monkeypatch.setattr(checks, "check_provider", check)
    monkeypatch.setattr(checks.asyncio, "sleep", sleep)
    providers = {key: checks.PROVIDERS[key] for key in ("bing", "unsplash")}
    results = asyncio.run(checks.run_checks(providers, {}, 1800))

    assert results["bing"].status == "passed"
    assert results["unsplash"].status == "skipped"
    assert "UNSPLASH_ACCESS_KEY" in results["unsplash"].detail


@pytest.mark.parametrize("status, exit_code", [("failed", 1), ("recovered", 0)])
def test_final_result_controls_ci_exit(monkeypatch, tmp_path, status, exit_code) -> None:
    async def run(providers, keys, delay):
        return {"bing": checks.CheckResult(status, "Check result")}

    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr(sys, "argv", ["check_sources.py", "--providers", "bing"])
    monkeypatch.setattr(checks, "run_checks", run)

    assert checks.main() == exit_code
    assert f"| bing | {status} |" in summary.read_text()


def test_download_must_be_a_decodable_image() -> None:
    image = io.BytesIO()
    Image.new("RGB", (20, 10)).save(image, format="PNG")
    assert checks.image_dimensions(image.getvalue()) == (20, 10)
    with pytest.raises(OSError):
        checks.image_dimensions(b"<html>Service unavailable</html>")
    with pytest.raises(OSError):
        checks.image_dimensions(image.getvalue()[:45])


def test_credentials_are_redacted_from_errors() -> None:
    assert checks.redact(
        "Bad key abc+/= at ?key=abc%2B%2F%3D\nretry later", {"api_key": "abc+/="}
    ) == "Bad key [redacted] at ?key=[redacted] retry later"


def test_oversized_image_is_rejected_before_decoding(monkeypatch) -> None:
    image = io.BytesIO()
    Image.new("RGB", (20, 10)).save(image, format="PNG")
    monkeypatch.setattr(checks, "MAX_SOURCE_PIXELS", 100)

    def load(image, *args, **kwargs):
        pytest.fail("An oversized image must not be decoded")

    monkeypatch.setattr(Image.Image, "load", load)
    with pytest.raises(ValueError, match="pixel limit"):
        checks.image_dimensions(image.getvalue())
