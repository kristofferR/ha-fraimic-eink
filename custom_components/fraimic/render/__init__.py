"""Native dashboard-screen rendering for the Fraimic E-Ink Canvas.

Renders Home Assistant entity data as TRMNL-style "screens": widgets composed
into layout slots, built as SVG and rasterised with resvg, then pushed through
the existing Spectra 6 conversion pipeline.

Package layout:
- Pure, HA-import-free (headless-testable): ``schema``, ``layout``, ``theme``,
  ``svg``, ``icons``, ``context``, ``compose``, ``widgets/``.
- Home Assistant side: ``fetch`` (entity/service data gathering) and
  ``display`` (render + upload orchestration).

This ``__init__`` must stay free of Home Assistant imports so the pure modules
can be imported standalone by the test suite.
"""
