# Making the firmware useful to Home Assistant

[Research index](README.md)

The practical direction is to let **ha-fraimic-eink own artwork, rendering,
playlists and voice-job history**, with a small adapter for the recovered frame
protocol. Retain the vendor display, power and microphone drivers initially.
This is a proposed design; no emulator, voice backend or customized firmware was
implemented as part of this research.

## What the integration already provides

This map was checked against repository commit
[`e5450665`](https://github.com/kristofferR/ha-fraimic-eink/commit/e5450665ddbb57c2542c883375ba68c0aefbb1b1)
(release 2.5.0). Use function names rather than assuming line numbers remain stable.

| Existing component | Reuse / boundary |
| --- | --- |
| [`library.py`](../../custom_components/fraimic/library.py), `async_add_image` | Store canonical originals in the shared image library |
| `library.py`, `async_render_for_entry` | Produce and cache the selected frame's rendered output |
| [`library_model.py`](../../custom_components/fraimic/library_model.py), `LibraryImage` | Existing source, attribution, album, crop and rotation metadata; no voice-job/transcript model yet |
| [`services.py`](../../custom_components/fraimic/services.py), `async_convert_for_entry` | Reuse frame-aware conversion, including orientation and Large packing |
| [`image_convert.py`](../../custom_components/fraimic/image_convert.py) | Tested panel palette, dithering and packing |
| [`playlists.py`](../../custom_components/fraimic/playlists.py), `async_add_slides` | Add creations to existing playlist machinery |
| [`scheduler.py`](../../custom_components/fraimic/scheduler.py), `begin_external_upload`, `finish_external_upload`, `async_notify_external_upload` | Coordinate external delivery with scheduled content; adapt semantics for cloud pull |
| [`power.py`](../../custom_components/fraimic/power.py), `async_record_upload` | Existing upload/power bookkeeping; do not count asset generation alone as a send |
| [`coordinator.py`](../../custom_components/fraimic/coordinator.py), `set_displayed_preview` | Preview state; do not equate a served download with confirmed display |
| [`api.py`](../../custom_components/fraimic/api.py) | Existing local push transport and firmware compatibility behavior |
| [`cloud.py`](../../custom_components/fraimic/cloud.py), `FraimicCloudClient` | Existing vendor-account authentication, upload, album and complete-settings support |
| [`cloud_delivery.py`](../../custom_components/fraimic/cloud_delivery.py), `async_deliver`, `async_plan_wake` | Existing vendor-cloud delivery state and a separate empty album for wake-only scheduling |
| [`awake_window.py`](../../custom_components/fraimic/awake_window.py), `AwakeWindow` | Planned awake/rest windows that currently steer vendor-cloud wake scheduling |
| [`delivery.py`](../../custom_components/fraimic/delivery.py), `async_use_cloud` | Hybrid selection under the upload lock; respects a pending cloud redraw window |

Cloud and Hybrid delivery already exist. The new work is replacing the vendor
side of the device protocol and adding voice jobs, not rebuilding these modes.
The existing wake-only album deliberately has no images, keeping wake planning
separate from artwork delivery. Preserve that distinction when implementing a
local equivalent with `next_image_utc`.

A cloud-pull adapter should render an asset **without first pushing it** through
the existing upload service. Otherwise one generation can cause two physical
redraws. Extract only the small shared operation needed if existing helpers
combine rendering with sending. Keep one conversion/cache implementation.

## Useful features before changing firmware

**Import existing voice artwork.** The vendor gallery schema exposes transcripts,
styles and originals. An explicit account-authenticated import could place these
in a `Creations` album, with stable upload identity for deduplication. Device-key
authentication was not shown to authorize this; only an unauthenticated 401 and
the public schema have been checked. No account session was imported.

**Create artwork from HA.** An integration-side STT/generation pipeline can store
new originals and deliver them through the existing LAN push transport while the
frame is awake. This is useful independently of redirecting the frame microphone,
but it does not provide stock-microphone capture or remote wake from deep sleep.

Both approaches can build the same library/job model later used by the emulator.

HA's [`ai_task.generate_image`](https://www.home-assistant.io/integrations/ai_task/)
is a candidate provider-independent generation interface. Check the installed HA
version and selected entity's image-generation capability before choosing it.
An edit/reference-image workflow also needs a provider that supports that input;
plain image-generation support does not establish editing support. Store the
returned original in the library, rather than retaining only a transient result URL.

## Minimal local-cloud adapter

For an already-paired frame, implement the device-facing subset first:

| Endpoint family | Responsibility |
| --- | --- |
| `upload/check/<device_key>` | Pending packed image, complete optional settings snapshot, persistent next deadline |
| `upload/audio/presign` | Create a device-scoped upload ticket and durable job record |
| Multipart audio upload | Accept bounded WAV, validate format, retain according to owner policy |
| `upload/audio/finalize` | Deduplicate work; transcribe, route/generate and render; synchronously return ready asset URL |
| Panel asset GET | Serve the correct immutable 2,304,000-byte Large asset |
| `upload/global/315/<key>` | Serve required account/get-started instruction images |
| Album proxy, later | Translate the supported vendor-shaped operations into HA-owned playlists where semantics match |

The full wire contract is in [cloud](cloud-protocol.md) and [voice](voice.md).
Do not return firmware offers by default. Omit `device_settings` until the
intended complete state is known. Preserve active future deadlines on every
successful poll. No enrollment impersonation is needed for the first paired-frame
experiment; independent enrollment remains separate work.

Keep frame authentication separate from owner/admin authentication. Map each
provisioned key to a specific frame; issue short-lived upload/download tickets,
bound body sizes and concurrent jobs, and redact keys from path logs. A frame
should not get an HA admin token or arbitrary library-file access. Existing HA
views must not simply become unauthenticated to accommodate the device.

An HA-hosted adapter or a small companion service can implement the same contract.
Choose based on deployment/TLS needs and the owner's preference; neither requires
an S3 service merely to satisfy the multipart upload. Local transport still needs
intentional TLS trust, and WAN-free operation needs the firmware's connectivity
and NTP dependencies addressed.

## Voice jobs and creations

A small durable job record should connect:

- Frame identity and device-scoped request/idempotency identity.
- Audio receipt, transcript, routed intent and generation provider/job identity.
- Original library image, parent image for edits, prompt/style and conversion inputs.
- Resulting panel content hash and proposed next schedule.
- Processing outcome separately from download and display evidence.

Only accept a finalize key belonging to that frame's recorded upload. Repeated
finalize requests should return the same result, not purchase another generation.
Persist the original before advertising the panel asset. Make raw-audio retention
an explicit option; transcript retention and deletion should be understandable too.

Potential user-facing behavior:

| Request | Result |
| --- | --- |
| “Make a misty mountain painting” | New original in Creations; rendered for this frame and reusable elsewhere |
| “Make this warmer” | New version linked to the previous library image; preserve the original |
| “Show today's weather and calendar” | Existing dashboard rendering, with no image-generation call |
| “Put this in the living-room playlist” | Change HA playlist membership using the same library identity |
| “Make a matching pair” | Two linked originals with separate target-frame conversions |

Stock finalize expects an image even for a command that needs no visual change.
Returning the current image can still cause a redraw. Clean no-redraw success
requires a firmware/protocol extension; do not promise it as a backend-only fix.
Actual user interaction and provider choices should be agreed before implementation.

## Delivery state and scheduling

Use explicit states such as generated, ready, download served and display
unconfirmed. A completed HTTP asset transfer is insufficient to claim the panel
changed. The strongest future signal is a frame `render_complete` event carrying
the same content ID. Keep current preview state honest until that exists.

The stock `display.last_refresh` value tracks maintenance history, and the render
worker's completion semaphore is also released on failure. Neither can substitute
for a per-content success result. Firmware events must include propagated driver
errors; see [rendering and concurrency](rendering-and-concurrency.md).

Use HA's existing scheduler as the source of truth for playlist progression and
let the adapter publish the next deadline. Avoid independent push and pull loops
competing over the same frame. Preserve voice holds and external-upload semantics,
but recognize the stock backend cannot detect the start of recording before
presign. Firmware busy events and shared-buffer ownership solve that missing edge.

The frame can wake itself for a scheduled pull. It cannot receive an immediate
unscheduled LAN command while deeply asleep. Prepare assets before its wake and
allow enough time for rendering before the next deadline is chosen.

## Highest-value firmware additions

1. Configurable API URL/trust and local time source, with recoverable configuration.
2. Backend-aware reachability instead of the public TCP gate.
3. Recording/busy/cancel and render-complete events with content/job identity.
4. Explicit ownership of the shared audio/image buffer across every entry point.
5. Local enforcement of the auto-update preference and reliable OTA outcome reporting.
6. Atomic image-cache replacement and distinct cache/display results.
7. Later: async voice jobs, sleep while generation runs, no-redraw command success,
   automatic end-of-speech, and offline playlists after storage capacity is known.

This prioritization avoids replacing working panel/microphone drivers before the
backend contract is understood. It is not a claim that custom app boot or recovery
has been established.

## Staged validation

1. Build fixtures from the sanitized response shapes; test defaults, missing fields,
   wrong ownership, duplicate finalize, truncation and failed/slow generation.
2. Run the adapter with an emulated HTTP client and a known packed asset. Confirm
   exact lengths, request sequence, long-request timeout and library metadata.
3. Verify gallery import with a deliberately authorized account session if desired.
4. Establish the [recovery prerequisites](ota-and-recovery.md) and review a minimal
   backend configuration change before any physical update experiment.
5. With owner-directed device tests, validate an idle poll, one image, one completed
   voice request, cancellation and a retry. Avoid paid generation during protocol tests.
6. Validate sleep deadlines, WAN outage, cold boot, setup assets and interrupted
   writes. Measure battery cost after the workflow is functionally correct.

The documentation does not imply completion of these experiments. Its purpose is
to make the next implementation and device test small, concrete and reviewable.
