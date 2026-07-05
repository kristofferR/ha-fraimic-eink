"""Generate custom_components/fraimic/render/mdi/mdi-paths.json.

Downloads the @mdi/svg npm package (Pictogrammers Material Design Icons,
Apache-2.0) and extracts every icon's single SVG path ``d`` attribute into one
JSON map: ``{"weather-sunny": "M3.55 19.09...", ...}``.

Dev-only; the generated JSON (plus the package LICENSE) is committed. Re-run to
pick up new MDI releases:

    uv run scripts/build_mdi_json.py
"""

from __future__ import annotations

import io
import json
import re
import tarfile
import urllib.request
from pathlib import Path

REGISTRY = "https://registry.npmjs.org/@mdi/svg"
OUT_DIR = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "fraimic"
    / "render"
    / "mdi"
)

_PATH_RE = re.compile(rb'<path d="([^"]+)"')


def main() -> None:
    with urllib.request.urlopen(REGISTRY, timeout=30) as resp:
        meta = json.load(resp)
    version = meta["dist-tags"]["latest"]
    tarball = meta["versions"][version]["dist"]["tarball"]
    print(f"@mdi/svg {version}: {tarball}")

    with urllib.request.urlopen(tarball, timeout=120) as resp:
        data = resp.read()

    icons: dict[str, str] = {}
    license_text: bytes | None = None
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            if member.name == "package/LICENSE":
                license_text = tar.extractfile(member).read()  # type: ignore[union-attr]
            if not member.name.startswith("package/svg/") or not member.name.endswith(
                ".svg"
            ):
                continue
            svg = tar.extractfile(member).read()  # type: ignore[union-attr]
            matches = _PATH_RE.findall(svg)
            if not matches:
                print(f"  skipping {member.name}: no <path d=...>")
                continue
            name = Path(member.name).stem
            icons[name] = " ".join(match.decode() for match in matches)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "mdi-paths.json"
    # Compact separators keep the file as small as possible; sorted for stable diffs.
    out.write_text(
        json.dumps(icons, separators=(",", ":"), sort_keys=True), encoding="utf-8"
    )
    (OUT_DIR / "VERSION").write_text(f"@mdi/svg {version}\n", encoding="utf-8")
    if license_text:
        (OUT_DIR / "LICENSE").write_bytes(license_text)
    print(f"wrote {len(icons)} icons -> {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
