# Application helper audit

[Research index](README.md) · [Static coverage](static-coverage.md) · [Role ledger](application-helper-roles.json)

**23 October 2026, pinned Large application.** A navigation audit found 130
nonempty Ghidra entries in the candidate vendor-code region whose exact entry
address lacked a link in the existing prose/address map. All 130 now have a
descriptive role and byte-checked reachable GNU control flow, totaling **6,366
instructions**. This does not mean 130 new features were discovered: many are
getters, wrappers or dependencies of behavior already documented.

The ledger preserves that distinction. It contains addresses, analytical
descriptions, instruction counts and private-CFG hashes, without vendor source,
binary data or embedded credentials. Model comparison and instruction-case
claims remain in their separate evidence files; this ledger is Large-specific.

## Battery summaries apply display policy to measurements

Large summary builder `0x42029fa4` produces a 24-byte structure containing cable,
charging/full flags, voltage, percentage, classification, LED state and a status
label. In the gauge branch it initializes charge/current temporaries and calls
their readers without checking the returned error codes.

With a detected cable, charge of **98% or higher** is presented as full/100%.
Charge of **95–97%** is also presented as full when current is **at least zero
and below 50** in the driver's current units used as mA elsewhere. Negative
current does not satisfy that second condition. Without a cable, the 98%
threshold still changes the displayed percentage to 100, while the charging
indicator remains off.

The no-gauge branch uses voltage-derived percentage and sample-history state.
It caps a charging estimate at 95% until its settled full-state condition is met.
The optional setup/readiness suppression changes the requested LED state; it
does not undo the other fields already assembled.

Thus a reported 100% is partly an application presentation decision, and a zero
current after an ignored read error can participate in that decision. The
instruction trace establishes these conditions; no physical misclassification,
measurement accuracy or battery fault is inferred. A future diagnostic/backend
interface would benefit from separating measurement validity, raw gauge SOC,
displayed percentage and inferred charging state.

## Wi-Fi setup success is distinct from retry-worker creation

Large setup/connection coordinator `0x4201dd0c` registers Wi-Fi/IP events,
initializes the Wi-Fi driver and chooses saved-configuration connection or
configuration-mode fallback. Several setup errors use fatal SDK checks, rather
than ordinary error returns. The saved-network route tries first-tier connection
at `0x4201d5f8`, then the [second-tier scan](wifi-recovery.md).

When both fail, it enters setup fallback, restores the station configuration
and, if retry mode was inactive, sets the retry-active byte and clears its
attempt count **before requesting the retry task**. The creation result is not
checked before the subsequent startup log. That log does not establish that
the retry worker exists. The coordinator's returned result belongs to its setup
fallback call, not a separately confirmed task-start acknowledgement.

The first-tier helper also handles saved BSSID/channel settings differently
from the second-tier scan, waits on an asynchronous connected flag and tracks
whether its retry counter stops progressing. These are separate layers from
the public-internet probe. An HTTP-ready local backend cannot treat a generic
Wi-Fi/setup log as proof of all those layers being ready.

## Small helpers still affect observable behavior

| Group | Reconciled role / consequence |
| --- | --- |
| Wi-Fi statistics | `0x4202ea78` maintains a twenty-event ring and requests persistence after five changes. Category counters at `0x4202e7e0` are 16-bit. The diagnostic summary at `0x4202eba4` derives severity from the retained event ratios, not an independent radio-health test. |
| Version text | `0x4202d2c4` parses three byte-sized dotted components and preserves bounded input text. `0x4202d330` does not propagate a version-parser error after a successful NVS string read. Displayed stored version text is not independent running-image verification. |
| PMIC/expander | Register helpers, virtual-pin dispatch and voltage-record conversion now have individual roles. `0x42021b6c` checks pin range and destination, propagates the nested read error and writes the selected bit only on success. |
| Cache and instruction helpers | Readiness getters, cache-size query, system-image directory creation, filename lookup and state descriptions are linked to the existing storage/instruction analysis. A readiness getter alone does not validate every asset. |
| LED helpers | Temporary RGB/green-blink routines suspend and resume the ordinary worker; separate task wrappers ignore creation results. They are distinct from the ordinary LED state setter. |
| Identity/authentication | Environment selection and XOR reconstruction helpers are classified without publishing their embedded authorization values. Their presence is not an additional configurable local-backend mechanism. |
| Display transport | Small command/read/reset wrappers lead to the already documented shared SPI descriptors, error narrowing and ignored-result paths. This pass does not relabel those earlier findings as new. |

## Method and limits

Fresh decompilation was read alongside the instruction exports. Incomplete
decompiler paths were recovered explicitly, including the full Wi-Fi candidate
selector, expander pin reader, battery summary and OTA metadata validator.
The GNU recovery utility was also corrected to follow Xtensa floating-condition
`bt`/`bf` targets. Its retrospective scan found missing targets only in four
new, unpublished helper exports; those were regenerated before this ledger.
Previously published instruction fixtures were not affected by that correction.

Complete reachable CFGs here mean decoded instruction/branch coverage under
the recovered function boundaries. They do not establish every dynamic call
target, concurrent schedule, SDK side effect, floating-point calibration or
physical outcome. Simple wrappers were inspected without inventing redundant
test suites. The specific new initialization, Wi-Fi and fuel-gauge policies have
their own separately scoped cases.

The [coverage census](static-coverage.md) still tracks candidate regions,
model-specific helpers and indirect references separately. This helper ledger
does not by itself claim that every function in the complete application image
has been semantically verified.
