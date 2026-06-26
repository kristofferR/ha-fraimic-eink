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
# Fraimic frames are E Ink Spectra 6 COLOUR panels (not grayscale). The default
# resolution is the 13.3" frame (1600x1200 landscape); the resolution is stored
# per config entry so smaller/larger frames can be configured.
DEFAULT_WIDTH: Final = 1600
DEFAULT_HEIGHT: Final = 1200
MAX_BIN_SIZE: Final = 1024 * 1024  # frame rejects uploads over 1 MB

# Spectra 6 palette. Nibble value -> (approx) display colour. Only 0-5 are valid.
SPECTRA6: Final = (
    (0, 0, 0),        # 0 Black
    (255, 255, 255),  # 1 White
    (0, 255, 0),      # 2 Green
    (0, 0, 255),      # 3 Blue
    (255, 0, 0),      # 4 Red
    (255, 255, 0),    # 5 Yellow
)
SPECTRA6_LEVELS: Final = len(SPECTRA6)

# Service
SERVICE_UPLOAD_IMAGE: Final = "upload_image"

ATTR_CONFIG_ENTRY: Final = "config_entry_id"
ATTR_PATH: Final = "path"
ATTR_URL: Final = "url"
ATTR_IMAGE_ENTITY: Final = "image_entity_id"
ATTR_FIT: Final = "fit"
ATTR_ROTATE: Final = "rotate"
ATTR_DITHER: Final = "dither"

FIT_COVER: Final = "cover"
FIT_CONTAIN: Final = "contain"
FIT_STRETCH: Final = "stretch"
FIT_MODES: Final = (FIT_COVER, FIT_CONTAIN, FIT_STRETCH)
