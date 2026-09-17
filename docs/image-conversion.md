# Image conversion

[Back to the README](../README.md#image-settings)


Fraimic frames are **E Ink Spectra 6** colour panels. The display buffer is raw and header-less,
but its layout depends on the panel. The 13.3" buffer is 960,000 bytes in two column-major
halves. The 31.5" EL315 is portrait-native 1440×2560 and uses eight padded controller blocks,
for an exact 2,304,000-byte payload. Pixel values are the E Ink standard Spectra 6 codes
(`0x4` is unused — the panel renders it as white):

| Nibble | Colour | Calibrated RGB |
|:------:|--------|:--------------:|
| 0x0 | Black  | #000000 |
| 0x1 | White  | #ffffff |
| 0x2 | Yellow | #f0e050 |
| 0x3 | Red    | #a02020 |
| 0x5 | Blue   | #5080b8 |
| 0x6 | Green  | #608050 |

Getting good results from a tiny-gamut, low-contrast 6-colour panel is as much about
pre-processing as the dither, so the integration runs a full pipeline (all in an executor):

1. **Orient + fit** — EXIF transpose, your `rotate`, then resize (`cover`/`contain`/`stretch`).
2. **Tone** — autocontrast (black/white point) + a contrast boost.
3. **Saturation** — a boost, because the Spectra gamut is small (the single biggest perceptual
   win after the palette fix).
4. **Sharpen** — a mild unsharp mask (dithering softens detail).
5. **Match against a *calibrated* palette** (the muted RGB above, **not** pure primaries — pure
   primaries are what a Spectra 6 panel can't make, and matching against them looks harsh) in
   **OKLab**, with **neutral preservation** so near-grey pixels dither between black/white instead
   of speckling with red/yellow.
6. **Dither** with the selected `mode`:
   - **`auto`** (default) — looks at the image and chooses for you: **Floyd-Steinberg** for photos,
     **Bayer** for flat graphics/UI (lots of solid colour). The mode it picked is shown on the
     `Current artwork` image entity as the `dither_mode` attribute (and logged).
   - `official` reproduces [Fraimic's published converter](https://github.com/Fraimic/fraimic_bin_converter):
     its fixed brightness/contrast/saturation enhancements, EDGE_ENHANCE → SMOOTH → SHARPEN filters,
     pure-primary RGB+luma matching, and left-to-right Atkinson diffusion. It intentionally ignores
     the saturation, contrast, sharpen, and tone settings. Choose `contain_black` as the fit mode to
     match the converter's default black letterboxing as well.
   - `floyd_steinberg` — best general error diffusion for photos.
   - `atkinson` — localised, preserves highlights; nice for portraits.
   - `bayer` — fast ordered dithering, best for flat graphics/dashboards/UI.
   - `none` — nearest colour, no dithering.
   The non-official error-diffusion modes use serpentine scanning in linear light;
   `official` intentionally keeps Fraimic's left-to-right RGB diffusion.
7. **Pack** into the frame's native controller layout and upload through the firmware-gated
   `/api/image` path (multipart `/upload` on older firmware). Error-diffusion targets are
   clamped to the panel's reachable gamut, so
   out-of-gamut colours degrade gracefully instead of smearing accumulated error across the
   image (yellow blobs trailing saturated patches — seen on real hardware before the clamp).

**Which mode?** Just leave it on `auto` — it picks per image. Use `official` for compatibility with
Fraimic's converter, or override with another mode for a specific look.

The calibrated palette comes from community reverse engineering of real Spectra 6 panels
([Toon-nooT's converter](https://github.com/Toon-nooT/PhotoPainter-E-Ink-Spectra-6-image-converter),
the [Pimoroni Inky community](https://forums.pimoroni.com/t/what-rgb-colors-are-you-using-for-the-colors-on-the-impression-spectra-6/27942)).

**Speed:** `none`/`bayer` are vectorised (well under a second at 1600×1200); the error-diffusion
modes are inherently sequential. `official` is the slowest compatibility path and can take tens of
seconds before upload, especially on low-power Home Assistant hardware. All conversion runs in the
background.


For verified firmware behaviour and controller layouts, see the [frame API reference](frame-api/routes.md).
