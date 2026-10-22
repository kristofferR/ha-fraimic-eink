# Firmware research checklist

[Research index](README.md)

This is the persistent backlog for the explicit unknowns, unverified inferences,
untested behaviors and deferred experiments in the firmware documentation.
Audited through 22 October 2026 against Large 0.2.29 / f1555ee5. Repeated questions
are consolidated under one ID; proposed features are feasibility checks, not
claims that the feature already exists or instructions to implement everything.

Start with local cloud, voice and HA reuse. Recovery findings are prerequisites
for experiments that depend on custom firmware. Battery repair remains deferred
behind the owner's backend priorities.
The owner has explicitly chosen to keep the enclosure closed and focus on backend
emulation. Physical inspection and custom-firmware/recovery experiments remain
deferred; do not repeatedly request board access while pursuing protocol checks.

Check an item only when its linked evidence answers the question. Record firmware
hash, method, result and limitations in the relevant topic page. A confirmed lack
of support is a valid result; a static finding does not close a live-validation
item. Keep private captures and credentials outside the repository.

Method labels: **Static** means binary/source inspection; **Read** means installed
configuration/capability inspection; **Host** means fixtures or a test harness;
**Device** means a controlled physical-frame experiment;
**Account** needs an authenticated owner session; **Hardware** needs physical
identification/access; **Design** means assessing an unimplemented extension.
Device writes, reset, flashing and hardware access are separate experiments,
not actions performed by adding this checklist.

## Latest pass: 22 October 2026

[Static continuation](validation-2026-10-22.md), [earlier validation](validation-2026-10-21.md)
and [live backend pass](backend-emulation.md):
**C09, A01 and H07 completed; 64 items
remain open.** Several open items have substantial new evidence. Completion is
per question, not a count of tool calls or decompiled functions.

