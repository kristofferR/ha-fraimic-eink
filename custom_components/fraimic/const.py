"""Constants for the Fraimic E-Ink Canvas integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "fraimic"

MANUFACTURER: Final = "Fraimic"
MODEL: Final = "E-Ink Canvas"

# Config / options keys
CONF_HOST: Final = "host"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_WIDTH: Final = "width"
CONF_HEIGHT: Final = "height"
CONF_FRAME_MODEL: Final = "frame_model"
CONF_ROTATION: Final = "rotation"

# Per-frame base rotation (degrees clockwise) applied to every upload, on top of
# any per-call rotate. Lets you correct how the frame is physically mounted.
DEFAULT_ROTATION: Final = 0
ROTATION_OPTIONS: Final = (0, 90, 180, 270)

DEFAULT_HOST: Final = "fraimic.local"
# The frame is battery-powered; polling /api/info every 5 minutes is a good
# balance. Users can change this in the options flow.
DEFAULT_SCAN_INTERVAL: Final = 300
MIN_SCAN_INTERVAL: Final = 30
DEFAULT_TIMEOUT: Final = 10
# The ESP32 web server is slow on large uploads; give it generous time.
UPLOAD_TIMEOUT: Final = 90

# Display / image format.
#
# Fraimic frames are E Ink Spectra 6 COLOUR panels (not grayscale). Resolution is
# stored per config entry so the different models can be configured:
#   - Standard Canvas (13.3"): 1200x1600 native (3:4). dsackr's working converter
#     used 1600x1200 (same byte count, landscape layout); both frames auto-orient,
#     so the exact layout is confirmed per frame via the real-frame test pattern.
#   - Large Canvas (31.5"): 2560x1440 (16:9).
# Known model presets, surfaced in the config flow for easy setup.
FRAME_MODELS: Final = {
    "standard": (1600, 1200),  # 13.3" — 960,000-byte buffer
    "large": (2560, 1440),     # 31.5" — 1,843,200-byte buffer
}
MODEL_CUSTOM: Final = "custom"

# Friendly model name by resolution (both Standard orientations map to Standard).
MODEL_NAMES: Final = {
    (1600, 1200): 'Standard Canvas (13.3")',
    (1200, 1600): 'Standard Canvas (13.3")',
    (2560, 1440): 'Large Canvas (31.5")',
}

DEFAULT_WIDTH: Final = 1600
DEFAULT_HEIGHT: Final = 1200
# Generous client-side ceiling — the Large Canvas buffer alone is ~1.84 MB, well
# over the small frame's documented 1 MB limit. The frame still validates size.
MAX_BIN_SIZE: Final = 4 * 1024 * 1024

# Spectra 6 palette — index order is the panel's nibble value; only 0-5 are valid.
# The packed nibble IS this index; the RGB tuples are *calibrated approximations*
# of what each colour actually looks like on the panel (used for quantization
# matching and previews). Spectra 6 colours are far more muted than monitor
# primaries, so matching against pure primaries (255,0,0 etc.) renders badly.
# Calibrated values corroborated by Toon-nooT's converter and the Pimoroni Inky
# community (red #a02020, yellow #f0e050, green #608050, blue #5080b8).
SPECTRA6_RGB: Final = (
    (0, 0, 0),        # 0 Black
    (255, 255, 255),  # 1 White
    (96, 128, 80),    # 2 Green  #608050
    (80, 128, 184),   # 3 Blue   #5080b8
    (160, 32, 32),    # 4 Red    #a02020
    (240, 224, 80),   # 5 Yellow #f0e050
)
SPECTRA6_LEVELS: Final = len(SPECTRA6_RGB)

# Dither / processing modes.
MODE_AUTO: Final = "auto"  # the integration's best general default
MODE_NONE: Final = "none"  # nearest colour, no dithering
MODE_BAYER: Final = "bayer"  # ordered dithering (fast, good for graphics)
MODE_FLOYD_STEINBERG: Final = "floyd_steinberg"
MODE_ATKINSON: Final = "atkinson"
DITHER_MODES: Final = (
    MODE_AUTO,
    MODE_NONE,
    MODE_BAYER,
    MODE_FLOYD_STEINBERG,
    MODE_ATKINSON,
)
# What MODE_AUTO resolves to — the empirically-best general result for photos.
DEFAULT_MODE_RESOLVED: Final = MODE_FLOYD_STEINBERG

# Default pre-processing parameters. Aligned with what real Spectra 6 owners use
# (e.g. Toon-nooT's converter defaults to contrast 1.5 / saturation 1.1): push
# contrast hard and saturation modestly, because the panel has no backlight and a
# small gamut. Images intentionally look over-contrasty/saturated on a monitor.
# 1.0 is a no-op for the enhance factors; sharpen is a 0-100 strength.
DEFAULT_SATURATION: Final = 1.15
DEFAULT_CONTRAST: Final = 1.4
DEFAULT_SHARPEN: Final = 80.0
# Clip this fraction off each end of the histogram for black/white-point autolevels.
AUTOCONTRAST_CUTOFF: Final = 0.5

# Neutral preservation: the calibrated palette's muted colours sit close to mid
# grey, so without this, near-neutral pixels speckle with red/yellow. We add a
# distance penalty to *chromatic* palette entries proportional to how achromatic
# the source pixel is (OKLab chroma below NEUTRAL_CHROMA_T), so greys dither
# between black/white while saturated regions keep their colour.
NEUTRAL_WEIGHT: Final = 4.0
NEUTRAL_CHROMA_T: Final = 0.06

# Auto mode classification: pick Bayer (ordered) only for clearly flat graphics,
# else Floyd-Steinberg. A graphic has lots of exactly-equal neighbouring pixels
# AND a few colours covering most of the image; photos (even low-colour/foggy
# ones) stay well under both thresholds. Biased toward FS — picking Bayer for a
# photo is the worse mistake. Calibrated on a sample of photos vs a UI mock.
AUTO_FLAT_THRESHOLD: Final = 0.6
AUTO_DOMINANCE_THRESHOLD: Final = 0.7

# Service
SERVICE_UPLOAD_IMAGE: Final = "upload_image"

ATTR_CONFIG_ENTRY: Final = "config_entry_id"
ATTR_PATH: Final = "path"
ATTR_URL: Final = "url"
ATTR_IMAGE_ENTITY: Final = "image_entity_id"
ATTR_FIT: Final = "fit"
ATTR_ROTATE: Final = "rotate"
ATTR_DITHER: Final = "dither"
ATTR_MODE: Final = "mode"
ATTR_SATURATION: Final = "saturation"
ATTR_CONTRAST: Final = "contrast"
ATTR_SHARPEN: Final = "sharpen"

FIT_COVER: Final = "cover"
FIT_CONTAIN: Final = "contain"
FIT_STRETCH: Final = "stretch"
FIT_MODES: Final = (FIT_COVER, FIT_CONTAIN, FIT_STRETCH)
