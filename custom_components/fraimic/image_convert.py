"""Convert ordinary images into the Fraimic Spectra 6 ``.bin`` display format.

Fraimic frames use an **E Ink Spectra 6** colour panel. The buffer is a raw,
header-less, uncompressed 4bpp image, ``width * height / 2`` bytes total
(1600x1200 = 960,000 bytes for the 13.3" frame) — but the scan order is NOT
row-major. Verified on real hardware (firmware 0.2.21): the buffer holds the
*bottom* half of the panel first, then the top half, each half column-major
with columns scanned bottom-up and two vertically-adjacent pixels per byte.
Pixel values are the E Ink standard Spectra 6 codes (0x4 unused) — see
``_pack_nibbles`` and ``SPECTRA6_PANEL_INDEX``.

Getting good output from a tiny-gamut, low-contrast 6-colour panel is as much
about *pre-processing* as it is about the dither, so this module runs a full
pipeline: orient -> resize -> autocontrast -> contrast -> saturation -> sharpen
-> gamut soft-clamp -> dither against a *calibrated* palette in OKLab.

The frame applies no processing of its own to a ``/upload`` — the nibbles we send
are the final panel colours — so all of this happens here. Everything is
CPU-bound (Pillow / numpy) and must be run in an executor.
"""

from __future__ import annotations

import io

from .const import (
    AUTO_DOMINANCE_THRESHOLD,
    AUTO_FLAT_THRESHOLD,
    AUTOCONTRAST_CUTOFF,
    DEFAULT_CONTRAST,
    DEFAULT_HEIGHT,
    DEFAULT_MODE_RESOLVED,
    DEFAULT_SATURATION,
    DEFAULT_SHARPEN,
    DEFAULT_TONE,
    DEFAULT_WIDTH,
    FIT_CONTAIN,
    FIT_CONTAIN_BLACK,
    FIT_STRETCH,
    MAX_SOURCE_PIXELS,
    MODE_ATKINSON,
    MODE_AUTO,
    MODE_BAYER,
    MODE_FLOYD_STEINBERG,
    MODE_NONE,
    NEUTRAL_CHROMA_T,
    NEUTRAL_WEIGHT,
    SPECTRA6_LEVELS,
    SPECTRA6_PANEL_INDEX,
    SPECTRA6_RGB,
)

# Lazily register extra Pillow decoders (HEIC/HEIF/AVIF via pillow-heif) once.
# iPhone photos and modern photo-library media sources (immich, Synology
# Photos, ...) commonly serve HEIC/AVIF, which stock Pillow can't open.
_extra_decoders_loaded = False


def _ensure_extra_decoders() -> None:
    global _extra_decoders_loaded  # noqa: PLW0603 - simple one-shot latch
    if _extra_decoders_loaded:
        return
    _extra_decoders_loaded = True
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    except Exception:  # noqa: BLE001 - optional; degrade to Pillow's own formats
        pass
    try:
        # pillow-heif < 1.0 shipped AVIF support; 1.0+ removed it in favour of
        # Pillow's native AVIF (11.2+). Register it only where it still exists.
        from pillow_heif import register_avif_opener

        register_avif_opener()
    except Exception:  # noqa: BLE001
        pass


def _sniff_format(raw: bytes) -> str:
    """Best-effort human-readable guess of what unidentifiable bytes are."""
    head = raw[:64]
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12].decode("ascii", "replace")
        if brand.startswith(("heic", "heix", "hevc", "heim", "heis", "mif1", "msf1")):
            return "a HEIC/HEIF image (install pillow-heif)"
        if brand.startswith(("avif", "avis")):
            return "an AVIF image (install pillow-heif)"
        return f"an ISO media file '{brand}' — probably a video, not an image"
    if head[:4] == b"\x1aE\xdf\xa3":
        return "a Matroska/WebM video, not an image"
    if head[:4] == b"%PDF":
        return "a PDF, not an image"
    if head[:7] == b"#EXTM3U":
        return "an HLS stream playlist — use a camera snapshot instead"
    if head[:5].lower() in (b"<html", b"<!doc") or b"<html" in raw[:512].lower():
        return "an HTML page — the URL likely needs auth or is wrong"
    if head[:2] == b"ID" or head[:4] == b"OggS" or head[:4] == b"fLaC":
        return "an audio file, not an image"
    if head[:4] == b"<svg" or b"<svg" in raw[:512]:
        return "an SVG (vector) — not supported, rasterise it first"
    return "an unrecognised format"


