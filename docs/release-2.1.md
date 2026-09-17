# Fraimic 2.1

## New

- **Hybrid delivery:** send locally when the frame is awake, or use Fraimic cloud delivery for its next scheduled wake when it is asleep. Configure Hybrid in the frame options with a Fraimic account. Existing delivery settings remain unchanged.
- **Tone and dithering preview (beta):** preview the processed image inside the crop while keeping the surrounding artwork and positioning controls visible. Includes native panel pixels, 1:1 pixel inspection and calibrated physical-size zoom.
- Preview modes prepare in the background, with the selected mode taking priority and visible rendering status beside the controls and on the crop.

## Fixed

- Player previews remain visible while sending and during cloud delivery, with stale cloud preview URLs rejected.
- Gallery artwork no longer appears more than once.
- Saved artwork rotations stay aligned with the crop, and sending to another frame respects that frame's saved crop and rotation.
- Preview caching uses bounded compressed storage. Online artwork with caching disabled prepares only the selected mode to avoid repeated speculative downloads.

## Preview beta limitation

The preview currently looks noticeably worse than the result on the physical frame. Treat it as an approximate guide when comparing tone and dithering. Improving visual fidelity is planned after this release; tracked in [issue #68](https://github.com/kristofferR/ha-fraimic-eink/issues/68).

## Updating

Update through HACS, restart Home Assistant, then reload the browser or companion-app page to load the updated panel. When upgrading from 1.x, also follow the [2.0 upgrade notes](https://github.com/kristofferR/ha-fraimic-eink/blob/v2.1.0/docs/release-2.0.md#upgrading-from-1x).

**Full changelog:** [v2.0.0…v2.1.0](https://github.com/kristofferR/ha-fraimic-eink/compare/v2.0.0...v2.1.0)
