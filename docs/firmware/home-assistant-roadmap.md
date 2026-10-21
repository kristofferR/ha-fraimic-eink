# Making the firmware useful to Home Assistant

[Research index](README.md)

The [cancellation trace](voice.md#cancellation-and-scheduled-content-races) adds
two adapter constraints: a `processing` status does not defer delivery when a
URL is present, and socket closure is not an explicit cancel command. Hold
finalize until the model-specific asset is ready, deduplicate it by stable job
identity, and keep generation/delivery state separate so a disconnected frame
does not lose the original or create a second generation on retry.

The practical direction is to let **ha-fraimic-eink own artwork, rendering,
playlists and voice-job history**, with a small adapter for the recovered frame
protocol. Retain the vendor display, power and microphone drivers initially.
The HA integration is a proposed design. Bounded, standalone
[backend fixtures](backend-emulation.md) have served the physical frame's poll
and album reads, captured its microphone and delivered one owner-confirmed test
card. A combined recording-to-fixed-image test also completed through the stock
driver, cache save and return to ready. These are bounded protocol experiments,
not a deployed HA backend, generation service or firmware fork.

The [Standard comparison](standard-model-comparison.md) supports one protocol
adapter with separate model renderers. Its captured setup response is useful
enrollment evidence, but minimum independent provisioning is still untested.
The [enrollment follow-up](cloud-protocol.md#enrollment-boundary) identifies the
stock sign-in branch as a candidate local-account entry point: bind the submitted
device key, return a stable nonempty user ID and supply setup assets. Returning
`success` alone can produce apparently registered state with broken voice.
The separate create-account verification task and all unpaired boot behavior
still need validation before offering independent onboarding.

WAN-free operation also needs a time-service plan. The Large startup path can
[switch APs after failed SNTP](boot-and-scheduling.md#time-failure-also-triggers-ap-failover),
before its public-connectivity monitor starts. Supplying only the local API and
a substitute TCP reachability target is insufficient. Accurate local NTP via
the stock server names is a candidate to test; configurable time sources and
separate backend/time/WAN health are the longer-term firmware direction.

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

A host experiment now verifies this primitive: the real library and converter
retained the original, produced 2,304,000 panel bytes and a 720 × 1280 preview,
and reused the cached result. All three delivery-mode option values were tested
with delivery forbidden. This does not test a new pull scheduler or its locks;
none has been implemented. See [validation and limits](validation-2026-10-21.md).

## Useful features before changing firmware

**Import existing voice artwork.** The vendor gallery schema exposes transcripts,
styles and originals. An explicit account-authenticated import could place these
in a `Creations` album, with stable upload identity for deduplication. Owner-token
page/detail reads and an original download have now succeeded; device-key Bearer
authentication returned 401. Missing/null metadata must be supported. No library
import was performed. A later expiry check verified that an expired original URL
returned 403, while re-reading the stable gallery item produced a fresh URL to
byte-identical PNG content. Persist the original and upload identity so URL
rotation does not create another library item. The existing `async_add_image` creates another item for
identical input, so an importer needs a persisted account/upload-ID mapping.

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

### Installed HA capability boundary

On HA **2026.10.2**, the `ai_task.generate_image` service is registered, but the
configured Anthropic and Google AI Task entities both report feature mask **3**:
data generation plus attachments. Neither advertises image generation (**4**).
A registered service is therefore insufficient to run this workflow today.
No local STT/generation provider was found in the inspected configuration.

The configured Assist pipeline uses cloud STT, an Anthropic conversation agent
and cloud TTS in Norwegian. Executing that pipeline can invoke intents; a
transcription-only adapter should use the STT boundary deliberately rather than
running arbitrary recorded speech as an Assist command by default.

For an image-capable entity, HA's [image-task implementation](https://raw.githubusercontent.com/home-assistant/core/2026.10.2/homeassistant/components/ai_task/task.py)
accepts local media-source attachments (including camera/image snapshots), saves
the generated image, and returns a media-source ID, signed URL, MIME type and
dimensions. The signed URL lasts one hour according to the
[versioned constants](https://raw.githubusercontent.com/home-assistant/core/2026.10.2/homeassistant/components/ai_task/const.py).
Keep the durable source ID/original. Reference-image editing also requires an
appropriate provider/model; attachment support on a data-only entity is not
image-edit support. Provider setup and real generation/edit tests remain decisions
for implementation. The capability inventory itself closes A01.

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
For later album compatibility, the [frame proxy](local-api.md#body-transformation-is-not-schema-validation)
does not validate JSON objects, eliminate duplicate identity fields or forward
query parameters. The emulator needs its own schema/device authorization and
complete JSON responses; a forwarded HTTP status alone cannot confirm a mutation.
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
- Final generation prompt, model/style and conversion inputs, kept distinct from
  the raw transcript and interpreted intent.
- Original library image and parent image for edits.
- Resulting panel content hash and proposed next schedule.
- Processing outcome separately from download and display evidence.

Prompt visibility is an owner priority. The Standard vendor capture exposed no
transcript or final prompt in presign/finalize, so a local job history must capture
its own stages explicitly. Do not present a gallery transcript as the vendor's
final generation prompt without evidence that they are identical.

A later object-identity correlation linked the captured Standard audio job and
panel result to its authenticated gallery record. That exact creation exposes a
transcript and original, and refreshed URLs restore its byte-identical original
after expiry. This supports an importer for existing voice creations independently
of a local STT service. Preserve the gallery upload ID explicitly; it differs
from the audio/storage job UUID. The final vendor generation prompt is still unknown.

Only accept a finalize key belonging to that frame's recorded upload. Repeated
finalize requests should return the same result, not purchase another generation.
Persist the original before advertising the panel asset. Make raw-audio retention
an explicit option; transcript retention and deletion should be understandable too.

There is a separate crash boundary between submitting a paid generation and
saving its provider job ID. A local lock or a completed-job cache cannot guarantee
exactly one purchase across that boundary. Prefer provider idempotency keys/job
lookup; otherwise persist an ambiguous-submission state and require deliberate
recovery instead of automatically buying another generation. A duplicate finalize
should attach to the existing job. A disconnect alone must not delete its original
or imply the frame cancelled it. These are design requirements for A04, not tested
behavior of an existing job store.

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

### Extension boundaries

| Capability | Backend-only limit | Required firmware/protocol work |
| --- | --- | --- |
| Recording/busy/cancel events | Presign arrives after recording; polling does not identify its start | Emit state transitions with frame/job identity and acquire the buffer before capture |
| No-redraw command success | Returning the current image still follows download/render | Explicit terminal success without an image; preserve legacy completed-image response |
| Sleep during generation | Stock finalize waits for a ready URL; `202` does not create a pending job | Persist pending job identity, define resume/cancel/expiry, and arbitrate its next wake with album/maintenance deadlines |
| Streaming STT | Backend can stream a stored WAV to STT only after stock upload | Upload chunks during capture, with ordering, bounds, cancellation and buffer lifetime |
| Automatic end-of-speech | Server cannot stop stock capture before it receives the completed recording | Device VAD or a live capture-control channel, with silence/noise/maximum-duration policy |
| Reliable rendered event | Asset download and worker termination are insufficient | Carry content ID, propagate driver errors and distinguish display result from power-safe cleanup |

Advertise a protocol/capability version before using extensions. Keep stock
responses for stock clients; a settings field the stock firmware ignores is not
capability negotiation. These boundaries are grounded in the recovered flow;
backward-compatibility fixtures and physical transitions remain A06 work.

## Delivery state and scheduling

Use explicit states such as generated, ready, download served and display
unconfirmed. A completed HTTP asset transfer is insufficient to claim the panel
changed. The strongest future signal is a frame `render_complete` event carrying
the same content ID. Keep current preview state honest until that exists.

The stock `display.last_refresh` value tracks maintenance history, and the render
worker's completion semaphore is also released on failure. Neither can substitute
for a per-content success result. Firmware events must include propagated driver
errors; see [rendering and concurrency](rendering-and-concurrency.md).

Likewise, `/api/info`'s `settings.voice_recording` is an enable preference,
`wifi.connected` is station connectivity, and `display.next_refresh` is a
maintenance deadline. None reports an active voice job. The timestamps have no
offset. Preserve unknown/missing values and use the device's timezone context;
see [snapshot semantics](local-api.md#interpreting-the-json-status-snapshot).
The server handles local requests in one task, so serialize large transfers and
avoid overlapping diagnostic polls. A delayed status response alone does not
prove that the frame lost Wi-Fi.

The existing [`sensor.py`](../../custom_components/fraimic/sensor.py) parser
attaches HA's default timezone to a naive frame timestamp. That is correct only
when the frame and HA use matching timezone rules. The frame's observed
`EST5EDT` and a differently configured HA zone would produce different instants
from the same text. This source-level integration limitation is documented for
later implementation; no sensor code or device timezone was changed here.

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
3. Build an idempotent importer from the verified account read contract; test
   pagination changes, expired URLs, duplicate runs and retained originals.
4. Establish the [recovery prerequisites](ota-and-recovery.md) and review a minimal
   backend configuration change before any physical update experiment.
5. With owner-directed device tests, validate an idle poll, one image, one completed
   voice request, cancellation and a retry. Avoid paid generation during protocol tests.
6. Validate sleep deadlines, WAN outage, cold boot, setup assets and interrupted
   writes. Measure battery cost after the workflow is functionally correct.

The documentation does not imply completion of these experiments. Its purpose is
to make the next implementation and device test small, concrete and reviewable.