# 8x8 Bayer threshold matrix (values 0..63), used for ordered dithering.
_BAYER8 = (
    (0, 32, 8, 40, 2, 34, 10, 42),
    (48, 16, 56, 24, 50, 18, 58, 26),
    (12, 44, 4, 36, 14, 46, 6, 38),
    (60, 28, 52, 20, 62, 30, 54, 22),
    (3, 35, 11, 43, 1, 33, 9, 41),
    (51, 19, 59, 27, 49, 17, 57, 25),
    (15, 47, 7, 39, 13, 45, 5, 37),
    (63, 31, 55, 23, 61, 29, 53, 21),
)

# Error-diffusion kernels as (dx, dy, weight) with weights summing to <= 1.
_FLOYD_STEINBERG_KERNEL = (
    (1, 0, 7 / 16),
    (-1, 1, 3 / 16),
    (0, 1, 5 / 16),
    (1, 1, 1 / 16),
)
_ATKINSON_KERNEL = (
    (1, 0, 1 / 8),
    (2, 0, 1 / 8),
    (-1, 1, 1 / 8),
    (0, 1, 1 / 8),
    (1, 1, 1 / 8),
    (0, 2, 1 / 8),
)


def _srgb_to_linear(values):
    """sRGB [0,1] -> linear-light [0,1] (vectorised)."""
    import numpy as np

    return np.where(values <= 0.04045, values / 12.92, ((values + 0.055) / 1.055) ** 2.4)


def _linear_to_oklab(linear):
    """Linear sRGB (...,3) -> OKLab (...,3) (vectorised)."""
    import numpy as np

    r, g, b = linear[..., 0], linear[..., 1], linear[..., 2]
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = np.cbrt(l), np.cbrt(m), np.cbrt(s)
    return np.stack(
        (
            0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
        ),
        axis=-1,
    )


def _palette_oklab():
    """Return the calibrated Spectra 6 palette as an OKLab (6,3) float array."""
    import numpy as np

    rgb = np.array(SPECTRA6_RGB, dtype=np.float64) / 255.0
    return _linear_to_oklab(_srgb_to_linear(rgb))


def _tone_curve_lut(strength: float) -> list[int] | None:
    """A filmic S-curve LUT (per channel, x3) for ``strength`` 0-100, or None.

    The sigmoid lifts midtone contrast while smoothly rolling off shadows and
    highlights, so extremes compress instead of clipping — fitting more of the
    image into the panel's limited dynamic range.
    """
    import math

    k = strength / 100.0 * 8.0  # map 0-100 -> sigmoid steepness 0-8
    if k < 0.05:
        return None
    s0 = 1.0 / (1.0 + math.exp(k * 0.5))
    s1 = 1.0 / (1.0 + math.exp(-k * 0.5))
    span = s1 - s0
    lut = []
    for i in range(256):
        s = 1.0 / (1.0 + math.exp(-k * (i / 255.0 - 0.5)))
        lut.append(max(0, min(255, round((s - s0) / span * 255.0))))
    return lut * 3  # apply identically to R, G, B


def _preprocess(
    image, saturation: float, contrast: float, sharpen: float, tone: float
):
    """Apply tone / contrast / saturation / sharpening to an RGB Pillow image."""
    from PIL import ImageEnhance, ImageFilter, ImageOps

    # Stretch to a full black/white point, clipping a tiny tail each end.
    image = ImageOps.autocontrast(image, cutoff=AUTOCONTRAST_CUTOFF)
    # Filmic tone curve: midtone contrast with shadow/highlight rolloff.
    if (lut := _tone_curve_lut(tone)) is not None:
        image = image.point(lut)
    if abs(contrast - 1.0) > 1e-3:
        image = ImageEnhance.Contrast(image).enhance(contrast)
    if abs(saturation - 1.0) > 1e-3:
        image = ImageEnhance.Color(image).enhance(saturation)
    if sharpen > 0:
        image = image.filter(
            ImageFilter.UnsharpMask(radius=1.0, percent=int(round(sharpen)), threshold=2)
        )
    return image


