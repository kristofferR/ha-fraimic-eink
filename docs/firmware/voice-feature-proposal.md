# Voice features grounded in the existing HA integration

[Research index](README.md) · [HA reuse map](home-assistant-roadmap.md) · [Future protocol](protocol-extensions.md)

**Owner-selected scope: all three feature groups.** Include new voice artwork
with visible transcript, final generation prompt and creation history; image
editing; and HA commands with playlist control. The owner selected this scope
on 22 October. This is a research proposal; it does not authorize implementation,
provider calls or deployment. Build on one job/history model across all three
groups, with explicit image and action targets as described below.

## First creation flow

1. Bind the microphone request to the enrolled frame's HA config-entry ID. Create
   one stable job ID for its recording, transcript, generation request and result.
2. Transcribe through an explicit STT interface, then store the transcript and
   exact final prompt separately. Record model/style and generation parameters;
   the transcript alone is not necessarily the prompt sent to an image model.
3. Add the resulting original to the existing library under a Creations album,
   keyed by job ID so retries do not add another item. Render for the requesting
   frame's configured model and mount using the existing conversion boundary.
4. Return the frozen panel artifact through stock synchronous finalize. Keep
   creation success, download served and display unconfirmed as separate states.
   The original remains available even if the frame disconnects.
5. In HA, let the owner inspect the transcript/prompt, edit the prompt and create
   a new result, or add the original to a playlist/scene. Regeneration creates a
   new linked version rather than overwriting the original or its provenance.

Existing library/render-only evidence supports those primitives. Durable jobs,
metadata, provider orchestration and a pull-delivery adapter remain implementation
work. The inspected HA 2026.10.2 installation has configured STT, but its inspected
AI Task entities do not advertise image generation. A service name alone cannot
supply that capability; an image-capable provider and any reference-edit support
must be selected and validated before implementation calls them. No provider was
configured or invoked by this research.

## Define what each command means

| User intent | Concrete target / operation | Important boundary |
| --- | --- | --- |
| Make new artwork | Enrolled requesting frame, new original and job | Default target comes from the frame identity, not a guessed spoken room name |
| Edit an image | Explicit library image ID selected in HA, then a new child original | “This” cannot safely mean the frame's physical pixels when delivery is unconfirmed |
| Add to a playlist | Saved playlist ID plus existing library image ID | Changes the saved catalog; does not insert into an already-running playback snapshot |
| Play next | Config-entry ID and current queue insertion | Separate operation from saved playlist membership |
| Show a dashboard | Existing screen configuration, rendered for the selected frame | Can produce a meaningful image without an image-generation provider; it still needs the relevant HA data |
| Show a matching scene | Existing scene ID with explicit frame→image mappings | Per-frame preparation and delivery outcomes; no simultaneous or atomic wall update |

For an edit requested through the microphone, retain the job as needing an
explicit reference selection in HA if “this” is ambiguous. Do not silently edit
the last library item or a thumbnail merely because it is available. Stock
firmware cannot present a rich disambiguation exchange or clean no-redraw command
success; terminate its bounded request without generation if the necessary
reference is unavailable. A later negotiated protocol can improve that interaction.

Store explicit target IDs once resolved. Playlist names are not unique in the
current manager, while scene creation enforces case-insensitive unique names and
its lookup rejects ambiguous legacy duplicates. A natural-language layer must
resolve ambiguity before a mutation; choosing the first matching name is not
an existing integration guarantee. Restrict commands to the defined frame/library
actions instead of passing unbounded speech into generic HA service execution.

## Six checks against real integration APIs

The isolated pass used unchanged release
[`e5450665`](https://github.com/kristofferR/ha-fraimic-eink/commit/e5450665ddbb57c2542c883375ba68c0aefbb1b1)
playlist, playback-queue and scene code with the repository's HA/storage test
substitutes. All **six scenarios passed**. Library conversion, frame uploads and
live HA were stubbed in this pass; the earlier real converter checks are separate.

- Appending a creation changes the saved playlist and survives the stubbed store
  reload. An already-copied `PlaybackQueue` stays unchanged until a separate
  insertion; “play next” inserts before the existing upcoming item.
- Two playlists can share a name. Appending the same image twice creates two
  different slide IDs. Command replay therefore needs an operation/job ledger;
  the manager does not supply semantic deduplication.
- A syntactically valid library-image reference is accepted without consulting
  the library. Resolve/validate the original before appending; schema acceptance
  does not prove the image exists.
- Scene activation renders each mapped frame before the upload phase. The
  actual method reports `ok: true` when the upload boundary returns false for
  accepted-but-queued delivery; its scheduling hold is released with
  `uploaded=False`. That result is not a physical display acknowledgment.
- One frame's render failure does not prevent another prepared frame from
  uploading. Results are per frame, and all acquired scheduling holds are released.
- Scene creation rejects a duplicate name and an absent library source;
  case-insensitive scene lookup works for an unambiguous name.

For a local pull backend, reuse scene mappings and the library's render-only
primitive. Do not call `SceneManager.async_send` merely to prepare assets: it
enters the existing push/queue delivery path. The same distinction applies to
the higher-level render-and-upload helper.

## Choices still open before implementation

The owner selected all three feature groups. Provider selection and editing
capability remain open; no paid-generation test has run. The proposal defines
target/current-image semantics conservatively and identifies the reusable APIs.
A07's host milestone is complete; its decision milestone remains open for
provider capability and the proposed interaction details. Stock firmware still
cannot provide clean no-redraw success for a nonvisual command.

See [validation and source hashes](validation-2026-10-22.md#voice-feature-reuse-a07).