| IDs | Progress | Next evidence needed |
| --- | --- | --- |
| C01/C11/D01 | Setup/verification split and redirects traced; response backing memory, conditional verification/poll guard, duplicate-worker and stale-pointer branches mapped; verification JSON is unescaped | Independent enrollment, controlled response/concurrency faults and remaining boot dependencies |
| C11/C01/D01 | Thirty enrollment host groups verify minimal parser acceptance, identity/type/duplicate/NUL boundaries and event-dependent overflow that can alter parsed JSON | Physical response variants, persistence, independent enrollment, actual transport event grouping and verification lifecycle |
| C02/S03 | Five idle polls preserved state; 25 host cases cover parser/field precedence; suppressed error returns differ from parsed empty JSON; I64 zero sentinel can reload an old deadline after failed clear | Device response faults, reboot persistence, remaining snapshot cases and induced NVS failures |
| C02/C08/D01/D07/E02 | Both models share poll-result offsets, separate readiness, two-second post-result task lifetime and non-joining clear; seven function pairs and two caller regions match | Controlled overlap/late-clear faults, full indirect-reference audit, remaining parser/loop comparison and per-job acknowledgement |
| C03 | Local panel/TLS controls retained; 19 matching-SDK host cases cover download framing/timeouts, including real Large-capacity acceptance before chunk termination | Device response faults, retry expiry/cancellation, other TLS consumers and Standard negative controls |
| C01/C03/D01/R11 | Ten current HTTP configurations and the older updater compared; RX/TX defaults, bundle-over-global-CA precedence and URL scheme override traced | Per-consumer TLS/device controls, allocation/transport faults and complete indirect-client audit |
| C01/E01/E02 | Both models have eleven recovered constructor sites, thirteen selector calls and the same eleven HTTP literal hosts; GNU continuation recovers missing multipart calls and rejects Standard's misaligned raw match | Dynamic destinations, indirect/non-HTTP paths, recursive consumer/TLS equivalence and complete offline operation |
| C05/C06/C07 | Large local and Standard vendor success retained; 12 host reader/parser cases establish partial-prefix acceptance, read-cap behavior and per-transport timeout scope | Device response faults, capture limits, worker lifetime, watchdog behavior and cancellation |
| C06/D01/A06/E02 | Recovered capture worker; nine matching-SDK host groups verify partial-timeout data loss and whole-block admission; nine Standard function pairs match capture, stop and completion-signal branches | Physical recording/dropout/stop timing, remaining external SDK/configuration paths and structured capture-result events |
| C05/C08/D01 | Multipart framing uses a separate PSRAM allocation and streams the shared WAV in 4 KiB writes; 120-second transport timeout, exact-write checks and post-body abort registration traced | Malformed fields, allocation/write faults, physical upload cancellation and complete outer-worker cleanup |
| C05/D01/E02 | Twenty-five host parser/field groups verify copy limits, duplicate/NUL/type handling, raw string-part projection and formatted-fields growth; ten Standard/Large function pairs match copying, printing and first-member lookup | Physical malformed-response/allocation controls, complete streaming/framing faults and remaining external parser/helper comparison |
| S01/E02 | Both models distinguish immediate TCP refusal from post-selection error, ignore socket-error query failure and preserve manager cycles after recovery; thirteen function pairs compare probe/queue and recovery thresholds | Controlled backend/WAN outages, refusal/error timing, retained-cycle sequences and full external Wi-Fi/transport faults |
| C07/C08/D01/D07 | Upload task creation passes a borrowed 220-byte caller context; timeout returns without joining, while every worker exit still accesses its status/semaphore pointers | Physical timing, expired-stack effects, late completion/two-job reproduction and complete cleanup design |
| C08/D01/D07 | Download context/handle and 300-second wait plus five-second grace mapped; late success stays failed; forced deletion can skip HTTP cleanup and race self-deletion | Actual scheduler/transport ordering, runtime callback ownership, retained-resource measurements and Standard equivalence |
| C08/D01/D07 | All 21 direct register/unregister/abort-read/reset sites checked; ignored lock failures, double/unowned unregister and false-on-failed-read semantics mapped | Concurrent request/cancellation tests, stale-client effects, allocator/lock timing and Standard comparison |
| E02/C08/D01/D07 | Fifteen Standard/Large function pairs match normalized operations and 210 internal branch targets; same slot ownership and download timeout paths; voice render wait is 90/180 seconds | Physical cancellation/late rendering, complete external cleanup helpers, runtime callbacks and resource measurements |
| C07/C08/D05 | Task creation/WAV lifetime and cancellation windows traced; pending poll can interrupt recording even without a usable image URL; five fixture TLS checks passed | Deferred physical cancellation, response/body-read gaps, worker lifetime and two-job validation |
| C09 | Fifteen host checks and one physical recording-to-fixed-image protocol/driver flow completed, including cache save and return to ready | Complete for bounded transport scope; same-card optical refresh was not witnessed, and STT/generation were not invoked |
| C10 | Captured Standard audio job/panel linked to gallery transcript/original; expired URL refreshed to identical PNG bytes; gallery ID differs from object-key UUID | Long-term retention, changing pagination and final vendor prompt availability |
| C12 | Proxy traced; account/device-key and local HTTPS reads succeeded; 19 JSON host cases expose root/duplicate-field behavior; ID truncation, ignored queries and response failure translation mapped | Explicit create/update/delete, assignment tests and device transport/allocation faults |
| A01 | Installed STT/Assist/AI Task inventory and WAV helper fixture completed | Provider choice/setup belongs to implementation; no image-capable entity currently configured |
| A02/A03 | Five real-library host checks passed; duplicate insertion demonstrated | Persisted import mapping; pull scheduling/locks and no-double-delivery integration |
| R11 | Current/legacy call sites, manifest and forced-version/counter references traced; mode switch's one-poll `0.0.0` override is normally restored before HTTP, but NVS persistence can fail | Host fault fixtures and remaining indirect-reference audit |
| R10/R11/N02 | Twenty-two host case groups cover OTA queue/cooldown branches; long-version mismatch, backward-clock boundary, failed persistence and replacement/retention traced | Physical offer/reporting faults, Standard comparison, full NVS failure semantics and artifact identity |
| R12 | Direct updater framing/timeouts and OTA SDK ordering traced; apparent response-MIME guard reads request headers; sequential erase precedes first-byte validation | Host fault fixtures, busy/safety cases and deferred controlled update/recovery tests |
| S01/S02 | Large startup retries SNTP five times and can invoke AP failover before the public monitor; callback/RTC flag distinction and allocation-failure path traced; Standard public-probe failure separately observed | Local NTP, cold boot/RTC retention, overlapping synchronization, outage timing and fully offline operation |
| S02/E02 | Both models' 32-entry TCP/IP mailbox, blocking hostname barrier and ignored asynchronous control-allocation failures traced; 34-function Standard comparison confirms the relevant queue/failure paths | Injected allocation/queue faults, physical timing, complete external-helper equivalence and actual offline boot |
| S01/C01/C11 | Cached reachability survives station disconnect; fallback AP request ordering and persistent wildcard captive-DNS worker traced | Physical recovery, actual AP configuration, DNS reachability/lifetime and setup/bind failure tests |
| D03/D06/D07 | Normal completion observed; short assets can reach stale-tail rendering or cache save after worker rejection; 1.347 MB free PSRAM cannot hold another full panel buffer | Memory lifetime/fragmentation, induced transfer/size faults and per-image acknowledgment |
| D01/D03/D06 | DMA staging copies one 4,800-byte PSRAM chunk at a time; completion frees it; shared descriptors/manual select state and truncated/overwritten errors traced | Measured DMA-memory fragmentation, controlled transfer/overlap faults and complete higher-level driver exclusion audit |
| S06/D01/D06 | Pre-sleep ordering and final wake-source reset traced; display shutdown discards BUSY timeout, suppresses hardware results and has no render join | Physical shutdown/wake controls, outstanding-worker faults and verified safe power-down |
| R02/R05/R09 | App-side NEW/VALID/INVALID operations and alternate-image checks traced; failed rollback return is discarded, confirmation precedes initializer's Wi-Fi start | Installed bootloader/eFuses, actual alternate-slot contents, interrupted metadata writes and physical rollback |
| C01/D01/D04 | Setup metadata framing and background screen tasks traced; shared pixels written before WAIT/DROP, two-minute Get Started poll hold, 90-second unscoped completion wait | Controlled task/heap faults, overlapping screens/producers, full metadata framing coverage and independent provisioning |
| D06/E01 | Task-watchdog startup is 5 seconds, both idle tasks, panic disabled; renderer unsubscribes before power/conditioning/transfer/refresh | Physical failure/recovery tests, interrupt-watchdog and hardware fallback coverage, remaining indirect references |
| H04/D06/S05 | Conditioning uses full-panel black or white/black clears and a temporary 288 KB block; elapsed selector uses 12/48-hour boundaries; MID suppresses clear errors and can advance the shared timestamp | Panel waveform constraints, physical conditioning/fault tests, other controller paths and interrupted timestamp writes |
| D04/D07/D08/S05 | Maintenance helpers drain the semaphore but treat DROP as success; Standard waits 60 seconds, Large 90; Large blank path can wait on its own busy state, and scheduled history ignores refresh results | Physical maintenance/failure tests, other shutdown callers, concurrent state changes and persisted history errors |
| N02/N03 | Application scalar/blob types and sizes mapped; SDK Wi-Fi/PHY namespaces, mode order and unchecked backup/restore operations traced | Remaining SDK/indirect keys, other-build schema, interrupted switching and migration faults |
| N04/N05/N06 | Wake-image version decisions and 8 KiB validation allocation mapped; validation failure can trigger replacement/unlink; version stamp commit is unchecked | Filesystem/allocation faults, custom-artwork persistence and controlled recovery |
| N08/D01/D07 | Sixteen Large and eighteen Standard RLE host cases verify model geometry, partial writes, unchecked colours, ignored trailing pairs and vendor-asset output; both show/restore paths write before DROP and change markers before completion | Physical rendering, overlap, storage faults, other releases and actual marker/artwork recovery |
| S05/S06 | POSIX parser/default US rules traced; nine parser and eight calendar host cases passed, reproducing stale-DST one-hour target shifts; powered wake/test-timeout observations retained | Physical timezone/DST, stored-schedule recalculation, remaining setter audit and ordinary sleep/wake transitions |
| S03/S04/S05/S06 | Thirty-three host case groups cover deadline selection, missed-album retry and scheduling faults; timer/reason ordering, maintenance correction and conditional recursive fallback traced | Physical wake timing, actual persisted correction, clock changes, concurrency and real timer/NVS faults |
| S05/S02/E02 | Both models have eight direct maintenance-setter calls, all passing four days/03:00; only the setter directly writes the record; key references map to load/save | Installed correction, persistence/clock changes and physical timing; computed indirect references remain outside the negative result |
| H05/S06 | HTTP capacity/shared task, registration failure groups, teardown wait and factory GET/POST behavior added to `/dev`, Wi-Fi, local actions and LED findings | Remaining handler schemas, physical request concurrency, all LED meanings/timing, boot-state and controlled side-effect validation |
| H05/N05/E01 | Log hook recovered; detail visibility, whole-history reset, mutex/truncation losses, binary snapshot and unchecked flush mapped | Controlled log/heap/storage faults, remaining redaction branches and complete diagnostics retention |
| H05/N03/C11 | Onboarding GET/cache semantics and eight embedded page selections mapped; seven script host checks establish local submissions, recurring checks and error-body behavior | Initialization/read faults, remaining pages, real browser behavior, cache refresh and independent enrollment |
| C11/H05 | Account handlers parse one 511-byte receive prefix and cap encoded fields at 127 bytes; thirteen host cases cover encoding expansion, duplicates, omissions and shortened values | Physical fragmented forms, full server parsing/cleanup, remaining form handlers and complete enrollment faults |
| H05/N03 | Wi-Fi form substring matching, decoded-byte truncation, retry cancellation before read and scan escaping traced; 15 C cases plus three JSON checks passed | Physical setup/scan faults, driver acceptance, asynchronous retry termination and other-build comparison |
| H07 | Separate build-log timestamp has −0400; descriptor still has no zone provenance | Retain descriptor null; do not transfer another timestamp's zone |
| H02/C07 | Both builds share sensor candidates, ineffective alternative-probe return, two-way orientation/fallback and post-upload voice sampling | Fitted-part confirmation, physical orientation/failure tests and sample coherence |
| E01/E03 | Missing task entries recovered; restart boundaries/nonreturning flow corrected; consequential time/cancellation branches cross-checked; observed account schema recorded | Remaining incomplete flow and full schema-version comparison |
| E02/H04/D01 | Both app hashes pinned; 42 routes and 73 function pairs compared; Standard has separate audio/image allocations, lacks Large's poll exclusions/creation retries, uses a 2 KiB clear buffer and differs in maintenance ordering | Remaining handler/driver/shutdown differences, physical concurrency/conditioning, same-version comparison and other releases |
| E02/H05/D01/D07 | Thirteen LED-related function pairs match across 826 relocated GNU instructions; 22 host groups cover pending replacement, latch timing, factory gates and conditional stale completion | Physical indications/interleavings, complete caller meanings, SDK/output-driver comparison and other releases |
| E02/C05/C07 | Standard's selected upload/finalize branches match empty upload acknowledgment, 4 KiB WAV chunks, 4,095-byte JSON reads and synchronous finalize; its voice image limit remains 960,000 bytes | Full error/SDK comparison, device response faults, cancellation and late-worker/two-job behavior |