def _fit_image(image, width: int, height: int, fit: str):
    """Resize an RGB ``image`` to ``width`` x ``height`` using ``fit``."""
    from PIL import Image, ImageOps

    size = (width, height)
    if fit == FIT_STRETCH:
        return image.resize(size, Image.Resampling.LANCZOS)
    if fit in (FIT_CONTAIN, FIT_CONTAIN_BLACK):
        # Letterbox so nothing is cropped: white bars (photo-mat look) or black.
        color = (0, 0, 0) if fit == FIT_CONTAIN_BLACK else (255, 255, 255)
        return ImageOps.pad(image, size, method=Image.Resampling.LANCZOS, color=color)
    return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def _gamut_soft_clamp(oklab, palette):
    """Soft-compress chroma toward the palette's reach so saturated input doesn't
    overshoot and collapse during dithering. Black/white (chroma ~0) are ignored."""
    import numpy as np

    pal_chroma = np.hypot(palette[:, 1], palette[:, 2])
    ceiling = float(pal_chroma.max()) * 1.3
    if ceiling <= 0:
        return oklab
    a, b = oklab[..., 1], oklab[..., 2]
    chroma = np.hypot(a, b)
    scale = np.where(chroma > 1e-6, ceiling * np.tanh(chroma / ceiling) / np.maximum(chroma, 1e-6), 1.0)
    out = oklab.copy()
    out[..., 1] = a * scale
    out[..., 2] = b * scale
    return out


def _palette_distances(flat, palette):
    """Squared OKLab distance to each palette colour + the neutral penalty.

    Returns an (N, P) float32 array. Computed one palette colour at a time to
    avoid the huge (N, P, 3) broadcast temporary (~530 MB on the 2560x1440 frame).
    """
    import numpy as np

    n = flat.shape[0]
    pal_chroma2 = palette[:, 1] ** 2 + palette[:, 2] ** 2  # (P,)
    px_chroma = np.sqrt(flat[:, 1] ** 2 + flat[:, 2] ** 2)
    factor = (NEUTRAL_WEIGHT * np.clip(1.0 - px_chroma / NEUTRAL_CHROMA_T, 0.0, None)).astype(
        np.float32
    )  # (N,)

    dist = np.empty((n, palette.shape[0]), dtype=np.float32)
    for i in range(palette.shape[0]):
        diff = flat - palette[i]  # (N, 3)
        dist[:, i] = np.einsum("ij,ij->i", diff, diff).astype(np.float32)
        dist[:, i] += factor * float(pal_chroma2[i])
    return dist


def _nearest(oklab_flat, palette):
    """Vectorised nearest-palette index for a flat (N,3) OKLab array."""
    return _palette_distances(oklab_flat, palette).argmin(axis=1).astype("uint8")


