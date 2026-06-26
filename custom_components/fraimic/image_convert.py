"""Convert ordinary images into the Fraimic Spectra 6 ``.bin`` display format.

Fraimic frames use an **E Ink Spectra 6** colour panel. The buffer is a raw,
header-less, uncompressed image where every pixel is a 4-bit palette index
into the 6-colour Spectra palette, packed two pixels per byte (high nibble =
left/even pixel, low nibble = right/odd pixel), scanned left-to-right then
top-to-bottom. Total size is ``width * height / 2`` bytes (1600x1200 = 960,000
bytes for the 13.3" frame).

Only indices 0-5 are valid; the official "guide" calling this "4-bit grayscale"
is wrong (confirmed by reverse engineering — see README).

All work here is CPU-bound (Pillow / numpy) and must be run in an executor.
"""

from __future__ import annotations

import io

from .const import (
    DEFAULT_WIDTH,
    FIT_CONTAIN,
    FIT_STRETCH,
    SPECTRA6,
    SPECTRA6_LEVELS,
)
from .const import DEFAULT_HEIGHT as _DEFAULT_HEIGHT


def _build_palette_image():
    """Return a Pillow ``P`` image whose 256 slots cycle through the 6 colours.

    Padding the palette by *cycling* the 6 colours (rather than with zeros) is
    essential: zero-padding makes Pillow's quantizer assign large indices to
    near-black pixels (several palette entries compete for black), which renders
    as garbage. After quantizing we clamp every index with ``% 6``.
    """
    from PIL import Image

    raw: list[int] = []
    for i in range(256):
        raw.extend(SPECTRA6[i % SPECTRA6_LEVELS])
    pal_img = Image.new("P", (1, 1))
    pal_img.putpalette(raw)
    return pal_img


def _fit_image(image, width: int, height: int, fit: str):
    """Resize an RGB ``image`` to ``width`` x ``height`` using ``fit``."""
    from PIL import Image, ImageOps

    size = (width, height)
    if fit == FIT_STRETCH:
        return image.resize(size, Image.Resampling.LANCZOS)
    if fit == FIT_CONTAIN:
        # Letterbox onto a black background so nothing is cropped.
        return ImageOps.pad(image, size, method=Image.Resampling.LANCZOS, color=(0, 0, 0))
    # FIT_COVER (default): scale to fill, then centre-crop the overflow.
    return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def _nearest_indices(rgb_bytes: bytes):
    """Map an RGB byte buffer to nearest Spectra 6 index (no dithering)."""
    import numpy as np

    pixels = np.frombuffer(rgb_bytes, dtype=np.uint8).reshape(-1, 3).astype(np.int16)
    palette = np.array(SPECTRA6, dtype=np.int16)
    # Luminance-weighted squared distance to each palette colour.
    weights = np.array([0.299, 0.587, 0.114], dtype=np.float32)
    diff = pixels[:, None, :] - palette[None, :, :]
    dist = (diff.astype(np.float32) ** 2 * weights).sum(axis=2)
    return dist.argmin(axis=1).astype(np.uint8)


def _pack_nibbles(indices) -> bytes:
    """Pack a per-pixel index buffer (values 0-5) into two-pixels-per-byte."""
    import numpy as np

    arr = np.asarray(indices, dtype=np.uint8)
    arr = arr % SPECTRA6_LEVELS  # clamp to valid palette indices
    arr = arr.reshape(-1, 2)
    packed = (arr[:, 0] << 4) | (arr[:, 1] & 0x0F)
    return packed.astype(np.uint8).tobytes()


def _render_indices(raw: bytes, width: int, height: int, fit: str, rotate: int, dither: bool):
    """Return a flat numpy array of Spectra 6 palette indices for the frame."""
    import numpy as np
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(raw)) as src:
        image = ImageOps.exif_transpose(src).convert("RGB")
        if rotate % 360:
            image = image.rotate(-(rotate % 360), expand=True)
        image = _fit_image(image, width, height, fit)

        if dither:
            # Pillow's native Floyd-Steinberg against the cycled palette, then
            # clamp the resulting indices back into 0-5.
            quantized = image.quantize(palette=_build_palette_image(), dither=Image.Dither.FLOYDSTEINBERG)
            indices = np.frombuffer(quantized.tobytes(), dtype=np.uint8) % SPECTRA6_LEVELS
        else:
            indices = _nearest_indices(image.tobytes())

    return indices


def _indices_to_png(indices, width: int, height: int) -> bytes:
    """Render palette indices back to a downscaled colour PNG for previews."""
    import numpy as np
    from PIL import Image

    palette = np.array(SPECTRA6, dtype=np.uint8)
    rgb = palette[np.asarray(indices, dtype=np.uint8) % SPECTRA6_LEVELS]
    image = Image.fromarray(rgb.reshape(height, width, 3), mode="RGB")
    image.thumbnail((width // 2, height // 2), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def convert_image(
    raw: bytes,
    *,
    width: int = DEFAULT_WIDTH,
    height: int = _DEFAULT_HEIGHT,
    fit: str = "cover",
    rotate: int = 0,
    dither: bool = True,
    preview: bool = True,
) -> tuple[bytes, bytes | None]:
    """Convert encoded image bytes into a Fraimic Spectra 6 ``.bin`` (+ PNG preview).

    Args:
        raw: Encoded source image bytes (PNG/JPEG/...).
        width: Frame width in pixels (e.g. 1600 for the 13.3" frame).
        height: Frame height in pixels (e.g. 1200 for the 13.3" frame).
        fit: ``cover`` (crop to fill), ``contain`` (pad), or ``stretch``.
        rotate: Clockwise rotation in degrees (0/90/180/270) applied first.
        dither: Apply Floyd-Steinberg dithering to the 6-colour palette.
        preview: Also return a downscaled colour PNG of the rendered result.

    Returns:
        ``(bin_bytes, preview_png_or_none)`` where ``bin_bytes`` is exactly
        ``width * height / 2`` bytes.
    """
    expected = width * height // 2
    indices = _render_indices(raw, width, height, fit, rotate, dither)

    packed = _pack_nibbles(indices)
    if len(packed) != expected:  # pragma: no cover - guarded by fixed size
        raise ValueError(f"Converted image is {len(packed)} bytes, expected {expected}")

    preview_png = _indices_to_png(indices, width, height) if preview else None
    return packed, preview_png


def image_to_bin(
    raw: bytes,
    *,
    width: int = DEFAULT_WIDTH,
    height: int = _DEFAULT_HEIGHT,
    fit: str = "cover",
    rotate: int = 0,
    dither: bool = True,
) -> bytes:
    """Convenience wrapper returning only the ``.bin`` buffer."""
    return convert_image(
        raw, width=width, height=height, fit=fit, rotate=rotate, dither=dither, preview=False
    )[0]