After the earlier unreachable read, the owner woke the frame on USB. Status/logs,
local-backend polling, microphone transport, an approved test-card display and
the combined voice-to-fixed-image flow were then exercised. The backend
record separates host results, physical observations and incomplete handoffs.
The separate Standard handoff adds owner-directed setup, a complete vendor voice
generation, public-probe failure and cleanup evidence; it does not change the
Large image identity or establish independent local provisioning.
Recovery/security/partition questions still need additional evidence; the stock
app cannot answer them alone. B01–B03 remain deferred.
The owner deferred the physical cancellation experiment. Continue static work;
the prepared fixture is stopped and does not need another recording now.
Commit and push completed, validated research batches periodically. The owner
requested more frequent checkpoints after the accumulated static passes.

## Local cloud and voice

Sources: [cloud protocol](cloud-protocol.md), [voice](voice.md),
[image downloads](image-downloads.md), [local API](local-api.md).

- [ ] **C01 · Static/Host:** Audit every consumer of the API, web and auth selectors,
  redirects and server-supplied URLs. Establish the full hostname/dependency set
  an already-paired local backend must replace.
  [Twenty SDK redirect host cases](cloud-protocol.md#redirect-url-handling-differs-from-a-browser)
  verify selected URL shapes, method/body/header retention, status branches and
  the replay limit. Full transport/TLS, device behavior and the remaining
  dependency/consumer audit are still open.
  [Poll request construction](cloud-protocol.md#poll-request-encoding-and-url-limits)
  adds 27 combined host cases for SSID escaping, URL length and one-shot OTA
  reports. No network response or update outcome is implied by those cases.
  The [outbound-client inventory](cloud-protocol.md#outbound-client-and-url-inventory)
  accounts for eleven constructor sites, thirteen selector calls and 43 literal
  HTTP(S) URL occurrences in each model. Startup/error-log selector calls, SVG
  namespaces and an unreferenced legacy LAN literal are distinguished from request destinations.
  Complete consumer-body equivalence, remaining indirect/non-HTTP paths and
  complete state-dependent offline validation remain open.
- [ ] **C02 · Host/Device:** Validate poll parser behavior for settings snapshots,
  missing/invalid fields, schedule clearing and persistence failures. Trace which
  `user_settings` members are actually applied locally rather than merely copied.
  Twenty-five host cases cover selected parser rules; suppressed HTTP/connection
  errors and parsed empty JSON have different state effects. Device faults remain.
  The two recovered `user_settings` consumers copy but do not apply members;
  [result ownership](cloud-protocol.md#poll-completion-is-one-shared-result-not-a-delivery-receipt)
  now distinguishes readiness, task lifetime and clearing from image completion.
  The selected [Standard lifecycle and caller comparison](standard-model-comparison.md#poll-result-ownership-also-matches)
  confirms those behaviors there; it does not cover every parser branch or loop.
- [ ] **C03 · Host/Device:** Verify owner-hosted HTTPS JSON and panel assets, including
  explicit lengths, redirects, response limits and download errors. Test hostname
  and trust behavior with controlled positive/negative certificates; do not infer
  arbitrary self-signed acceptance from the earlier test-chain result.
  [Nineteen SDK-reader host cases](image-downloads.md#host-results-with-the-matching-sdk-reader)
  now reproduce short-body acceptance, incomplete chunked success at Large
  capacity, partial-write retention and timeout-streak behavior. No malformed
  response was sent to either frame.
- [ ] **C04 · Host/Device:** Supply local `create_account` and `get_started` assets;
  verify IP-query handling, format, fetch failures and actual setup-screen behavior.
  Establish what an offline fallback would need.
- [ ] **C05 · Host/Device:** Test multipart voice upload against a plain local HTTP
  service, including empty `{}` fields, required fields, upload tickets, status
  codes, size limits and malformed presign responses. Confirm no S3 service is needed.
  Positive path now reaches the local sink with `{}` fields. Check the discovered
  zero-length upload-acknowledgment requirement separately from positive-length JSON.
  [Multipart tracing](voice.md#multipart-construction-and-streaming) adds field
  filtering/duplicates, framing allocation, exact-write handling and cancellation
  registration only after the body has been sent.
  [Presign field fixtures](voice.md#presign-copying-and-field-reserialization)
  now cover 25 groups, including formatted-JSON expansion, silent URL/key
  truncation, first-duplicate lookup and serialization allocation failure.
  Complete incoming JSON can still become unusable copied fields; physical
  response variants and transport/framing failures remain open.
  [Ten Standard function pairs](standard-model-comparison.md#presign-copying-and-member-lookup-also-match)
  confirm the same result layout, formatted serializer and ASCII first-match
  lookup; the earlier host groups are not counted as a second run.
- [ ] **C06 · Device:** Verify actual WAV format, duration/size limits, initial tap
  suppression, completion taps, cancellation and deadline behavior with a short
  owner-directed recording. Check the near-60-second boundary separately.
  [Capture-reader tracing and nine SDK host groups](voice.md#capture-reads-can-lose-audio-without-invalidating-wav-structure)
  establish conditional audio gaps despite valid stored WAV framing. The
  [stop/completion trace](voice.md#recording-stop-and-completion-are-separate-signals)
  distinguishes the outer wait from task exit and shows why a timeout log need
  not mean user inaction. These do not replace the deferred physical tests.
  The [nine-function Standard comparison](standard-model-comparison.md#capture-loss-and-stop-behavior-also-match)
  confirms matching selected capture/stop paths despite separate audio/image
  allocations; it does not count the host groups again.
- [ ] **C07 · Host/Device:** Exercise finalize with slow responses, timeout, non-200
  statuses, missing URL, status variants, chunked/missing length, truncated/oversized
  JSON and network retry. Establish end-to-end timeout behavior through the proxy.
  Twelve host cases now cover selected fixed-length reader/parser boundaries;
  incomplete HTTP bodies can supply accepted JSON prefixes. Per-transport timeout
  is not an absolute request deadline. Device faults and outer-worker lifetime remain.
- [ ] **C08 · Host/Device:** Trace cancellation through recording, upload, finalize,
  download and rendering. Determine what the backend observes on disconnect and
  what work continues; verify retry/idempotency and stale-result behavior.
  [Ten SDK-state host cases](voice.md#sdk-cancellation-state-and-response-bookkeeping)
  distinguish transport close, conditional reconnect, parser reset and synthetic
  response counters. Concurrent parser/transport access, actual disconnect timing,
  worker exit and force-delete outcomes remain unverified. The
  [download lifetime trace](image-downloads.md#voice-download-timeout-and-forced-task-deletion)
  maps semaphore-before-self-delete ordering, the unguarded retained handle and
  HTTP cleanup bypass; none is a reproduced physical failure.
  [Active-client ownership](voice.md#active-client-ownership-and-failed-unregistration)
  now maps ignored registration/cleanup errors, potential stale client storage,
  cross-request clearing and shared abort-byte classification.
  [Standard comparison](standard-model-comparison.md#cancellation-ownership-and-download-timeouts-also-match)
  confirms matching slot helpers/call sites, SDK cancellation branches and voice
  timeout ownership; runtime faults and external cleanup coverage remain open.
- [x] **C09 · Host/Device:** Complete one local end-to-end voice round trip using
  fixture audio and a known panel image first, then one physical tap-to-image flow.
  Separate transport validation from paid generation and provider variability.
  [Host and device evidence](backend-emulation.md#combined-voiceimage-device-result-c09)
  confirms the stock protocol/driver path; identical pixels prevented an
  independently witnessed second refresh. This does not close D06/D07's failure
  and acknowledgment questions.
- [ ] **C10 · Account:** Read a gallery page/item with an owner session; establish
  token versus device-key permissions, actual `upload_type`/metadata/transcript/style
  values, pagination, stable IDs and original availability after URL expiry.
- [ ] **C11 · Static/Host/Device:** Map complete enrollment, verification, web redirects,
  auth dependencies and identity persistence. Determine how independent local
  enrollment could work without unintentionally forwarding account passwords.
  [Selected page scripts](local-api.md#embedded-setup-scripts-use-local-routes)
  add local form requests, overlapping verification checks and portal polling;
  seven host cases use extracted scripts without contacting the frame.
  [Form parsing](local-api.md#account-form-limits-apply-before-decoding) adds
  thirteen host cases for pre-decoding limits and single-receive prefixes.
  [Thirty response/parser groups](cloud-protocol.md#host-checked-enrollment-response-boundaries)
  now cover field acceptance, unusable identities and event-dependent content
  loss; they do not establish complete enrollment or save/verification behavior.
- [ ] **C12 · Static/Host/Account/Device:** Verify album proxy headers and authorization,
  create/delete/update payloads and device assignment support. Establish which
  vendor album semantics can map to HA playlists; registration alone is insufficient.
  The [body/response follow-up](local-api.md#body-transformation-is-not-schema-validation)
  adds 19 host JSON cases and static framing, identity and error boundaries.
  Mutation permissions, persistence and fault behavior remain untested on-device.

## Home Assistant reuse and proposed capabilities

Sources: [HA roadmap](home-assistant-roadmap.md), [voice integration](voice.md#local-speech-and-ha-integration).

- [x] **A01 · Read/Host:** Inspect the installed HA version and configured STT,
  Assist and AI Task entities. Verify `ai_task.generate_image` availability,
  input/output formats, editing/reference-image support and local-inference options.
- [ ] **A02 · Host/Account:** Validate idempotent gallery import into the library,
  including original retention, transcript/style metadata, pagination, duplicate
  imports and URL expiry. Reuse C10's authenticated evidence.
- [ ] **A03 · Static/Host:** Verify render-without-send reuse, model/orientation/cache
  keys, and integration with existing Cloud/Hybrid, wake-only albums and upload
  locks. Demonstrate that pull delivery does not also cause a local push/redraw.
  [Six additional host checks](home-assistant-roadmap.md#render-only-reuse-and-cache-validation)
  verify actual parameter resolution for both models and two mount rotations,
  no runtime/delivery access and acceptance of damaged cached bytes. Overlay,
  vendor-delivery and scheduler side effects are mapped; an actual pull adapter
  and concurrent delivery coordination remain unimplemented/unvalidated.
- [ ] **A04 · Design/Host:** Validate durable voice-job identity, ownership, retries,
  reload recovery, audio retention/deletion, original storage and edit lineage.
  Prove duplicate finalize requests do not create duplicate work or library items.
- [ ] **A05 · Design/Host:** Compare HA-hosted protocol views with a companion service
  using actual TLS/deployment constraints. Check device-scoped authentication,
  upload/download tickets, bounds and log redaction while preserving admin auth.
- [ ] **A06 · Design/Host/Device:** Evaluate recording/busy/cancel/render-result events,
  async jobs that sleep while processing, no-redraw command success, streaming STT
  and automatic end-of-speech. Identify required firmware/protocol changes and
  backward compatibility for each; a feature decision does not require building it.
  Capture statistics do not implement speech detection, and stored WAV duration
  need not equal elapsed recording time; proposed events should report stop
  reason and captured/stored/dropped byte counts.
- [ ] **A07 · Design/Host:** Check that proposed voice creations, image edits,
  dashboard commands, playlist controls and multi-frame scenes can reuse existing
  library/scheduler behavior. Resolve provider capability, ambiguous-current-image
  and UI/interaction choices before implementation.

## Recovery and OTA prerequisites

Sources: [OTA and recovery](ota-and-recovery.md),
[image identity](firmware-identity.json), [hardware layout](hardware-and-layout.md).

- [ ] **R01 · Static/Device:** Recover the complete partition table: bootloader,
  partition metadata, both application slots, OTA data, NVS, image filesystem,
  calibration and other data partitions. Reconcile the observed app1 offset.
- [ ] **R02 · Static/Device:** Establish the actual bootloader configuration and
  boot-selection/validation behavior; distinguish app SDK defaults from this unit.
- [ ] **R03 · Device:** Read and interpret actual secure-boot/eFuse state and image
  authorization requirements. Do not change eFuses to determine their state.
- [ ] **R04 · Device:** Establish flash-encryption state separately from encrypted
  NVS, and determine what form of backup/restore is possible without exposing keys.
- [ ] **R05 · Static/Device:** Determine anti-rollback/security-version policy,
  accepted downgrade conditions and implications for returning to stock.
  [App-side evidence](ota-and-recovery.md#ota-metadata-and-anti-rollback-evidence-remain-separate)
  matches rollback-enabled, anti-rollback-disabled SDK branches in selected APIs;
  this does not establish installed bootloader/eFuse policy or downgrade acceptance.
- [ ] **R06 · Static/Device:** Establish a complete backup/restore strategy including
  provisioning, calibration and original images. Verify backup coverage/integrity
  and restoration prerequisites; the downloaded app alone is insufficient.
- [ ] **R07 · Hardware/Device:** Identify and verify a recovery entry despite the
  absent USB serial interface: actual test points, boot straps/interfaces or a
  supported recovery route, rather than generic ESP32-S3 assumptions.
- [ ] **R08 · Static/Host/Device:** Prepare and review the smallest backend-URL/trust
  candidate, regenerate integrity fields, then determine custom-image boot
  acceptance only after a recovery path is established.
- [ ] **R09 · Host/Device:** Verify pending-validation checks, confirmation timing,
  actual rollback and stock restoration. Include an unreachable configured backend
  and failed changed functionality, not only PSRAM/I2C health.
  [Rollback selection](ota-and-recovery.md#rollback-requires-a-usable-alternate-image)
  now distinguishes candidate verification, metadata writing and restart. The
  application counts an attempt before the API and discards its failure result.
- [ ] **R10 · Host/Device:** Validate update offers against the disabled auto-update
  preference, repeated/same-version offers, truncation, the three-failure cooldown,
  missing clock, result-report loss and compiled-version/artifact identity mismatch.
  [Queue/cooldown evidence](ota-and-recovery.md#cooldown-clock-and-version-boundaries)
  now includes 22 host case groups. Long versions miss their truncated failure
  identity, a future failure timestamp has a one-hour boundary, and an empty poll
  does not revoke a pending offer. Physical update tests remain deferred.
  [Result consumption](ota-and-recovery.md#result-reporting) now distinguishes
  state/error clearing, compiled versus current version, and report loss before
  URL/client/transport success; durable delivery remains unproven.
- [ ] **R11 · Static/Host:** Trace forced-version bookkeeping and every active OTA
  entry point, including factory controls; establish which newer paths still use
  the older manifest/hash, force-version and statistics mechanisms.
- [ ] **R12 · Static/Host/Device:** Verify direct-download validation, completeness,
  invalid-image handling, partition-capacity checks and the safety predicate under busy,
  Wi-Fi, time and uptime conditions. Reproduce fault cases in a harness before
  attempting controlled device updates; battery scale is tracked in B02.
  The apparent MIME guard reads request headers, and sequential writes can erase
  inactive-slot sectors before rejecting bad image magic. Zero/unknown-length
  bodies skip the read loop and fail finalization. These are static findings.

## Offline boot, sleep and scheduling

Source: [boot and scheduling](boot-and-scheduling.md).

- [ ] **S01 · Static/Host/Device:** Trace the connectivity manager beyond its cached
  getter. Test backend-up/WAN-down, backend-down/Wi-Fi-up and recovery/failover;
  determine how to replace the public TCP gate without breaking AP recovery.
  [Fallback lifecycle](boot-and-scheduling.md#fallback-ap-configuration-and-captive-dns)
  now distinguishes the cached result, Wi-Fi events, AP mode and DNS worker;
  AP disable does not explicitly stop the wildcard DNS listener.
  [Probe branches](boot-and-scheduling.md#reachability-result-branches-and-timeout-scope)
  distinguish immediate refusal, post-selection socket errors and an unchecked
  query failure; three seconds is not a whole-operation deadline.
  [Recovery counters](boot-and-scheduling.md#recovery-thresholds-and-retained-cycle-count)
  retain failover cycles after a successful probe and use count-based thresholds,
  not the elapsed time printed in some logs. Thirteen Standard function pairs
  match these selected paths; actual outage/fault sequences remain untested.
- [ ] **S02 · Static/Device:** Verify local time-source configuration, DNS/service
  dependencies, unsynchronized cold boot and RTC-preserving sleep. Establish
  offline TLS/time/scheduling behavior, including drift and clock corrections.
  Follow up the separate synchronized/completed/in-progress flags, NTP-triggered
  AP failover and semaphore-allocation/overlapping-wait behavior now mapped in
  [the time-service trace](boot-and-scheduling.md#time-service).
  Both models' [HTTP Date callbacks](boot-and-scheduling.md#http-date-does-not-supply-a-fallback-clock)
  ignore the header value and do not provide a clock/synchronized-flag fallback;
  ordinary offline boot and actual local NTP compatibility still need validation.
  Large's [single-slot SNTP and startup delay](boot-and-scheduling.md#sntp-server-selection-and-startup-delay)
  can cancel a delayed request when the first two application waits expire.
  Large's [DHCPv4 parser and hooks](boot-and-scheduling.md#dhcp-does-not-configure-the-stock-time-server)
  skip option 42, including unsolicited time-server offers. The
  [Standard comparison](standard-model-comparison.md#stock-time-service-also-matches)
  confirms the same DHCP and startup-delay branches. Large's
  [pending DNS callback lifetime](boot-and-scheduling.md#pending-dns-callbacks-survive-sntp-stop)
  and eight isolated host cases show stale completion can alter a replacement
  client or rearm work after stop. The Standard comparison confirms those static
  branches too. The [control-queue trace](boot-and-scheduling.md#sntp-control-queue-ordering-and-allocation-failures)
  now distinguishes Large's blocking hostname barrier from three allocation-dependent
  asynchronous controls, and maps lost-stop assertions and unchecked semaphore
  creation failure. The [Standard queue comparison](standard-model-comparison.md#sntp-control-queue-and-failure-paths-also-match)
  confirms the relevant paths there too. Check injected allocation/queue faults
  and physical startup timing; these static branches do not establish
  observed failure or fully offline operation.
  Large's [DNS fallback/cache trace](boot-and-scheduling.md#dns-fallback-and-cached-destinations)
  identifies a separate public resolver in slot 2, preserved across DHCP setup,
  and distinguishes timeout/error fallback from cached-answer reuse. The
  [Standard resolver comparison](standard-model-comparison.md#dns-fallback-cache-and-late-callbacks-also-match)
  confirms the same selected paths and constants. A bounded DNS cutover/outage
  remains for when device tests resume.
  Large's [NTP receive contract](boot-and-scheduling.md#ntp-response-contract-and-clock-application)
  now includes 18 host cases for packet acceptance and timestamp conversion,
  including zero timestamp mapping to 2036. The Standard receive/clock comparison
  confirms those static paths too. Test accurate local NTP separately from SDK
  parse success or the year-only app flag.
- [ ] **S03 · Host/Device:** Exercise future, absent, invalid, past and failed-poll
  deadlines across reboot. Check persistence and the distinction between clearing
  the schedule and a network failure.
- [ ] **S04 · Host/Device:** Validate the strict 30-second margin, equal deadline
  handling, maintenance/album collisions, long transfer/redraw, overdue five-minute
  retry, missing-album fallback and invalid-time fallback.
  [Timer/reason ordering](boot-and-scheduling.md#timer-selection-arming-and-wake-reason-are-separate-operations)
  and 33 host case groups now distinguish candidate filtering, fallback timer
  requests and persisted reasons. Physical timing remains unverified.
- [ ] **S05 · Static/Host/Device:** Validate maintenance calendar calculations,
  default first target, timezone/DST changes and stored schedule limits. Determine
  whether any usable public setter exists for the internal schedule parameters.
  [Timezone and calendar fixtures](boot-and-scheduling.md#timezone-format-and-default-rules)
  now establish the POSIX-only parser and reproduce stale-DST target shifts on
  the host; physical transitions and stored-schedule recalculation remain open.
  [Setter caller audit](boot-and-scheduling.md#maintenance-parameters-have-only-fixed-default-callers)
  finds eight fixed `(4,3,0)` calls and no configurable public entry point in the
  bounded direct-call/pointer/key search. The internal accepted parameter range
  does not establish a backend setting. The [Standard caller audit](standard-model-comparison.md#fixed-maintenance-callers-also-match)
  confirms eight fixed calls there too; persistence and physical timing remain open.
- [ ] **S06 · Device:** Map actual wake sources and transitions for normal, button,
  charger, maintenance, album, first-setup/storage and factory-test modes. Verify
  HTTP reachability and timeout behavior in each, without treating test-mode sleep
  as evidence of normal idle sleep.
  [Static shutdown ordering](boot-and-scheduling.md#pre-sleep-ordering-and-outstanding-work)
  now maps network-before-display teardown, non-joining workers, suppressed
  display errors and final button/timer setup. It does not verify physical sleep.
- [ ] **S07 · Host/Device:** Validate a local pull playlist with wake-only scheduling,
  backend outages, changed plans and HA restart; quantify wake latency and battery
  cost. Check offline cached playlists only after N01/N07 establish feasibility.

## Rendering and concurrency

Source: [rendering and concurrency](rendering-and-concurrency.md).

- [ ] **D01 · Static/Host:** Finish the ownership/lifetime map for recording, audio
  transmission, raw/multipart HTTP, cloud downloads, system images, cache I/O and
  rendering, including indirect references and task/mutex boundaries.
  [Cloud response ownership](cloud-protocol.md#shared-response-ownership-and-verification-guard)
  now distinguishes poll globals, setup stack memory and verification heap memory,
  with a conditional polling guard and untested overlap/cleanup hazards.
  [Instruction tasks](rendering-and-concurrency.md#setup-screen-tasks-and-the-two-minute-poll-hold)
  add a safe copied task context but shared pixel writes before render arbitration,
  a time-limited polling hold and unscoped render-completion signals.
  [Standard's allocation comparison](standard-model-comparison.md#separate-recording-and-image-allocations)
  rules out Large's specific audio/image alias there; image producers still share
  an allocation, and recording/upload reuse still needs job ownership.
  [Large upload-context lifetime](voice.md#late-upload-workers-retain-caller-stack-pointers)
  now follows the borrowed pointer through SDK task setup and all terminal worker
  branches. Timeout can release its caller stack before those accesses; physical
  corruption, late semaphore consumption and two-job interleavings remain untested.
  [Download lifetime](image-downloads.md#voice-download-timeout-and-forced-task-deletion)
  adds its borrowed 1,556-byte context, retained handle, grace-period result policy
  and kernel-versus-HTTP cleanup distinction. Runtime thread-local cleanup,
  concurrent deletion and complete cross-model ownership remain open.
- [ ] **D02 · Host/Device:** Reproduce the shared-buffer interference with controlled
  overlapping operations. Record which bytes/operation are affected and when;
  static missing guards alone do not demonstrate a particular runtime failure.
- [ ] **D03 · Static/Host:** Verify SPI/DMA consumption and completion semantics to
  establish when the source bytes can be released. Evaluate exclusive ownership
  versus a real snapshot against measured free memory and fragmentation.
  [DMA staging](rendering-and-concurrency.md#dma-staging-protects-only-the-current-chunk)
  now establishes current-chunk copy/release and the separate DMA-memory allocation.
  Unsent chunks and shared descriptors/manual controller state still need ownership;
  no concurrent producer or DMA-allocation fault has been exercised.
- [ ] **D04 · Host/Device:** Exercise WAIT/DROP, simultaneous producers, stuck worker,
  task-allocation failure and early render failure. Check busy flags, semaphore
  behavior, recording-state query failures and timeout cleanup.
  [Maintenance](rendering-and-concurrency.md#maintenance-refresh-has-separate-completion-rules)
  adds DROP-as-success, an unwaited fallback and a conditional blank-refresh
  self-wait; these need controlled validation, not normal-frame inference.
- [ ] **D05 · Host/Device:** Validate voice versus scheduled-content races and every
  cancellation stage, including recording before presign. Check how far HA locks
  and backend holds help and which cases require firmware ownership/events.
- [ ] **D06 · Static/Host/Device:** Trace and inject controller/SPI, BUSY, PMIC and I2C
  failures. Establish watchdog behavior for the power-good wait, recovery and safe
  shutdown; distinguish logged failures from propagated results.
  The [task-watchdog trace](rendering-and-concurrency.md#the-task-watchdog-does-not-bound-the-long-panel-sequence)
  establishes early render unsubscription and non-panic startup policy. Idle-task
  supervision does not impose a render deadline; whole-device recovery remains open.
  [Conditioning](rendering-and-concurrency.md#conditioning-adds-full-panel-clear-cycles)
  adds unconditional MID success and timestamp advancement before artwork transfer;
  neither that timestamp nor its log establishes panel completion.
- [ ] **D07 · Host/Device:** Correlate accepted/cached/worker-ended/driver-completed/
  power-safe states with the physical panel. Verify a content-ID result design
  reports errors accurately and does not mistake semaphore release for success.
- [ ] **D08 · Device:** Confirm maintenance-only `last_refresh` behavior across local
  upload, voice, system images, maintenance, errors and reboot. Verify history-ring
  persistence and absence of per-image identity in the exposed field.
  Static tracing now shows the scheduled caller appends after ignoring the refresh
  result; a changed timestamp alone cannot establish maintenance success either.

## Storage, identity and system artwork

Source: [storage and configuration](storage-and-configuration.md).

- [ ] **N01 · Static/Device:** Establish actual `imagedata` partition size, free space,
  allocation overhead, wear-leveling behavior and practical endurance/write budget.
- [ ] **N02 · Static/Host:** Complete the NVS schema, including value types, defaults,
  namespaces and references omitted from the current table. Map compatibility and
  migration across versions without publishing identity/password values.
- [ ] **N03 · Host/Device:** Verify production/development identity and Wi-Fi isolation,
  legacy-key migration, reset semantics, timezone sharing and interrupted/failed
  saves. Determine exactly what is preserved and what requires reenrollment.
- [ ] **N04 · Host/Device:** Validate mount retries and format-on-failure decisions
  with missing legacy key, NVS read error and filesystem corruption in a disposable
  fixture. Establish which state/artwork survives recovery on the actual layout.
- [ ] **N05 · Host/Device:** Verify partial writes, flush/fsync errors, truncated
  last-image loads and save-failure-with-render behavior. Assess an atomic cache
  replacement/hash design against actual FAT support and available space.
- [ ] **N06 · Static/Host/Device:** Verify custom wake-up artwork feasibility and
  persistence across version changes, missing/truncated/same-size corrupt files,
  resets and cache recovery. Establish the true validation/palette contract.
- [ ] **N07 · Design/Host:** Determine feasible offline playlist capacity, eviction,
  canonical restoration and content deduplication using measured storage. Account
  for system artwork, temporary files and wear before promising multiple images.
- [ ] **N08 · Host/Device:** Test generated low-battery/status RLE artwork, invalid
  palette values and malformed runs; verify actual rendering and preservation of
  last artwork/sys_img state. [Sixteen host cases and marker tracing](storage-and-configuration.md#status-decoder-validation-and-partial-writes)
  now cover malformed run/size, palette and partial-write behavior. They do not
  close physical rendering, overlap, NVS-failure or next-boot restoration checks.
  [Standard's geometry and marker comparison](storage-and-configuration.md#standard-status-assets-use-different-row-geometry)
  adds eighteen host cases and an independent complete asset decode; the same
  outstanding physical and storage-fault checks apply to both models.

## Hardware and remaining local interfaces

Sources: [hardware](hardware-and-layout.md), [local API](local-api.md),
[frame API reference](../frame-api/routes.md).

- [ ] **H01 · Hardware:** Identify the microphone's physical part number and verify
  the recovered PDM wiring/configuration against the actual board.
- [ ] **H02 · Static/Hardware:** Identify which accelerometer is fitted, separate
  probe candidates from detected hardware, and verify orientation behavior.
  [The software trace](hardware-and-layout.md#accelerometer-target-and-orientation-semantics)
  identifies fixed address `0x1e`, ID `0x41`, a LIS2HH12TR-labelled target and a
  nonfunctional alternative-probe success return. It does not establish the
  fitted part. Orientation is two-way, has no hysteresis and defaults to portrait
  on error. Standard's relevant branches and decoded probe records now match;
  physical checks and other releases remain open.
- [ ] **H03 · Static/Hardware:** Determine whether speech/audio output hardware
  exists and is usable; microphone input does not establish speaker capability.
- [ ] **H04 · Static/Host/Hardware:** Determine supported partial-refresh/custom
  waveform modes and their panel/power constraints; do not transfer capabilities
  from another display model without evidence. Recovered MIN/MID conditioning
  performs full-panel clears through the ordinary refresh path; these names do
  not identify partial-update or custom-waveform support. Other controller paths
  and panel-specific constraints remain open.
- [ ] **H05 · Static/Device:** Map request/response schemas, authentication, boot-state
  availability and side effects for all 42 registrations. Cover action/log/dev/test
  controls and undiscovered setters; validate read-only branches first and track
  mutating/destructive branches as explicit separate experiments. Albums are C12.
  `/dev` authentication is now recovered statically on both builds; its actions
  remain unsubmitted and its storage-failure behavior is not device-validated.
  [Local action ordering](local-api.md#restart-sleep-and-refresh-acknowledgments)
  and the [LED protection latch](led-and-workflow-state.md) are now mapped;
  physical LED timing, remaining state meanings, contended guards and Wi-Fi
  form boundary behavior are untested. Standard table bytes and thirteen
  [LED arbitration helpers](led-and-workflow-state.md#standard-comparison-and-host-scope)
  now match; physical interleavings, full caller/SDK/output-driver comparison and
  other releases remain in E02. Wi-Fi scan/escape, AP-switch fault,
  separate reachability and stats-erasure behaviors still need physical checks.
  [Wi-Fi parsing and scan escaping](local-api.md#wi-fi-field-matching-and-byte-limits)
  now have isolated host cases for truncation, substring fields and invalid JSON;
  no credentials, scan requests or network changes were submitted to a frame.
  [Diagnostic storage](diagnostics-and-logs.md) adds fixed-cookie detail filtering,
  whole-history resets and unchecked persistence; retain the remaining log-loss,
  allocation, redaction and clear/flush fault cases as untested.
- [ ] **H06 · Static/Hardware:** Establish current/voltage calibration, fitted battery
  arrangement and hardware measurement accuracy separately from software labels.
- [x] **H07 · Static:** Resolve descriptor build timezone if supporting provenance
  exists; otherwise retain the explicit null/unknown rather than inventing one.

## Deferred battery investigation

Sources: [battery observation](evidence-and-open-questions.md#battery-observation),
[OTA voltage scale](ota-and-recovery.md#apparent-battery-scale-mismatch).

- [ ] **B01 · Static/Device:** Determine the root cause of false cable-connected
  state, including the −50 mA branch, actual plugged/unplugged readings, current
  sign/calibration and resulting sleep decisions. Preserve the owner's deferral
  of the battery fix while investigating backend functionality.
- [ ] **B02 · Host/Device:** Validate the apparent OTA one-cell/two-cell voltage-scale
  mismatch and effective charge protection using controlled inputs/bench conditions,
  without using low-charge flashing as the first validation method.
- [ ] **B03 · Device:** Measure long-term sleep/idle, voice, Wi-Fi recovery, display
  maintenance and local-pull energy use, including cable/LED/keep-awake effects.
  Compare behavior before and after any eventual firmware changes.

## Evidence quality and compatibility

Source: [research method](evidence-and-open-questions.md).

- [ ] **E01 · Static:** Revisit incomplete Ghidra control flow, inferred types,
  function boundaries and indirect references for claims used by implementation.
  Validate consequential instructions with the matching Xtensa configuration.
- [ ] **E02 · Static/Device:** Compare each relevant finding with other firmware
  builds and the Standard model before generalizing. Track hash/version, actual
  hardware, route differences, image packing and timing independently.
- [ ] **E03 · Static/Account:** Reconcile the older repository OpenAPI snapshot,
  the October capture and observed client behavior. Distinguish advertised schema,
  client consumption, account authorization and actually exercised responses.

## Coverage of the existing documentation

This table records the audit scope, not completion of its checks.

| Source | Checklist coverage |
| --- | --- |
| [Index/current boundary](README.md) | C01–C12, R01–R09, E01–E03 |
| [Hardware and layout](hardware-and-layout.md) | R01–R07, D01–D03, H01–H07, E02 |
| [Cloud protocol](cloud-protocol.md) | C01–C05, C10–C12, R08, S01–S04 |
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