def _bayer_indices(oklab, palette, width: int, height: int):
    """Ordered dithering: blend between the two nearest palette colours using an
    8x8 Bayer threshold. Great for flat graphics; fully vectorised."""
    import numpy as np

    flat = oklab.reshape(-1, 3)
    dist = _palette_distances(flat, palette)
    i1 = dist.argmin(axis=1)
    d2 = dist.copy()
    d2[np.arange(d2.shape[0]), i1] = np.inf
    i2 = d2.argmin(axis=1)

    c1 = palette[i1]
    c2 = palette[i2]
    seg = c2 - c1
    seg_len2 = (seg * seg).sum(axis=1)
    t = ((flat - c1) * seg).sum(axis=1) / np.maximum(seg_len2, 1e-9)
    t = np.clip(t, 0.0, 1.0)

    bayer = (np.array(_BAYER8, dtype=np.float64) + 0.5) / 64.0
    thresh = np.tile(bayer, ((height + 7) // 8, (width + 7) // 8))[:height, :width].reshape(-1)

    chosen = np.where(t > thresh, i2, i1)
    return chosen.astype(np.uint8)


def _error_diffuse(oklab, palette, kernel, width: int, height: int):
    """Serpentine error diffusion in OKLab space (sequential per pixel).

    Only materialises the few rows the kernel touches (current + up to 2 ahead)
    as Python lists at a time, instead of list-converting the whole frame, so a
    large frame (2560x1440) doesn't balloon memory.

    The error-adjusted target is clamped to just beyond the palette's reach
    before matching, and the *clamped* value drives the diffused error. FS
    kernels conserve error, so on out-of-gamut regions (a colour the panel
    simply cannot mix) the residual otherwise accumulates without bound and
    smears across whatever comes next — verified on real hardware as yellow
    blobs trailing saturated patches and text tinted by a colour field above
    it. Clamping discards the unrepresentable excess instead of propagating it.
    """
    import numpy as np

    pal = palette.tolist()
    pal_chroma2 = [p[1] * p[1] + p[2] * p[2] for p in pal]
    # Clamp bounds: L slightly past black/white; chroma to the same ceiling the
    # pre-dither gamut soft-clamp compresses to (palette reach + dither margin).
    chroma_cap = max(c2 for c2 in pal_chroma2) ** 0.5 * 1.3
    chroma_cap2 = chroma_cap * chroma_cap
    out = bytearray(width * height)

    rows: dict[int, list] = {}

    def get_row(yy: int) -> list:
        row = rows.get(yy)
        if row is None:
            row = oklab[yy].tolist()
            rows[yy] = row
        return row

    for y in range(height):
        row = get_row(y)
        left_to_right = (y % 2) == 0
        xs = range(width) if left_to_right else range(width - 1, -1, -1)
        for x in xs:
            px = row[x]
            # Clamp the error-adjusted target to the panel's reachable gamut
            # (see docstring) — the clamped value also drives the error below.
            l = px[0]
            if l < -0.05:
                l = -0.05
            elif l > 1.05:
                l = 1.05
            a_, b_ = px[1], px[2]
            c2 = a_ * a_ + b_ * b_
            if c2 > chroma_cap2:
                scale = chroma_cap / c2**0.5
                a_ *= scale
                b_ *= scale
            px = (l, a_, b_)
            # Neutral preservation: penalise chromatic palette entries when this
            # pixel is near-grey, so neutrals dither between black/white only.
            px_chroma = (px[1] * px[1] + px[2] * px[2]) ** 0.5
            factor = 1.0 - px_chroma / NEUTRAL_CHROMA_T
            if factor < 0.0:
                factor = 0.0
            factor *= NEUTRAL_WEIGHT
            # nearest palette colour (with neutral penalty)
            best_i = 0
            best_d = 1e30
            for i in range(SPECTRA6_LEVELS):
                p = pal[i]
                dl = px[0] - p[0]
                da = px[1] - p[1]
                db = px[2] - p[2]
                d = dl * dl + da * da + db * db + factor * pal_chroma2[i]
                if d < best_d:
                    best_d = d
                    best_i = i
            out[y * width + x] = best_i
            chosen = pal[best_i]
            el = px[0] - chosen[0]
            ea = px[1] - chosen[1]
            eb = px[2] - chosen[2]
            for dx, dy, w in kernel:
                sx = x + dx if left_to_right else x - dx
                ny = y + dy
                if 0 <= sx < width and ny < height:
                    tgt = (row if ny == y else get_row(ny))[sx]
                    tgt[0] += el * w
                    tgt[1] += ea * w
                    tgt[2] += eb * w
        rows.pop(y, None)  # done with this row; release it

    return np.frombuffer(bytes(out), dtype=np.uint8)


def _auto_mode(image) -> str:
    """Pick the best dither mode for ``image`` (a Pillow RGB image).

    Flat graphics / UI / illustrations (large regions of identical colour, few
    distinct colours) dither best with ordered/Bayer; photographs (continuous
    tone, lots of colours, no exactly-equal neighbours) want error diffusion.
    """
    import numpy as np

    thumb = image.copy()
    thumb.thumbnail((256, 256))
    arr = np.asarray(thumb, dtype=np.int16)

    # A 1x1 (or degenerate) source has no neighbours to compare — just use the
    # default error-diffusion mode rather than dividing by zero.
    if arr.shape[0] < 2 or arr.shape[1] < 2:
        return MODE_FLOYD_STEINBERG

    # Fraction of adjacent pixels that are *exactly* equal — high for graphics,
    # low for photos (sensor/compression noise breaks exact equality).
    dx = np.abs(arr[:, 1:, :] - arr[:, :-1, :]).max(axis=2)
    dy = np.abs(arr[1:, :, :] - arr[:-1, :, :]).max(axis=2)
    flat_fraction = ((dx == 0).sum() + (dy == 0).sum()) / (dx.size + dy.size)

    # Colour dominance: do the top-8 colours (quantised to 5 bits/channel) cover
    # most of the image? Graphics yes; photos spread across many colours.
    q = np.asarray(thumb, dtype=np.uint8) >> 3
    packed = (q[..., 0].astype(np.uint32) << 10) | (q[..., 1] << 5) | q[..., 2]
    counts = np.bincount(packed.reshape(-1))
    dominance = float(np.sort(counts)[-8:].sum()) / packed.size

    if flat_fraction > AUTO_FLAT_THRESHOLD and dominance > AUTO_DOMINANCE_THRESHOLD:
        return MODE_BAYER
    return MODE_FLOYD_STEINBERG


def _resolve_mode(mode: str) -> str:
    return DEFAULT_MODE_RESOLVED if mode == MODE_AUTO else mode


def _render_indices(image, width: int, height: int, mode: str):
    """Return a flat numpy array of Spectra 6 palette indices for ``image``."""
    import numpy as np

    palette = _palette_oklab()
    arr = np.asarray(image, dtype=np.float64) / 255.0  # (H, W, 3) sRGB
    oklab = _linear_to_oklab(_srgb_to_linear(arr))
    oklab = _gamut_soft_clamp(oklab, palette)

    mode = _resolve_mode(mode)
    if mode == MODE_NONE:
        return _nearest(oklab.reshape(-1, 3), palette)
    if mode == MODE_BAYER:
        return _bayer_indices(oklab, palette, width, height)
    if mode == MODE_ATKINSON:
        return _error_diffuse(oklab, palette, _ATKINSON_KERNEL, width, height)
    # MODE_FLOYD_STEINBERG (and the resolved default)
    return _error_diffuse(oklab, palette, _FLOYD_STEINBERG_KERNEL, width, height)


def _pack_nibbles(indices, width: int, height: int) -> bytes:
    """Pack per-pixel palette positions into the frame's native buffer layout.

    Reverse-engineered on real hardware (firmware 0.2.21) with test patterns:
    the buffer is NOT a row-major scan of the panel. It is two 4bpp halves —
    the *bottom* half of the panel first, then the top half — and each half is
    column-major: panel columns left-to-right, each column scanned *bottom-up*,
    two vertically-adjacent pixels per byte (high nibble first). Palette
    positions are translated to the E Ink standard Spectra 6 nibbles
    (0,1,2,3,5,6 — 0x4 is unused) via SPECTRA6_PANEL_INDEX.
    """
    import numpy as np

    panel_nibble = np.array(SPECTRA6_PANEL_INDEX, dtype=np.uint8)
    arr = panel_nibble[np.asarray(indices, dtype=np.uint8) % SPECTRA6_LEVELS]
    arr = arr.reshape(height, width)

    half_h = height // 2
    parts = []
    for half in (arr[half_h:, :], arr[:half_h, :]):  # bottom half first
        # Column-major, bottom-up within each column.
        cols = np.flipud(half).T  # (width, half_h): per-column, bottom pixel first
        pairs = cols.reshape(-1, 2)
        parts.append(((pairs[:, 0] << 4) | (pairs[:, 1] & 0x0F)).astype(np.uint8))
    return np.concatenate(parts).tobytes()


def _indices_to_png(indices, width: int, height: int, preview_rotate: int = 0) -> bytes:
    """Render palette indices to a downscaled colour PNG using the calibrated RGB.

    ``preview_rotate`` (clockwise degrees) rotates the preview so it matches how
    the frame is physically mounted — the raw buffer is native-orientation, but a
    turned frame is viewed rotated, so the dashboard preview should be too.
    """
    import numpy as np
    from PIL import Image

    palette = np.array(SPECTRA6_RGB, dtype=np.uint8)
    rgb = palette[np.asarray(indices, dtype=np.uint8) % SPECTRA6_LEVELS]
    image = Image.fromarray(rgb.reshape(height, width, 3), mode="RGB")
    if preview_rotate % 360:
        image = image.rotate(-(preview_rotate % 360), expand=True)
    image.thumbnail((width // 2, height // 2), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def convert_image(
    raw: bytes,
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fit: str = "cover",
    rotate: int = 0,
    mode: str = MODE_AUTO,
    saturation: float = DEFAULT_SATURATION,
    contrast: float = DEFAULT_CONTRAST,
    sharpen: float = DEFAULT_SHARPEN,
    tone: float = DEFAULT_TONE,
    preview: bool = True,
    preview_rotate: int = 0,
) -> tuple[bytes, bytes | None, str]:
    """Convert encoded image bytes into a Fraimic Spectra 6 ``.bin`` (+ PNG preview).

    Args:
        raw: Encoded source image bytes (PNG/JPEG/...).
        width/height: Frame resolution in pixels (e.g. 1600x1200 for the 13.3").
        fit: ``cover`` (crop to fill), ``contain`` (pad), or ``stretch``.
        rotate: Clockwise rotation in degrees (0/90/180/270) applied first.
        mode: ``auto`` | ``none`` | ``bayer`` | ``floyd_steinberg`` | ``atkinson``.
        saturation/contrast: enhancement factors (1.0 = no change).
        sharpen: unsharp-mask strength 0-100 (0 disables).
        preview: also return a downscaled colour PNG of the rendered result.
        preview_rotate: rotate only the preview (clockwise) to match how the frame
            is mounted — the ``.bin`` buffer stays native-orientation.

    Returns:
        ``(bin_bytes, preview_png_or_none, resolved_mode)`` where ``bin_bytes`` is
        exactly ``width * height / 2`` bytes and ``resolved_mode`` is the concrete
        mode used (``auto`` is resolved to the mode actually chosen).
    """
    from PIL import Image, ImageOps, UnidentifiedImageError

    _ensure_extra_decoders()

    pixels = width * height
    # The native layout packs two vertically-adjacent pixels per byte within
    # each half-panel, so each half's height must itself be even.
    if height % 4:
        raise ValueError("Fraimic buffers require a height divisible by 4")
    expected = pixels // 2
    try:
        src_img = Image.open(io.BytesIO(raw))
    except UnidentifiedImageError as err:
        raise ValueError(
            f"Source is not a supported image — looks like {_sniff_format(raw)}"
        ) from err
    with src_img as src:
        # Reject decompression bombs before the full decode (size is read from
        # the header by open(), without decoding the pixels).
        if src.width * src.height > MAX_SOURCE_PIXELS:
            raise ValueError(
                f"Source image is too large ({src.width}x{src.height})"
            )
        image = ImageOps.exif_transpose(src)
        # Flatten any transparency onto white (not the default black) so PNG/logo
        # transparent areas don't turn into black blocks on the frame.
        if image.mode in ("RGBA", "LA", "PA") or (
            image.mode == "P" and "transparency" in image.info
        ):
            rgba = image.convert("RGBA")
            background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            image = Image.alpha_composite(background, rgba).convert("RGB")
        else:
            image = image.convert("RGB")
        if rotate % 360:
            image = image.rotate(-(rotate % 360), expand=True)
        # Classify BEFORE fitting/preprocessing: `contain` padding adds flat
        # borders and sharpening adds edges, both of which would skew the
        # photo-vs-graphic decision toward graphics.
        resolved = _auto_mode(image) if mode == MODE_AUTO else mode
        image = _fit_image(image, width, height, fit)
        image = _preprocess(image, saturation, contrast, sharpen, tone)
        indices = _render_indices(image, width, height, resolved)

    packed = _pack_nibbles(indices, width, height)
    if len(packed) != expected:  # pragma: no cover - guarded by fixed size
        raise ValueError(f"Converted image is {len(packed)} bytes, expected {expected}")

    preview_png = (
        _indices_to_png(indices, width, height, preview_rotate) if preview else None
    )
    return packed, preview_png, resolved


def image_to_bin(
    raw: bytes,
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fit: str = "cover",
    rotate: int = 0,
    mode: str = MODE_AUTO,
    saturation: float = DEFAULT_SATURATION,
    contrast: float = DEFAULT_CONTRAST,
    sharpen: float = DEFAULT_SHARPEN,
    tone: float = DEFAULT_TONE,
) -> bytes:
    """Convenience wrapper returning only the ``.bin`` buffer."""
    return convert_image(  # noqa: returns (bin, preview, mode); we want bin only
        raw,
        width=width,
        height=height,
        fit=fit,
        rotate=rotate,
        mode=mode,
        saturation=saturation,
        contrast=contrast,
        sharpen=sharpen,
        tone=tone,
        preview=False,
    )[0]
