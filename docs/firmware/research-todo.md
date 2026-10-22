# Firmware research checklist

[Research index](README.md) · [Detailed pass history](research-progress-2026-10-22.md)

Reconciled against the published evidence on 22 October 2026 for Large 0.2.29 /
f1555ee5 and Standard 0.2.28 / 4654a1d8. The 67 original IDs and questions are
retained. Checkboxes below distinguish completed milestones from remaining work;
the top-level box closes only the stated question.

## Current status

**11 of 67 original items complete; 119 of 187 concrete milestones complete.**
These are task counts, not a percentage estimate of firmware understood.

| Status | Items | Meaning |
| --- | --- | --- |
| Complete | 11 | Original bounded question answered; evidence linked below |
| Research | 5 | Concrete static, host or design work remains available |
| Waiting for device | 24 | Remaining original criteria require physical validation |
| Needs implementation | 5 | Validation depends on an adapter, importer or protocol extension |
| Waiting for recovery | 11 | Access, partition, backup or recovery prerequisite is missing |
| Deferred | 9 | Owner-postponed work; do not resume automatically |
| Ongoing | 2 | Evidence discipline applied to relevant findings/builds, not a finite feature |

Completed original items: **C01, C05, C09, C10, A01, A05, R11, D01, N02, H07, E03**. The reconciliation closed
C05, C10, R11 and E03 from evidence already gathered; it adds no new device tests.
The latest 31 finalize cases are recorded under C07, whose end-to-end physical
timeout criterion remains unchecked.
A05 subsequently closed with the deployment comparison and 24 isolated boundary
checks; production bridge/job implementation remains A02–A04.
C01 subsequently closed with all identified constructor destinations classified
and explicit remaining indirect-search limits; offline operation is not claimed.
N02 subsequently closed with the pinned-build key inventory, Wi-Fi/PHY and
Standard display-health records, migration cases and explicit reference-search
limits. Installed NVS and physical recovery remain separate criteria.
D01 subsequently closed with the buffer-reference census, transport callback
teardown and task-local registration audit. Physical corruption and cleanup
outcomes remain separate deferred tests.

## How to use this list

Each completed milestone links to evidence and retains its method: **Static**,
**Host**, **Device**, **Account**, **Read** or **Design**. A host reconstruction
does not close a physical criterion. **Next** marks available research;
**Implementation**, **Blocked** and **Deferred** explain why an unchecked step
cannot be cleared by another static pass. Some research items also have a
separate deferred physical step.

Close a bounded question when its stated evidence is sufficient. Put newly
discovered work in an explicit remaining step or its owning item; do not quietly
expand the acceptance criteria. In particular:

- C05's local upload contract is established. Physical cancellation and actual
  disconnect/retry behavior remain C08; extra SDK cleanup audit belongs to E01.
- C10 establishes sampled gallery fields/permissions/IDs and one expiry cycle.
  Concurrent-pagination import and retained originals belong to A02. Indefinite
  vendor retention and the final vendor AI prompt remain unknown, not conditions
  for repeating the completed read experiment.
- R11 closes the recovered entry-point/bookkeeping trace, with its documented
  indirect-reference limits. Installed policy, update faults and restoration
  remain R02/R05/R09/R10/R12.
- E03 reconciles the two saved schemas with the capture. Independent enrollment,
  unobserved mutations and broader permissions remain C11/C12; no schema promises
  authorization by itself.

The owner chose backend emulation with the enclosure closed. Physical recording/
cancellation tests, flashing/recovery experiments and battery work remain
deferred; R12's unfinished host work and N04's filesystem pass were also explicitly postponed. Do not
repeatedly request a recording or board access. No device/network change or HA
implementation is authorized merely by an unchecked box.

## Available next work

Continue with H03's audio-output initialization/call-path audit, then the remaining
H05 handler/diagnostic contracts. A07's [feature proposal](voice-feature-proposal.md)
awaits provider/interaction choices; the owner selected all three feature groups.
Its six API reuse checks, C12's local album mutation contract, D02's byte-level
overlap, D04's bounded renderer fault model, N05's recoverable cache-slot pass,
N06's wake-asset cases, D06's driver-fault/watchdog pass and S02's bounded
time-control/overlapping-waiter cases and N03's bounded identity/save/reset comparison
are complete. A06's compatibility
examples, C08/D05's bounded interleaving
pass and C11's synthetic enrollment pass are complete; their physical criteria
remain deferred. A02–A04 and A03's final integration check need implementation;
report that dependency rather than substituting more library decompilation.
Preserve the remaining lower-priority static work under its original ID.
Commit and push validated research batches periodically as requested.

## Local cloud and voice

