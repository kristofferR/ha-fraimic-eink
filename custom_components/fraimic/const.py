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

# How often a camera "playing" on the frame re-snapshots (seconds). Every
# update is a full ~30 s E-Ink refresh cycle and costs battery, so this is
# deliberately slow. 0 = snapshot once, no auto-refresh.
CONF_CAMERA_INTERVAL: Final = "camera_refresh_interval"
DEFAULT_CAMERA_INTERVAL: Final = 1800
MIN_CAMERA_INTERVAL: Final = 60
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
# Source images are always scaled to the frame resolution, so this is just an
# out-of-memory guard, not a resolution limit — generous enough for any photo.
MAX_SOURCE_BYTES: Final = 64 * 1024 * 1024
# Reject absurd source dimensions (decompression bombs) before fully decoding.
MAX_SOURCE_PIXELS: Final = 100_000_000  # 100 MP — far above any real photo

# Spectra 6 palette. The RGB tuples are *calibrated approximations* of what each
# colour actually looks like on the panel (used for quantization matching and
# previews). Spectra 6 colours are far more muted than monitor primaries, so
# matching against pure primaries (255,0,0 etc.) renders badly. Calibrated
# values corroborated by Toon-nooT's converter and the Pimoroni Inky community
# (red #a02020, yellow #f0e050, green #608050, blue #5080b8).
#
# NOTE: tuple position here is the *internal* palette position used throughout
# the dither pipeline and previews — NOT the nibble sent to the frame. Real
# frames (verified on firmware 0.2.21 hardware) use the E Ink standard Spectra 6
# codes, which skip 0x4: 0x0 black, 0x1 white, 0x2 yellow, 0x3 red, 0x5 blue,
# 0x6 green. SPECTRA6_PANEL_INDEX maps position -> panel nibble at pack time.
SPECTRA6_RGB: Final = (
    (0, 0, 0),        # Black
    (255, 255, 255),  # White
    (240, 224, 80),   # Yellow #f0e050
    (160, 32, 32),    # Red    #a02020
    (80, 128, 184),   # Blue   #5080b8
    (96, 128, 80),    # Green  #608050
)
# Panel nibble for each SPECTRA6_RGB position (E Ink standard; 0x4 is unused —
# the panel renders it as white).
SPECTRA6_PANEL_INDEX: Final = (0x0, 0x1, 0x2, 0x3, 0x5, 0x6)
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
# Filmic tone-curve (S-curve) strength 0-100: lifts midtone contrast while rolling
# off shadows/highlights so detail survives the panel's limited dynamic range
# (rather than clipping). 0 disables.
DEFAULT_TONE: Final = 25.0
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

# Media library. Originals + manifest live under <config>/fraimic_library/;
# rendered .bin/.png pairs are cached per (resolution + conversion params) so a
# playlist/scene can re-send an image without paying the dither cost again.
LIBRARY_DIR: Final = "fraimic_library"
LIBRARY_ALBUM_DEFAULT: Final = "Images"
# Longest edge of the JPEG thumbnails served to the panel grid.
LIBRARY_THUMB_SIZE: Final = 480

# Named palette positions for dashboard screens (position in SPECTRA6_RGB).
# Screens render with these exact calibrated RGB values so every flat region
# quantises losslessly to its palette index (mode "none", no dithering noise).
PALETTE_NAMES: Final = {
    "black": 0,
    "white": 1,
    "yellow": 2,
    "red": 3,
    "blue": 4,
    "green": 5,
}

# Dashboard screens: rotation interval bounds (each upload is a full ~30 s
# E-Ink refresh and costs battery, so the floor is deliberately high).
MIN_SCREEN_INTERVAL: Final = 300
DEFAULT_SCREEN_INTERVAL: Final = 1800

# Online image providers ("art frame" mode).
# Keyless: five museums (CC0/public-domain masterpieces — dimu is
# Nasjonalmuseet via the DigitaltMuseum API), Wellcome Collection
# (illustration/archive), Wikimedia picture of the day, Bing image of the day
# (unofficial; personal use), NASA APOD and the NASA Image Library
# (DEMO_KEY/keyless tiers suffice for daily use), Lorem Picsum (random demo
# photos). Smithsonian works on DEMO_KEY; a free api.data.gov key raises its
# limit.
PROVIDER_KEYS: Final = (
    "met",
    "aic",
    "cleveland",
    "smk",
    "dimu",
    "smithsonian",  # optional free api.data.gov key (frame options)
    "wellcome",
    "wikimedia",
    "bing",
    "apod",
    "nasa",
    "picsum",
    "unsplash",  # requires a free API key (frame options)
    "pexels",  # requires a free API key (frame options)
)
PROVIDER_SHUFFLE: Final = "shuffle"  # random pick across available providers
MEDIA_SCHEME: Final = "fraimic-online"

# Aggressive e-ink curation: anything with a short edge below this upscales
# visibly soft on the ~150 PPI panel, and extreme aspect mismatches lose most
# of the artwork to the cover-crop.
MIN_ART_SHORT_EDGE: Final = 1000
ART_ASPECT_MIN: Final = 0.5  # x the frame's viewed aspect ratio
ART_ASPECT_MAX: Final = 2.0

# Optional provider API keys (entry options).
CONF_NASA_API_KEY: Final = "nasa_api_key"
CONF_SMITHSONIAN_KEY: Final = "smithsonian_api_key"
CONF_UNSPLASH_KEY: Final = "unsplash_access_key"
CONF_PEXELS_KEY: Final = "pexels_api_key"
CONF_DEFAULT_PROVIDER: Final = "default_provider"

# Services
SERVICE_UPLOAD_IMAGE: Final = "upload_image"
SERVICE_SEND_SCENE: Final = "send_scene"
ATTR_SCENE_NAME: Final = "name"
SERVICE_RENDER_SCREEN: Final = "render_screen"
SERVICE_SHOW_ONLINE_IMAGE: Final = "show_online_image"

ATTR_SCREEN: Final = "screen"
ATTR_SCREEN_ID: Final = "screen_id"
ATTR_PREVIEW_ONLY: Final = "preview_only"
ATTR_PROVIDER: Final = "provider"
ATTR_QUERY: Final = "query"
ATTR_CAPTION: Final = "caption"

ATTR_CONFIG_ENTRY: Final = "config_entry_id"
ATTR_PATH: Final = "path"
ATTR_URL: Final = "url"
ATTR_IMAGE_ENTITY: Final = "image_entity_id"
ATTR_LIBRARY_IMAGE: Final = "library_image_id"
ATTR_FIT: Final = "fit"
ATTR_ROTATE: Final = "rotate"
ATTR_DITHER: Final = "dither"
ATTR_MODE: Final = "mode"
ATTR_SATURATION: Final = "saturation"
ATTR_CONTRAST: Final = "contrast"
ATTR_SHARPEN: Final = "sharpen"
ATTR_TONE: Final = "tone"

FIT_COVER: Final = "cover"
FIT_CONTAIN: Final = "contain"  # keep aspect, white bars
FIT_CONTAIN_BLACK: Final = "contain_black"  # keep aspect, black bars
FIT_STRETCH: Final = "stretch"
FIT_MODES: Final = (FIT_COVER, FIT_CONTAIN, FIT_CONTAIN_BLACK, FIT_STRETCH)