- [x] **C01 · Static/Host:** Audit every consumer of the API, web and auth selectors,
  redirects and server-supplied URLs. Establish the full hostname/dependency set
  an already-paired local backend must replace.

  Status: **Complete**.

  - [x] **Static:** Inventory eleven client-constructor sites, thirteen selector calls, literal hosts, returned URLs and non-HTTP dependencies on both builds. [Inventory](cloud-protocol.md#outbound-client-and-url-inventory).
  - [x] **Static/Host:** Trace redirects, request encoding, local-name resolution and first-address behavior, with bounded SDK fixtures. [URL behavior](cloud-protocol.md#redirect-url-handling-differs-from-a-browser), [DNS](boot-and-scheduling.md#outbound-local-names-and-blocking-resolution).
  - [x] **Static/Read:** Reconcile every identified constructor to a URL source in both builds; explicitly bound dynamic response/NVS values, legacy literals and computed-call search limits. No unclassified direct constructor remains; WAN-free operation is separate. [Coverage ledger](cloud-protocol.md#destination-coverage-and-remaining-indirect-call-limits).

- [ ] **C02 · Host/Device:** Validate poll parser behavior for settings snapshots,
  missing/invalid fields, schedule clearing and persistence failures. Trace which
  `user_settings` members are actually applied locally rather than merely copied.

  Status: **Waiting for device**.

  - [x] **Host:** Exercise poll field precedence, settings snapshots and missing/invalid deadlines in 25 cases. [Parser](cloud-protocol.md#field-selection-and-permissive-json-parsing).
  - [x] **Static:** Trace copied-but-unapplied user settings, result lifetime and failed-save/no-retry behavior on both builds. [Consumers](cloud-protocol.md#user_settings-is-copied-with-no-recovered-local-application), [persistence](storage-and-configuration.md#failed-settings-saves-are-not-retried-by-an-identical-snapshot).
  - [x] **Device:** Receive five local idle polls while preserving the observed switches and future deadline. [Experiment](backend-emulation.md#idle-experiment-c02c03c12).
  - [ ] **Deferred:** **Device:** Inject selected malformed/partial snapshots and NVS failures, then verify state after reboot. Coordinate with S03 rather than repeating its schedule tests.

- [ ] **C03 · Host/Device:** Verify owner-hosted HTTPS JSON and panel assets, including
  explicit lengths, redirects, response limits and download errors. Test hostname
  and trust behavior with controlled positive/negative certificates; do not infer
  arbitrary self-signed acceptance from the earlier test-chain result.

  Status: **Waiting for device**.

  - [x] **Device:** Serve local HTTPS JSON/panel data; retain Large hostname/untrusted-chain negative controls and Standard positive interception evidence. [TLS boundary](cloud-protocol.md#http-and-tls-requirements), [panel result](backend-emulation.md#one-shot-panel-delivery-c03c09d06).
  - [x] **Host:** Exercise redirect, length, framing, short-body and timeout branches. [Nineteen image-reader cases](image-downloads.md#host-results-with-the-matching-sdk-reader).
  - [x] **Static/Host:** Establish TLS 1.2, cipher/name configuration, allocation policy and selected ClientHello boundaries. [TLS findings](cloud-protocol.md#tls-setup-needs-internal-ram-before-authentication).
  - [ ] **Deferred:** **Device:** Validate the remaining redirect/response-fault cases and Standard negative TLS controls. Further SDK internals are E01 follow-ups, not a requirement to re-prove successful local delivery.

- [ ] **C04 · Host/Device:** Supply local `create_account` and `get_started` assets;
  verify IP-query handling, format, fetch failures and actual setup-screen behavior.
  Establish what an offline fallback would need.

  Status: **Waiting for device**.

  - [x] **Static/Host:** Compare setup metadata/fetch paths and test request/response/URL boundaries in nineteen cases. [Evidence](cloud-protocol.md#setup-metadata-comparison-and-host-boundaries).
  - [x] **Device:** Observe vendor create-account/get-started asset requests during Standard enrollment. [Capture](standard-model-comparison.md#poll-and-voice-observations).
  - [ ] **Deferred:** **Device:** Supply those two assets from the local backend and verify actual setup-screen/failure behavior. Independent enrollment remains C11.

- [x] **C05 · Host/Device:** Test multipart voice upload against a plain local HTTP
  service, including empty `{}` fields, required fields, upload tickets, status
  codes, size limits and malformed presign responses. Confirm no S3 service is needed.

  Status: **Complete**.

  - [x] **Device:** Receive real WAV uploads through plain local HTTP with empty fields; confirm that an S3 service is unnecessary and a positive-length acknowledgment fails. [Physical capture](backend-emulation.md#physical-microphone-results).
  - [x] **Host:** Check ticket validation, upload ordering, invalid/oversized WAV, identical/conflicting retries and capture-only finalize in the eleven-case fixture. [Fixture](backend-emulation.md#voice-capture-fixture-c05c06c07).
  - [x] **Host/Static:** Cover malformed presign fields/copy limits, multipart framing/write failures and acknowledgment status/framing with 25, eight and 24 groups respectively. [Presign](voice.md#presign-copying-and-field-reserialization), [writer](voice.md#host-checked-write-failures-and-framing-length), [acknowledgment](voice.md#upload-acknowledgment-parser-and-early-success-boundaries).

- [ ] **C06 · Device:** Verify actual WAV format, duration/size limits, initial tap
  suppression, completion taps, cancellation and deadline behavior with a short
  owner-directed recording. Check the near-60-second boundary separately.

  Status: **Waiting for device**.

  - [x] **Device:** Confirm PCM WAV framing, actual short-recording durations and tap-to-finish uploads. [Captured format](voice.md#stock-sequence).
  - [x] **Static/Host:** Map duration capacity, capture loss, stop/completion signaling and model differences. [Nine reader cases](voice.md#capture-reads-can-lose-audio-without-invalidating-wav-structure).
  - [ ] **Deferred:** **Device:** Check initial-tap suppression, near-60-second behavior, deadline/stop timing and cancellation. The owner postponed recordings/cancellation; do not repeatedly request one.

- [ ] **C07 · Host/Device:** Exercise finalize with slow responses, timeout, non-200
  statuses, missing URL, status variants, chunked/missing length, truncated/oversized
  JSON and network retry. Establish end-to-end timeout behavior through the proxy.

  Status: **Waiting for device**.

  - [x] **Host:** Cover partial/truncated/oversized JSON and per-read delays in twelve reader cases; cover missing URL/status/defaults in eight parser groups. [Reader](voice.md#body-completeness-and-timeout-scope), [fields](voice.md#finalize-response-fields-and-host-parser-checks).
  - [x] **Host:** Add 31 combined status/framing cases, including chunked/missing length, interim responses, slow errors and length narrowing. [Latest results](voice.md#finalize-http-status-framing-and-failure-ordering).
  - [x] **Static:** Establish no finalize retry/status-polling loop, three same-URL image attempts and the unjoined outer-worker timeout. [Retry stage](image-downloads.md), [worker lifetime](voice.md#late-upload-workers-retain-caller-stack-pointers).
  - [ ] **Deferred:** **Device:** Measure end-to-end slow response/timeout behavior through the actual proxy, including the outer task and disconnect. Host virtual delays do not close this requirement.

- [ ] **C08 · Host/Device:** Trace cancellation through recording, upload, finalize,
  download and rendering. Determine what the backend observes on disconnect and
  what work continues; verify retry/idempotency and stale-result behavior.

  Status: **Waiting for device**.

  - [x] **Static/Host:** Map cancellation at each stage, all 21 direct active-client operations, SDK close/reconnect state and selected Standard equivalents. [Cancellation](voice.md#which-stages-can-abort-their-socket), [slot ownership](voice.md#active-client-ownership-and-failed-unregistration).
  - [x] **Static:** Trace borrowed upload/download contexts, timeout returns, forced deletion and stale-result candidates. [Download lifetime](image-downloads.md#voice-download-timeout-and-forced-task-deletion).
  - [x] **Host:** Enumerate 70 client-slot orders and explicit late-result/stale-cancel traces using bounded transition models; retain overlap, stack-reuse and scheduler/socket assumptions. [Model and counterexamples](voice.md#bounded-two-job-ownership-and-completion-model).
  - [ ] **Deferred:** **Device:** Run the postponed cancellation experiment and correlate backend disconnect, continuing work and final state. This is the owner-deferred recording test.

- [x] **C09 · Host/Device:** Complete one local end-to-end voice round trip using
  fixture audio and a known panel image first, then one physical tap-to-image flow.
  Separate transport validation from paid generation and provider variability.

  Status: **Complete**.

  - [x] **Host:** Complete fifteen local voice-to-fixed-image checks. [Fixture](backend-emulation.md#combined-voiceimage-host-fixture-c09).
  - [x] **Device:** Complete the recording, upload, finalize, panel download, cache and driver sequence. The first card was visually confirmed; the repeated identical card was confirmed by logs. [Result](backend-emulation.md#combined-voiceimage-device-result-c09).

- [x] **C10 · Account:** Read a gallery page/item with an owner session; establish
  token versus device-key permissions, actual `upload_type`/metadata/transcript/style
  values, pagination, stable IDs and original availability after URL expiry.

  Status: **Complete**.

  - [x] **Account:** Read owner-authenticated gallery pages/detail and distinguish owner-token access from rejected device-key Bearer access. [Read evidence](validation-2026-10-21.md#authenticated-gallery-and-album-reads-c10c12e03).
  - [x] **Account:** Record pagination/metadata/type/style/transcript fields and matching list/detail identity; correlate the captured voice item. [Schema](cloud-protocol.md#albums-and-gallery), [voice correlation](standard-model-comparison.md#prompt-visibility-and-ha-reuse).
  - [x] **Account:** Let an original URL expire, refresh the same item and verify byte-identical PNG content. [Expiry cycle](validation-2026-10-21.md#authenticated-gallery-and-album-reads-c10c12e03).

- [ ] **C11 · Static/Host/Device:** Map complete enrollment, verification, web redirects,
  auth dependencies and identity persistence. Determine how independent local
  enrollment could work without unintentionally forwarding account passwords.

  Status: **Waiting for device**.

  - [x] **Static/Host:** Map account/verification split, browser scripts, local forms, response acceptance and persistence hazards. [Enrollment](cloud-protocol.md#enrollment-boundary), [thirty response groups](cloud-protocol.md#host-checked-enrollment-response-boundaries).
  - [x] **Device:** Capture successful vendor enrollment and identity surviving reboot on Standard. [Comparison/capture](standard-model-comparison.md).
  - [x] **Host/Static:** Run 28 local-only enrollment checks with a minimal response, pinned cJSON parser, downstream poll/voice identity and synthetic restart state; document the real sign-in save gate separately from the temporary-file model. [Fixture and limits](cloud-protocol.md#synthetic-local-enrollment-and-identity-continuation).
  - [ ] **Deferred:** **Device:** Validate independent local provisioning and reboot behavior without forwarding account passwords. Reset/re-enrollment needs a separate owner-directed experiment.

- [ ] **C12 · Static/Host/Account/Device:** Verify album proxy headers and authorization,
  create/delete/update payloads and device assignment support. Establish which
  vendor album semantics can map to HA playlists; registration alone is insufficient.

  Status: **Waiting for device**.

  - [x] **Static/Host:** Map proxy headers/body/ID/query/error translation and nineteen JSON cases. [Album contract](local-api.md#album-proxy-contract).
  - [x] **Account/Device:** Read owner/device-key album lists and return a matching local album snapshot. [Account evidence](cloud-protocol.md#albums-and-gallery), [local experiment](backend-emulation.md#idle-experiment-c02c03c12).
  - [x] **Design/Host:** Specify the interval/picture/wake-only subset and check nineteen mutation/API properties using actual HA payload builders/client and a loopback fixture. Production identity/atomicity, scheduling and real permissions remain separate. [Mapping and limits](album-playlist-mapping.md).
  - [ ] **Deferred:** **Account/Device:** Exercise create/update/delete and assignments with an approved disposable album; verify persistence and authorization.

## Home Assistant reuse and proposed capabilities

- [x] **A01 · Read/Host:** Inspect the installed HA version and configured STT,
  Assist and AI Task entities. Verify `ai_task.generate_image` availability,
  input/output formats, editing/reference-image support and local-inference options.

  Status: **Complete**.

  - [x] **Read:** Inventory installed STT/Assist/AI Task capabilities and document the absent image-capable/local provider. [HA inventory](validation-2026-10-21.md#ha-capability-inspection-a01).
  - [x] **Read/Host:** Verify WAV-to-PCM boundary and image-task input/output/reference-image requirements. [WAV fixture](validation-2026-10-21.md#wav-to-stt-fixture-a01c06), [provider boundary](home-assistant-roadmap.md#installed-ha-capability-boundary).

- [ ] **A02 · Host/Account:** Validate idempotent gallery import into the library,
  including original retention, transcript/style metadata, pagination, duplicate
  imports and URL expiry. Reuse C10's authenticated evidence.

  Status: **Needs implementation**.

  - [x] **Account/Host:** Establish the gallery import inputs and demonstrate that duplicate library insertion creates separate IDs. [Gallery](cloud-protocol.md#albums-and-gallery), [library checks](validation-2026-10-21.md#real-libraryconverter-experiment-a02a03).
  - [ ] **Implementation:** Persist an account/upload-ID import map; test duplicate imports, changing pagination, metadata and expired-URL refresh without duplicate originals.
  - [ ] **Implementation:** Define retention/deletion policy and test retained originals across reload. Indefinite vendor retention is unknown and is not an open-ended prerequisite for importing.

- [ ] **A03 · Static/Host:** Verify render-without-send reuse, model/orientation/cache
  keys, and integration with existing Cloud/Hybrid, wake-only albums and upload
  locks. Demonstrate that pull delivery does not also cause a local push/redraw.

  Status: **Needs implementation**.

  - [x] **Host:** Verify real render-without-send reuse, both model formats, mount/config/cache keys and damaged-cache acceptance. [Render evidence](home-assistant-roadmap.md#render-only-reuse-and-cache-validation).
  - [x] **Static:** Map overlay/delivery side effects, wake-only albums and integration locks. [Helper boundaries](home-assistant-roadmap.md#delivery-helpers-have-additional-side-effects).
  - [ ] **Implementation:** Integrate one pull adapter with scheduling/Cloud/Hybrid locks and prove it does not also push or redraw. Repeating render-only tests cannot close this integration requirement.

- [ ] **A04 · Design/Host:** Validate durable voice-job identity, ownership, retries,
  reload recovery, audio retention/deletion, original storage and edit lineage.
  Prove duplicate finalize requests do not create duplicate work or library items.

  Status: **Needs implementation**.

  - [x] **Host:** Demonstrate bounded ticket identity and identical/conflicting upload/finalize handling in the local fixture. [Voice fixture](backend-emulation.md#voice-capture-fixture-c05c06c07).
  - [ ] **Implementation:** Validate durable job ownership, generation deduplication and library identity across HA/service reload, retries and concurrent requests.
  - [ ] **Implementation:** Specify and test audio deletion, original retention and edit lineage; include transcript/prompt/model under the same job ID.

- [x] **A05 · Design/Host:** Compare HA-hosted protocol views with a companion service
  using actual TLS/deployment constraints. Check device-scoped authentication,
  upload/download tickets, bounds and log redaction while preserving admin auth.

  Status: **Complete**.

  - [x] **Host/Device:** Demonstrate standalone local HTTPS/API/upload/assets with frame-scoped tickets and bounded bodies; preserve separate admin credentials. [Backend evidence](backend-emulation.md).
  - [x] **Design/Read:** Compare HA views and a companion against active HTTP configuration, certificate maintenance, request lifetimes and deployment ownership; recommend a companion with a narrow HA bridge. [Comparison](backend-deployment.md).
  - [x] **Host:** Run 24 isolated checks using the pinned HA wrapper/TLS builder plus synthetic credential, size/job-limit and logging boundaries. Production integration and restart recovery are not claimed. [Evidence](backend-deployment.md#isolated-host-evidence).

- [ ] **A06 · Design/Host/Device:** Evaluate recording/busy/cancel/render-result events,
  async jobs that sleep while processing, no-redraw command success, streaming STT
  and automatic end-of-speech. Identify required firmware/protocol changes and
  backward compatibility for each; a feature decision does not require building it.

  Status: **Waiting for device**.

  - [x] **Static/Design:** Identify stock limitations and required firmware/protocol changes for events, sleeping jobs, no-redraw success, streaming STT and end-of-speech. [Capability map](home-assistant-roadmap.md#extension-boundaries).
  - [x] **Design/Host:** Define a separate negotiated protocol and legacy behavior for all six extensions; check eight examples against the stock parser and eighteen proposed-policy/message properties. [Proposal and limits](protocol-extensions.md), [messages](extension-examples.json).
  - [ ] **Deferred:** **Device:** Validate selected transitions only after an extension is implemented and a recovery path exists.

- [ ] **A07 · Design/Host:** Check that proposed voice creations, image edits,
  dashboard commands, playlist controls and multi-frame scenes can reuse existing
  library/scheduler behavior. Resolve provider capability, ambiguous-current-image
  and UI/interaction choices before implementation.

  Status: **Research**.

  - [x] **Static/Design:** Map candidate library/scheduler reuse and provider limitations for voice creations, edits and commands. [Roadmap](home-assistant-roadmap.md).
  - [ ] **Next:** **Design:** Select/validate provider capabilities and settle interaction details before implementation. The owner selected new artwork/history, edits and HA/playlist commands; current-image and target semantics are defined in the [concrete proposal](voice-feature-proposal.md).
  - [x] **Host:** Check six playlist/queue/scene scenarios against unchanged integration APIs, including replay, missing sources, partial success and queued delivery. [Results and limits](validation-2026-10-22.md#voice-feature-reuse-a07).

## Recovery and OTA prerequisites

- [ ] **R01 · Static/Device:** Recover the complete partition table: bootloader,
  partition metadata, both application slots, OTA data, NVS, image filesystem,
  calibration and other data partitions. Reconcile the observed app1 offset.

  Status: **Waiting for recovery**.

  - [x] **Device:** Record running app1 at 0x4a0000 with 0x480000 capacity and distinguish the 16 MB image header from a partition table. [Identity](hardware-and-layout.md#exact-image).
  - [ ] **Blocked:** **Recovery/Device:** Obtain a read route for the actual complete partition table, then map both apps, metadata, NVS, calibration and image filesystem. The enclosure stays closed.

- [ ] **R02 · Static/Device:** Establish the actual bootloader configuration and
  boot-selection/validation behavior; distinguish app SDK defaults from this unit.

  Status: **Waiting for recovery**.

  - [x] **Static:** Trace app-side pending validation, confirmation, alternate-image selection and metadata writes. [App boundary](ota-and-recovery.md#app-side-confirmation-is-real-but-is-not-a-recovery-guarantee).
  - [ ] **Blocked:** **Recovery/Device:** Read the installed bootloader/configuration and establish actual boot-selection policy; application SDK branches are insufficient.

- [ ] **R03 · Device:** Read and interpret actual secure-boot/eFuse state and image
  authorization requirements. Do not change eFuses to determine their state.

  Status: **Waiting for recovery**.

  - [x] **Static:** Record absence of a standard appended Secure Boot v2 signature sector in the downloaded app without inferring eFuse state. [Image limit](ota-and-recovery.md#two-update-paths).
  - [ ] **Blocked:** **Recovery/Device:** Read secure-boot and related authorization eFuses through an established read-only access path. Never burn an eFuse to test this.

- [ ] **R04 · Device:** Establish flash-encryption state separately from encrypted
  NVS, and determine what form of backup/restore is possible without exposing keys.

  Status: **Waiting for recovery**.

  - [x] **Device/Static:** Separate observed encrypted NVS from unknown whole-flash encryption and the compiled runtime encryption branch. [Identity](hardware-and-layout.md#exact-image), [OTA branch](ota-and-recovery.md#rejection-can-still-change-the-inactive-slot).
  - [ ] **Blocked:** **Recovery/Device:** Read actual flash-encryption state and establish which backup/restore form is possible without exporting keys.

- [ ] **R05 · Static/Device:** Determine anti-rollback/security-version policy,
  accepted downgrade conditions and implications for returning to stock.

  Status: **Waiting for recovery**.

  - [x] **Static:** Establish anti-rollback-disabled application branches without claiming bootloader/eFuse policy. [Evidence](ota-and-recovery.md#ota-metadata-and-anti-rollback-evidence-remain-separate).
  - [ ] **Blocked:** **Recovery/Device:** Determine installed security-version/downgrade policy and stock-return conditions after R02/R03. No downgrade test is authorized by this checkbox.

- [ ] **R06 · Static/Device:** Establish a complete backup/restore strategy including
  provisioning, calibration and original images. Verify backup coverage/integrity
  and restoration prerequisites; the downloaded app alone is insufficient.

  Status: **Waiting for recovery**.

  - [x] **Static:** Preserve/hash both matching vendor applications and identify their coverage limits. [Images](standard-model-comparison.md).
  - [ ] **Blocked:** **Recovery/Device:** Acquire and verify complete provisioning/calibration/artwork/partition coverage, then establish a restoration procedure. Application downloads alone do not fulfill backup coverage.

- [ ] **R07 · Hardware/Device:** Identify and verify a recovery entry despite the
  absent USB serial interface: actual test points, boot straps/interfaces or a
  supported recovery route, rather than generic ESP32-S3 assumptions.

  Status: **Deferred**.

  - [ ] **Deferred:** **Hardware/Device:** Establish an actual supported recovery/debug entry. Owner reports no USB serial interface and wants the enclosure closed; board inspection remains deferred. [Boundary](ota-and-recovery.md#minimal-customization-and-outstanding-prerequisites).

- [ ] **R08 · Static/Host/Device:** Prepare and review the smallest backend-URL/trust
  candidate, regenerate integrity fields, then determine custom-image boot
  acceptance only after a recovery path is established.

  Status: **Waiting for recovery**.

  - [x] **Static:** Locate central API selection, candidate URL replacement and separate trust/offline dependencies. [Selector](cloud-protocol.md#backend-selection).
  - [ ] **Blocked:** **Host:** Prepare/review the minimal URL/trust artifact and regenerate integrity fields after recovery/backup prerequisites are settled. No patch has been prepared.
  - [ ] **Deferred:** **Device:** Establish actual custom-image boot acceptance only with verified recovery and an explicitly approved flash experiment.

- [ ] **R09 · Host/Device:** Verify pending-validation checks, confirmation timing,
  actual rollback and stock restoration. Include an unreachable configured backend
  and failed changed functionality, not only PSRAM/I2C health.

  Status: **Waiting for recovery**.

  - [x] **Static:** Trace health confirmation before Wi-Fi, alternate-image checks and discarded rollback error. [Rollback](ota-and-recovery.md#rollback-requires-a-usable-alternate-image).
  - [ ] **Blocked:** **Recovery/Host:** Establish usable alternate contents and restoration prerequisites; design unreachable-backend/failed-feature checks.
  - [ ] **Deferred:** **Device:** Exercise confirmation, failed validation, actual rollback and stock restoration after recovery is verified.

- [ ] **R10 · Host/Device:** Validate update offers against the disabled auto-update
  preference, repeated/same-version offers, truncation, the three-failure cooldown,
  missing clock, result-report loss and compiled-version/artifact identity mismatch.

  Status: **Waiting for device**.

  - [x] **Static/Host:** Cover disabled-setting bypass, same/long versions, cooldown/clock, replacement/retention and failed persistence in 22 host groups. [Queue](ota-and-recovery.md#cooldown-clock-and-version-boundaries).
  - [x] **Static/Host:** Trace report consumption and compiled-version/artifact mismatch; poll construction cases cover report loss before transmission. [Reporting](ota-and-recovery.md#result-reporting).
  - [ ] **Deferred:** **Device:** Validate offer/report persistence and timing without assuming an offer is harmless. Installation/rollback experiments require recovery and separate approval.

- [x] **R11 · Static/Host:** Trace forced-version bookkeeping and every active OTA
  entry point, including factory controls; establish which newer paths still use
  the older manifest/hash, force-version and statistics mechanisms.

  Status: **Complete**.

  - [x] **Static:** Map poll queue, main/pre-sleep direct updater and legacy action/manifest path; identify factory POST as image upload. [Entry points](ota-and-recovery.md#legacy-manifest-and-retained-bookkeeping).
  - [x] **Static:** Distinguish legacy hash/force/statistics references from current version/URL queuing and counter resets. [Bookkeeping](ota-and-recovery.md#legacy-manifest-and-retained-bookkeeping).
  - [x] **Static/Host:** Trace one-poll version override, restoration/report consumption and related failure boundaries. [Mode switch](storage-and-configuration.md#update-solicitation-and-cached-artwork), [reporting](ota-and-recovery.md#result-reporting).

- [ ] **R12 · Static/Host/Device:** Verify direct-download validation, completeness,
  invalid-image handling, partition-capacity checks and the safety predicate under busy,
  Wi-Fi, time and uptime conditions. Reproduce fault cases in a harness before
  attempting controlled device updates; battery scale is tracked in B02.

  Status: **Deferred**.

  - [x] **Static:** Trace direct download framing, wrong-table MIME check, safety gates and image validation. [Updater](ota-and-recovery.md#direct-download-framing-and-failure-boundaries).
  - [x] **Static/Host:** Compare six SDK lifecycle bodies and pass 22 begin/write/end/abort groups, including erase-before-rejection and conditional encrypted-sector gap. [Fixtures](ota-and-recovery.md#ota-handle-and-write-fault-fixtures).
  - [ ] **Deferred:** **Host:** Outer HTTP/length and busy/safety fault fixtures were explicitly postponed by the owner on 22 October. Preserve unfinished private artifacts; do not resume this item automatically.
  - [ ] **Deferred:** **Device:** Actual partition/encryption state and controlled update/recovery remain unverified; resume only after prerequisites and owner direction.

## Offline boot, sleep and scheduling

- [ ] **S01 · Static/Host/Device:** Trace the connectivity manager beyond its cached
  getter. Test backend-up/WAN-down, backend-down/Wi-Fi-up and recovery/failover;
  determine how to replace the public TCP gate without breaking AP recovery.

  Status: **Waiting for device**.

  - [x] **Static/Host:** Map probe/refusal branches, cached state, AP failover/recovery counters and both-build equivalents. [Connectivity](boot-and-scheduling.md#public-reachability-gate).
  - [x] **Device:** Observe the Standard public-probe block disrupting a transfer and temporary exception restoring connectivity; remove that exception afterward. [Capture](standard-model-comparison.md).
  - [ ] **Deferred:** **Device:** Test backend-up/WAN-down, backend-down/Wi-Fi-up and recovery sequences with a local replacement gate. Do not turn the previous temporary exception into a permanent rule.

- [ ] **S02 · Static/Device:** Verify local time-source configuration, DNS/service
  dependencies, unsynchronized cold boot and RTC-preserving sleep. Establish
  offline TLS/time/scheduling behavior, including drift and clock corrections.

  Status: **Waiting for device**.

  - [x] **Static/Host:** Map DNS/NTP dependencies, DHCP option 42 omission, ignored HTTP Date, server/wait ordering and stale callbacks. [Offline dependencies](boot-and-scheduling.md#offline-dependencies).
  - [x] **Host/Static:** Exercise resolver/reply/NTP boundaries and compare selected Standard paths. [DNS replies](boot-and-scheduling.md#dns-replies-for-a-local-backend), [NTP](boot-and-scheduling.md#ntp-response-contract-and-clock-application).
  - [x] **Host:** Exercise time-service queue/allocation failures and overlapping control callbacks in 25 bounded reconstruction cases, with explicit ownership, semaphore-consumption and completion assertions. [Lifecycle cases and limits](boot-and-scheduling.md#time-control-and-overlapping-waiters-host-cases).
  - [ ] **Deferred:** **Device:** Validate accurate local NTP, cold boot/RTC sleep, cache-expired DNS, drift/corrections and fully offline TLS/scheduling.

- [ ] **S03 · Host/Device:** Exercise future, absent, invalid, past and failed-poll
  deadlines across reboot. Check persistence and the distinction between clearing
  the schedule and a network failure.

  Status: **Waiting for device**.

  - [x] **Static/Host:** Cover missing/invalid/past/future deadline rules, failed-poll preservation and the failed-clear reload sentinel. [Persistence](boot-and-scheduling.md#album-deadline-persistence), [sentinel](storage-and-configuration.md#a-failed-schedule-clear-can-reload-the-old-deadline).
  - [ ] **Deferred:** **Device:** Verify those cases across reboot and injected save/clear failures with C02.

- [ ] **S04 · Host/Device:** Validate the strict 30-second margin, equal deadline
  handling, maintenance/album collisions, long transfer/redraw, overdue five-minute
  retry, missing-album fallback and invalid-time fallback.

  Status: **Waiting for device**.

  - [x] **Host/Static:** Exercise strict 30-second margin, ties, fallback/retry and timer/reason ordering in 33 groups. [Wake selection](boot-and-scheduling.md#timer-selection-arming-and-wake-reason-are-separate-operations).
  - [ ] **Deferred:** **Device:** Measure actual wake/deadline behavior during long transfers/redraw, collisions and invalid time. Virtual timer calls do not prove physical timing.

- [ ] **S05 · Static/Host/Device:** Validate maintenance calendar calculations,
  default first target, timezone/DST changes and stored schedule limits. Determine
  whether any usable public setter exists for the internal schedule parameters.

  Status: **Waiting for device**.

  - [x] **Static/Host:** Establish POSIX/default-US timezone parsing and stale-DST target shifts with nine parser/eight calendar cases. [Calendar](boot-and-scheduling.md#timezone-format-and-default-rules).
  - [x] **Static:** Audit eight fixed maintenance setter calls per build; no configurable public setter was recovered in the bounded search. [Setter audit](boot-and-scheduling.md#maintenance-parameters-have-only-fixed-default-callers).
  - [ ] **Deferred:** **Device:** Validate stored-schedule recalculation and actual maintenance timing across timezone/DST/clock changes.

- [ ] **S06 · Device:** Map actual wake sources and transitions for normal, button,
  charger, maintenance, album, first-setup/storage and factory-test modes. Verify
  HTTP reachability and timeout behavior in each, without treating test-mode sleep
  as evidence of normal idle sleep.

  Status: **Waiting for device**.

  - [x] **Static:** Map lifecycle, network/display shutdown ordering and final wake-source reset. [Shutdown](boot-and-scheduling.md#pre-sleep-ordering-and-outstanding-work).
  - [x] **Device:** Preserve USB-powered reachability and separate earlier factory-test sleep evidence. [Observed scope](validation-2026-10-21.md#later-awake-read-s05s06h05h07).
  - [ ] **Deferred:** **Device:** Measure normal/button/charger/maintenance/album/setup/factory transitions and HTTP windows without treating factory sleep as normal idle behavior.

- [ ] **S07 · Host/Device:** Validate a local pull playlist with wake-only scheduling,
  backend outages, changed plans and HA restart; quantify wake latency and battery
  cost. Check offline cached playlists only after N01/N07 establish feasibility.

  Status: **Needs implementation**.

  - [ ] **Implementation:** Build the local pull/wake-only playlist fixture, then test changed plans, backend outages and HA restart.
  - [ ] **Deferred:** **Device:** Measure wake latency and energy cost for that implementation. Offline cached capacity depends on N01/N07; battery measurements remain deferred under B03.

## Rendering and concurrency

- [x] **D01 · Static/Host:** Finish the ownership/lifetime map for recording, audio
  transmission, raw/multipart HTTP, cloud downloads, system images, cache I/O and
  rendering, including indirect references and task/mutex boundaries.

  Status: **Complete**.

  Scope: identified paths in the two pinned builds, with computed-reference and
  runtime limits explicit. Physical overlap/cleanup outcomes remain D02/D04/D05.

  - [x] **Static:** Map shared audio/image/render buffers, response backing stores, system-image producers, cache paths and render arbitration. [Ownership](rendering-and-concurrency.md), [response memory](cloud-protocol.md#shared-response-ownership-and-verification-guard).
  - [x] **Static:** Recover borrowed worker contexts, timeout/cleanup boundaries and Standard separate audio allocation. [Upload lifetime](voice.md#late-upload-workers-retain-caller-stack-pointers), [model comparison](standard-model-comparison.md#separate-recording-and-image-allocations).
  - [x] **Static:** Reconcile sixteen buffer-reference functions per build, seventeen paired transport bodies and thirteen task-local bodies; resolve constant callback registrations and distinguish callback arguments from calls. Keep demonstrated aliases separate from hypothesized runtime corruption. [Coverage](rendering-and-concurrency.md#ownership-coverage-across-the-two-pinned-builds), [transport](voice.md#transport-close-frees-tls-state-before-client-cleanup), [task-local cleanup](image-downloads.md#task-local-destructors-do-not-replace-http-cleanup).

- [ ] **D02 · Host/Device:** Reproduce the shared-buffer interference with controlled
  overlapping operations. Record which bytes/operation are affected and when;
  static missing guards alone do not demonstrate a particular runtime failure.

  Status: **Waiting for device**.

  - [x] **Static:** Identify overlapping producer writes before render arbitration and the Large audio/image alias. [Candidate interference](rendering-and-concurrency.md#readiness-is-not-ownership).
  - [x] **Host:** Execute eleven synthetic memory-copy scenarios at recovered sizes/offsets, with exact changed ranges, DMA-stage behavior, WAV structure checks and separate Standard allocation controls. [Byte-level evidence and limits](rendering-and-concurrency.md#byte-level-overlap-fixture-and-model-controls).
  - [ ] **Deferred:** **Device:** Validate an approved overlap scenario physically; static missing guards alone are not an observed failure.

- [ ] **D03 · Static/Host:** Verify SPI/DMA consumption and completion semantics to
  establish when the source bytes can be released. Evaluate exclusive ownership
  versus a real snapshot against measured free memory and fragmentation.

  Status: **Research**.

  - [x] **Static:** Establish blocking source consumption and per-chunk DMA staging/release. [DMA](rendering-and-concurrency.md#dma-staging-protects-only-the-current-chunk).
  - [x] **Read:** Compare observed free PSRAM with the size of a full Large snapshot. [Memory boundary](hardware-and-layout.md#one-psram-buffer-serves-audio-and-images).
  - [ ] **Next:** **Host/Design:** Evaluate exclusive ownership versus snapshot allocation under measured fragmentation/pressure; do not infer a second full buffer from nominal PSRAM capacity.

- [ ] **D04 · Host/Device:** Exercise WAIT/DROP, simultaneous producers, stuck worker,
  task-allocation failure and early render failure. Check busy flags, semaphore
  behavior, recording-state query failures and timeout cleanup.

  Status: **Waiting for device**.

  - [x] **Static:** Map WAIT/DROP, pre-arbitration writes, setup-task waits and maintenance DROP-as-success. [Render policy](rendering-and-concurrency.md#what-wait-and-drop-actually-guarantee), [maintenance](rendering-and-concurrency.md#maintenance-refresh-has-separate-completion-rules).
  - [x] **Host:** Exercise twenty Large renderer/query scenarios and 140 admission orders, including context/task failures, early cleanup, stuck waits and stale/collapsed completion. SDK/hardware and scheduling remain modeled. [Results and limits](rendering-and-concurrency.md#bounded-renderer-fault-and-admission-model).
  - [ ] **Deferred:** **Device:** Validate selected timeout/cleanup outcomes after a bounded fixture exists.

- [ ] **D05 · Host/Device:** Validate voice versus scheduled-content races and every
  cancellation stage, including recording before presign. Check how far HA locks
  and backend holds help and which cases require firmware ownership/events.

  Status: **Waiting for device**.

  - [x] **Static:** Establish that a pending scheduled response can interrupt recording and that HA locks do not cover frame-originated capture. [Race](voice.md#scheduled-content-can-interrupt-recording), [HA boundaries](home-assistant-roadmap.md#delivery-helpers-have-additional-side-effects).
  - [x] **Design/Host:** Enumerate 15 recording/poll orders under three policies; distinguish presign holds, proposed recording events and device-side deferral. Reuse the C08 ownership model; no physical race is claimed. [Recording boundary](voice.md#scheduled-content-can-interrupt-recording).
  - [ ] **Deferred:** **Device:** Validate selected cancellation stages and scheduled-content races when physical testing resumes.

- [ ] **D06 · Static/Host/Device:** Trace and inject controller/SPI, BUSY, PMIC and I2C
  failures. Establish watchdog behavior for the power-good wait, recovery and safe
  shutdown; distinguish logged failures from propagated results.

  Status: **Waiting for device**.

  - [x] **Static:** Trace controller/DMA/BUSY/PMIC errors, unbounded power-good wait, task-watchdog unsubscription and suppressed shutdown results. [Watchdog](rendering-and-concurrency.md#the-task-watchdog-does-not-bound-the-long-panel-sequence), [shutdown](boot-and-scheduling.md#display-shutdown-suppresses-its-own-failure-evidence).
  - [x] **Static/Host:** Exercise 26 Large driver-fault/feed-policy cases through the reconstructed worker; recover MWDT1 startup, dual-core feeding and 300/600 ms interrupt/reset stage settings. These do not bound yielding panel waits or verify physical recovery. [Fault cases](rendering-and-concurrency.md#driver-faults-through-the-worker-bounded-host-cases), [interrupt watchdog](rendering-and-concurrency.md#interrupt-watchdog-tick-health-is-not-render-progress).
  - [ ] **Deferred:** **Device:** Establish actual fault recovery and safe shutdown. A successful ordinary render does not close these tests.

- [ ] **D07 · Host/Device:** Correlate accepted/cached/worker-ended/driver-completed/
  power-safe states with the physical panel. Verify a content-ID result design
  reports errors accurately and does not mistake semaphore release for success.

  Status: **Needs implementation**.

  - [x] **Static/Device:** Separate accepted, cached, worker-ended, driver-complete and power-safe evidence in observed delivery logs. [Ordering](rendering-and-concurrency.md#observed-poll-and-voice-cache-ordering).
  - [ ] **Implementation:** Validate a content-ID result model with propagated errors and distinct display/power-safe states; semaphore release must not imply success.
  - [ ] **Deferred:** **Device:** Correlate that result model with actual panel output and selected error cases after firmware support and recovery exist.

- [ ] **D08 · Device:** Confirm maintenance-only `last_refresh` behavior across local
  upload, voice, system images, maintenance, errors and reboot. Verify history-ring
  persistence and absence of per-image identity in the exposed field.

  Status: **Waiting for device**.

  - [x] **Static:** Trace maintenance-only timestamp/history writes, including ignored refresh result and missing per-image identity. [History](rendering-and-concurrency.md#displaylast_refresh-is-maintenance-history).
  - [x] **Device:** Observe null last_refresh after successful Standard voice rendering. [Capture](standard-model-comparison.md#poll-and-voice-observations).
  - [ ] **Deferred:** **Device:** Cover local uploads, system images, maintenance, failures and reboot/history persistence.

## Storage, identity and system artwork

- [ ] **N01 · Static/Device:** Establish actual `imagedata` partition size, free space,
  allocation overhead, wear-leveling behavior and practical endurance/write budget.

  Status: **Waiting for recovery**.

  - [x] **Static:** Distinguish image FAT storage from NVS and recover selected mount/allocation behavior. [Storage](storage-and-configuration.md#nvs-is-not-the-image-filesystem).
  - [ ] **Blocked:** **Recovery/Device:** Obtain actual imagedata geometry/free space, then measure overhead and derive a wear/write budget. Do not infer capacity from app or buffer size.

- [x] **N02 · Static/Host:** Complete the NVS schema, including value types, defaults,
  namespaces and references omitted from the current table. Map compatibility and
  migration across versions without publishing identity/password values.

  Status: **Complete**.

  Scope: the two pinned builds and identified consumers. Installed storage,
  physical recovery and unexamined releases are outside this static/host criterion.

  - [x] **Static:** Map application key types, blob layouts, defaults and SDK Wi-Fi/PHY namespaces. [Schema](storage-and-configuration.md#recovered-nvs-types-and-record-sizes).
  - [x] **Static:** Compare selected settings/identity paths and establish non-atomic per-key writes. [Persistence](storage-and-configuration.md#nvs-commit-does-not-make-the-four-switches-atomic).
  - [x] **Static:** Compare seventeen selected SDK bodies and resolve both actual handle tables, extending per-key storage/commit semantics to Standard. This does not compare all page/flash helpers or establish downgrade safety. [SDK comparison](standard-model-comparison.md#nvs-handle-dispatch-and-storage-writes-also-match).
  - [x] **Host/Static:** Check legacy-field migration with 28 scenarios per build using recovered caller instructions and synthetic SDK results: missing versus erroneous destinations, unchecked copies/rereads, partial progress and misleading completion logs. [Migration boundaries](storage-and-configuration.md#legacy-field-migration-does-not-validate-a-whole-identity).
  - [x] **Static:** Recover all 73 Wi-Fi descriptors, their storage types/capacities and twelve indirect NVS callback slots on both builds; compare five registry/load/open/cleanup bodies. [SDK schema](storage-and-configuration.md#wi-fi-registers-73-configuration-keys-outside-app_data), [machine-readable records](wifi-nvs-schema.json).
  - [x] **Static:** Compare eleven Wi-Fi post-load/default/set/commit helpers, distinguish RAM cleanup from optional writeback, and confirm the AP SSID length-word layout. [Normalization](storage-and-configuration.md#wi-fi-normalization-changes-ram-before-optional-writeback).
  - [x] **Static:** Reconcile 23 namespace/key API roots: 316/330 decoded direct calls, twelve exact function-pointer words per build, four paired PHY wrappers and Standard's separate display-health records. No identified consumer remains unclassified; computed references and physical compatibility retain explicit limits. [Coverage](storage-and-configuration.md#nvs-consumer-coverage-and-compatibility-boundary), [Standard counters](storage-and-configuration.md#standard-also-stores-per-build-display-health-counters).

- [ ] **N03 · Host/Device:** Verify production/development identity and Wi-Fi isolation,
  legacy-key migration, reset semantics, timezone sharing and interrupted/failed
  saves. Determine exactly what is preserved and what requires reenrollment.

  Status: **Waiting for device**.

  - [x] **Static:** Map environment namespaces, deterministic key selection, legacy migration, whole-NVS reset backups and subsequent cached-state writes. [Identity](storage-and-configuration.md#identity-layout-and-migration), [reset](storage-and-configuration.md#cached-identity-and-later-writes-after-reset).
  - [x] **Host:** Exercise interrupted saves/reset restoration with synthetic identity: nineteen groups, 34 successful-mutation cut points and 28 setter errors. These are API-boundary models, not physical power-loss tests. [Persistence cases](storage-and-configuration.md#identity-saves-and-reset-restoration-host-cases).
  - [x] **Static:** Compare 21 selected Standard SDK/caller bodies around identity saving, reset and cached-state handoff; separately trace both main-loop regions and their different waits. Deeper storage internals remain N02, and whole-workflow physical equivalence is not claimed. [Comparison](standard-model-comparison.md#identity-persistence-and-reset-handoff-comparison).
  - [ ] **Deferred:** **Device:** Verify final production/development/Wi-Fi/timezone state and reenrollment after approved reset/mode-switch cases.

- [ ] **N04 · Host/Device:** Validate mount retries and format-on-failure decisions
  with missing legacy key, NVS read error and filesystem corruption in a disposable
  fixture. Establish which state/artwork survives recovery on the actual layout.

  Status: **Deferred**.

  - [x] **Host:** Check application mount retries/format eligibility and retained wear-leveling slots in 24 plus twelve groups. [Format](storage-and-configuration.md#formatting-permission-is-not-proof-that-formatting-happened), [cleanup](storage-and-configuration.md#failed-mounts-can-retain-wear-leveling-handles).
  - [x] **Static:** Trace accepted already-registered error with unset filesystem output and allocation-region preference. [Registration](storage-and-configuration.md#existing-vfs-registration-does-not-supply-a-filesystem-pointer).
  - [ ] **Deferred:** **Host:** Complete actual disposable filesystem corruption and registration/cleanup failures beyond stub return codes. Owner postponed this pass; partial host artifacts remain private and are not a checked validation milestone.
  - [ ] **Blocked:** **Recovery/Device:** Establish artwork survival on the actual layout after N01/recovery; no live formatting is part of this research pass.

- [ ] **N05 · Host/Device:** Verify partial writes, flush/fsync errors, truncated
  last-image loads and save-failure-with-render behavior. Assess an atomic cache
  replacement/hash design against actual FAT support and available space.

  Status: **Waiting for recovery**.

  - [x] **Static/Host:** Map partial cache reads/writes, ignored flush/close, destination-exists rename and late sync behavior in RAM FAT. [Cache](storage-and-configuration.md#cache-success-and-failure-leave-different-state-behind), [sync cases](storage-and-configuration.md#a-second-sync-can-conceal-an-earlier-metadata-sync-failure).
  - [x] **Design/Host:** Assess atomic replacement limits and test a recoverable two-slot/hash proposal against pinned FatFs: 812 whole-write cut points plus sixteen integrity/space/recovery checks. Installed capacity and physical atomicity remain unknown. [Design and limits](storage-and-configuration.md#recoverable-cache-replacement-proposal-and-interrupted-write-checks).
  - [ ] **Blocked:** **Recovery/Device:** Verify actual wear-leveling, power-loss and reboot durability once the layout and recovery route are known.

- [ ] **N06 · Static/Host/Device:** Verify custom wake-up artwork feasibility and
  persistence across version changes, missing/truncated/same-size corrupt files,
  resets and cache recovery. Establish the true validation/palette contract.

  Status: **Waiting for device**.

  - [x] **Static:** Map embedded wake-image installation, validation allocation, version checks and unchecked version commit. [Wake artwork](storage-and-configuration.md#wake-up-screen-embedded-raw-image-installed-to-fat).
  - [x] **Host:** Exercise twenty-two Large wake-file/version scenarios over disposable files, including invalid palette, repair faults and missing-version/file-loss states. Reset/FAT/NVS effects are modeled, not physical tests. [Results and limits](storage-and-configuration.md#wake-asset-validation-and-recovery-host-cases).
  - [ ] **Deferred:** **Device:** Verify custom wake artwork and upgrade/reset persistence after recovery prerequisites are established.

- [ ] **N07 · Design/Host:** Determine feasible offline playlist capacity, eviction,
  canonical restoration and content deduplication using measured storage. Account
  for system artwork, temporary files and wear before promising multiple images.

  Status: **Waiting for recovery**.

  - [ ] **Blocked:** **Design/Host:** After N01 provides actual storage, calculate offline playlist capacity and test eviction, canonical restoration, deduplication, temporary-space and wear constraints.

- [ ] **N08 · Host/Device:** Test generated low-battery/status RLE artwork, invalid
  palette values and malformed runs; verify actual rendering and preservation of
  last artwork/sys_img state.

  Status: **Waiting for device**.

  - [x] **Host/Static:** Exercise malformed RLE/size/palette/partial writes with sixteen Large and eighteen Standard cases; trace marker changes before completion. [Large](storage-and-configuration.md#status-decoder-validation-and-partial-writes), [Standard](storage-and-configuration.md#standard-status-assets-use-different-row-geometry).
  - [ ] **Deferred:** **Device:** Verify generated status artwork, actual palette/rendering and last-artwork/sys_img recovery across overlap, failure and reboot.

## Hardware and remaining local interfaces

- [ ] **H01 · Hardware:** Identify the microphone's physical part number and verify
  the recovered PDM wiring/configuration against the actual board.

  Status: **Deferred**.

  - [x] **Static:** Recover PDM RX configuration and clock/data pins. [Wiring](hardware-and-layout.md#display-and-wiring).
  - [ ] **Deferred:** **Hardware:** Read the microphone part marking and compare actual wiring. Enclosure inspection is explicitly deferred.

- [ ] **H02 · Static/Hardware:** Identify which accelerometer is fitted, separate
  probe candidates from detected hardware, and verify orientation behavior.

  Status: **Deferred**.

  - [x] **Static:** Establish software address/ID, candidate probes, ineffective alternate success, two-way orientation and error fallback on both builds. [Sensor trace](hardware-and-layout.md#accelerometer-target-and-orientation-semantics).
  - [ ] **Deferred:** **Hardware/Device:** Identify the fitted part and test mounting/orientation/failure behavior. The software label does not identify the physical component.

- [ ] **H03 · Static/Hardware:** Determine whether speech/audio output hardware
  exists and is usable; microphone input does not establish speaker capability.

  Status: **Research**.

  - [ ] **Next:** **Static:** Audit possible audio-output initialization/call paths independently of the known PDM input.
  - [ ] **Deferred:** **Hardware:** Establish whether usable output hardware exists. Do not infer a speaker from microphone support; keep the enclosure closed.

- [ ] **H04 · Static/Host/Hardware:** Determine supported partial-refresh/custom
  waveform modes and their panel/power constraints; do not transfer capabilities
  from another display model without evidence.

  Status: **Research**.

  - [x] **Static:** Establish MIN/MID full-panel conditioning and model-specific clear-buffer behavior. [Conditioning](rendering-and-concurrency.md#conditioning-adds-full-panel-clear-cycles).
  - [ ] **Next:** **Static:** Audit remaining controller command paths and available panel-specific evidence for partial refresh/custom waveforms.
  - [ ] **Deferred:** **Hardware/Device:** Verify supported modes and power/panel constraints before trying any custom waveform.

- [ ] **H05 · Static/Device:** Map request/response schemas, authentication, boot-state
  availability and side effects for all 42 registrations. Cover action/log/dev/test
  controls and undiscovered setters; validate read-only branches first and track
  mutating/destructive branches as explicit separate experiments. Albums are C12.

  Status: **Research**.

  - [x] **Static:** Inventory all 42 registrations; recover dev authentication, factory/action side effects, server capacity and diagnostic behavior. [Local API](local-api.md), [logs](diagnostics-and-logs.md).
  - [x] **Static/Host:** Check selected setup/Wi-Fi forms/scripts, mDNS lifecycle and LED arbitration. [Forms](local-api.md#wi-fi-field-matching-and-byte-limits), [LEDs](led-and-workflow-state.md).
  - [ ] **Next:** **Static/Host:** Reconcile the remaining per-handler schemas/setters and explicit diagnostic allocation/redaction/flush cases against the registration inventory.
  - [ ] **Deferred:** **Device:** Validate remaining boot-state availability, concurrent reads, LED/discovery timing and separately approved mutating controls. Keep destructive actions separate.

- [ ] **H06 · Static/Hardware:** Establish current/voltage calibration, fitted battery
  arrangement and hardware measurement accuracy separately from software labels.

  Status: **Deferred**.

  - [x] **Static/Read:** Identify gauge/software scale conventions and observed readings, without equating labels to physical calibration. [Voltage mismatch](ota-and-recovery.md#apparent-battery-scale-mismatch).
  - [ ] **Deferred:** **Hardware/Device:** Establish actual battery arrangement and calibrated current/voltage accuracy. Hardware access and battery investigation remain deferred.

- [x] **H07 · Static:** Resolve descriptor build timezone if supporting provenance
  exists; otherwise retain the explicit null/unknown rather than inventing one.

  Status: **Complete**.

  - [x] **Static:** Distinguish the separate −0400 boot-log timestamp from unknown descriptor provenance; retain descriptor timezone null. [Identity evidence](hardware-and-layout.md#exact-image).

## Deferred battery investigation

- [ ] **B01 · Static/Device:** Determine the root cause of false cable-connected
  state, including the −50 mA branch, actual plugged/unplugged readings, current
  sign/calibration and resulting sleep decisions. Preserve the owner's deferral
  of the battery fix while investigating backend functionality.

  Status: **Deferred**.

  - [x] **Static/Device:** Preserve the unplugged false-connected observation and relevant current/charging branches. [Observation](evidence-and-open-questions.md#battery-observation).
  - [ ] **Deferred:** **Device:** Compare plugged/unplugged calibrated readings and trace the actual root cause/sleep effect. The owner deferred battery repair.

- [ ] **B02 · Host/Device:** Validate the apparent OTA one-cell/two-cell voltage-scale
  mismatch and effective charge protection using controlled inputs/bench conditions,
  without using low-charge flashing as the first validation method.

  Status: **Deferred**.

  - [x] **Static:** Identify the one-cell percentage calculation versus doubled pack-voltage input. [Scale](ota-and-recovery.md#apparent-battery-scale-mismatch).
  - [ ] **Deferred:** **Host/Device:** Validate effective protection under controlled inputs/bench conditions; never use low-charge flashing as the first test.

- [ ] **B03 · Device:** Measure long-term sleep/idle, voice, Wi-Fi recovery, display
  maintenance and local-pull energy use, including cable/LED/keep-awake effects.
  Compare behavior before and after any eventual firmware changes.

  Status: **Deferred**.

  - [ ] **Deferred:** **Device:** Measure ordinary sleep/idle, voice, Wi-Fi recovery, display maintenance and pull energy with cable/LED/keep-awake controlled. Existing diagnostic reads are not a battery baseline.

## Evidence quality and compatibility

- [ ] **E01 · Static:** Revisit incomplete Ghidra control flow, inferred types,
  function boundaries and indirect references for claims used by implementation.
  Validate consequential instructions with the matching Xtensa configuration.

  Status: **Ongoing**.

  - [x] **Static:** Correct consequential Ghidra truncations, missing task entries and generic-Xtensa decoding with pinned bytes/GNU control flow. [Method](evidence-and-open-questions.md#method-and-private-artifacts). The response-cache follow-up adds two complete cleanup pairs and twelve bounded allocation cases: [evidence](validation-2026-10-22.md#response-cache-allocation-and-cleanup-e01e02).
  - [ ] **Next:** **Static:** Audit unresolved claims used by the next implementation decision. Track each concrete missing call/body/type in its owning item; do not reopen completed work merely because more library code exists.

- [ ] **E02 · Static/Device:** Compare each relevant finding with other firmware
  builds and the Standard model before generalizing. Track hash/version, actual
  hardware, route differences, image packing and timing independently.

  Status: **Ongoing**.

  - [x] **Static/Device:** Pin both app hashes, compare 42 routes and the accumulated selected function/data pairs, and retain model-specific rendering/memory/timing differences. [Model comparison](standard-model-comparison.md), [machine-readable map](model-comparison.json).
  - [ ] **Next:** **Static:** Compare remaining decision-relevant handlers/SDK/driver paths and new builds when they become relevant; a mapped external call is not body equivalence.
  - [ ] **Deferred:** **Device:** Validate model-specific concurrency, conditioning and timing differences when experiments resume; never infer cross-flash compatibility.

- [x] **E03 · Static/Account:** Reconcile the older repository OpenAPI snapshot,
  the October capture and observed client behavior. Distinguish advertised schema,
  client consumption, account authorization and actually exercised responses.

  Status: **Complete**.

  - [x] **Static:** Pin and compare July/October schemas: 25 operations, 23 paths and five structural differences. [Snapshot reconciliation](schema-and-client-contract.md#snapshot-changes).
  - [x] **Static/Account:** Audit all 24 captured origin exchanges and distinguish schema declarations, stock consumption and observed authorization. [Capture audit](schema-and-client-contract.md#reconciliation-with-the-captured-exchanges), [implementation differences](schema-and-client-contract.md#differences-that-affect-implementation).

## Coverage of the existing documentation

This table records the audit scope, not completion of its checks.

| Source | Checklist coverage |
| --- | --- |
| [Index/current boundary](README.md) | C01–C12, R01–R09, E01–E03 |
| [Hardware and layout](hardware-and-layout.md) | R01–R07, D01–D03, H01–H07, E02 |
| [Cloud protocol](cloud-protocol.md) | C01–C05, C10–C12, R08, S01–S04 |
| [Schema/client reconciliation](schema-and-client-contract.md) / [metadata](schema-comparison.json) | E03, C01/C02/C05/C07/C10–C12 |
| [Voice](voice.md) | C05–C09, A01/A04/A06, D01–D05 |
| [Image downloads](image-downloads.md) | C03/C04/C07/C08, D03/D05–D07, N05 |
| [Boot and scheduling](boot-and-scheduling.md) | S01–S07, C04/C11, R10/R12 |
| [Storage and configuration](storage-and-configuration.md) | N01–N08, R04/R06, H06 |
| [OTA and recovery](ota-and-recovery.md) | R01–R12, B02 |
| [Local API](local-api.md) | C12, H05, D01/D02/D04/D07, A05/A06 |
| [LED and workflow state](led-and-workflow-state.md) / [records](led-states.json) | H05, A06, D01/D02/D07, E01/E02 |
| [Diagnostics and logs](diagnostics-and-logs.md) | H05, N01/N05, E01, A04/A05 |
| [Rendering and concurrency](rendering-and-concurrency.md) | D01–D08, N05, B03 |
| [HA roadmap](home-assistant-roadmap.md) | A01–A07, C01–C12, S07, D05/D07 |
| [21 October validation](validation-2026-10-21.md) | A01–A03, C01/C02/C06/C10–C12, R11, S01, D03/D06, N02, H05/H07, E01/E03 |
| [Live backend emulation](backend-emulation.md) | C02/C03/C05–C07/C09/C12, D03/D06/D07, S05/S06, H05/H07, E01 |
| [Standard comparison and model schemas](standard-model-comparison.md) | C01/C03–C07/C10/C11, S01, D07, H03/H05, B03, E02/E03 |
| [Evidence and open questions](evidence-and-open-questions.md) | All groups, especially B01–B03 and E01–E03 |
| [Route metadata](route-registrations.json) / [address map](address-map.json) | H05, E01/E02, B01 |
| Existing [local](../frame-api/routes.md) and [cloud](../fraimic-cloud-api/routes.md) API references | C12, H05, E02/E03 |

Explicit fields in [firmware-identity.json](firmware-identity.json):

| Unresolved field | Task |
| --- | --- |
| `full_partition_table` | R01 |
| `bootloader_configuration` | R02 |
| `secure_boot_efuses` | R03 |
| `flash_encryption_state` | R04 |
| `anti_rollback_state` | R05 |
| `physical_recovery_entry` | R07 |
| `custom_image_boot_acceptance`, `verified_custom_boot: false` | R08/R09 |
| `imagedata_capacity` | N01 |
| `descriptor_build_timezone: null` | H07 |

Add newly discovered unknowns here with a stable ID and a link to their evidence.
Do not remove an uncertainty from a topic page simply because it has a checkbox.
