# Startup failures and readiness

[Research index](README.md) · [Boot and scheduling](boot-and-scheduling.md)

**Static and host evidence:** Large 0.2.29 and Standard 0.2.28. This pass follows
early initialization errors into their caller, then checks selected background
task-creation and completion-wait branches. It does not execute the background
initializer, bring up networking or induce a device failure.

## Early initialization has a real return value

Fast initializer Large `0x420153b0` / Standard `0x420153d0` is incorrectly typed
as `void` in the exploratory Ghidra export. GNU instructions preserve its result
in return register `a2`; the application entry tests the returned value in `a10`.
When nonzero, entry logs the initialization failure and returns before invoking
the main loop. This branch does not itself request a restart or deep sleep.
Returning from application entry is not a claim about what other SDK tasks or
already-initialized peripherals subsequently do.

The selected fast bodies contain 413 instructions and match after relocation,
apart from an error-check diagnostic source line: 515 on Large, 516 on Standard.
Their model-specific allocators and drivers are external to this equivalence.

| Fast-initialization result | Recovered caller behavior |
| --- | --- |
| NVS initialization fails outside its two recovery conditions | Return the error; application entry exits before main |
| NVS reports `0x110d` or `0x1110` | Attempt NVS erase, then retry initialization; a failed retry returns its error |
| Recovery erase fails | Invoke the SDK error-check failure handler; the host case stops at that call |
| PSRAM-manager initialization fails | Return the error; skip later cache/instruction/recording initialization |
| Flash-image manager fails for an existing user | Log the failure; still attempt instruction-manager and recording initialization |
| Flash-image manager fails for a first-time user | Log the failure; skip instruction initialization in this branch, then return success if earlier required stages succeeded |
| Instruction-manager initialization fails | Log it; this failure does not become the initializer's return code |
| Existing-user recording-system initialization fails | Return that error; application entry exits before main |
| First-time user | Skip recording-system initialization in this early phase |

The NVS recovery attempt is existing firmware behavior, not an experiment run
by this research. See the [storage initialization notes](storage-and-configuration.md#nvs-is-not-the-image-filesystem)
for its data-loss implications. The matching SDK
[error-check implementation](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_system/esp_err.c)
distinguishes its aborting and non-aborting handlers. The fixture substitutes a
stop at the selected failure handler; it does not emulate panic or reset.

## First-time state is not proof of account enrollment

In this initializer, the first-time byte is derived from the Wi-Fi-present
predicate, plus `force_ftu == 1` when the selected environment is development.
The separate account-complete predicate participates in diagnostic state logs;
it does not independently set this first-time byte.

The host case with Wi-Fi present and account-complete false therefore still
selects the existing-user fast path and attempts recording initialization. This
does not establish successful authentication or complete provisioning. Those
predicates have separate [identity and credential semantics](storage-and-configuration.md#cached-identity-and-later-writes-after-reset).
In production, a nonzero force-first-time marker invokes the existing clear
helper; the actual persistence of that clear was not exercised here.

## Background completion depends on wake context

After successful early initialization, the main loop starts the background
initializer through differently named task-creation sites. In selected
existing-user cases, creation failure does not have one universal outcome:

| Wake path | Background creation fails | Completion wait before the selected next step |
| --- | --- | --- |
| Ordinary cold boot, both models | Log warning, request completion wait; a failed wait still reaches idle input handling | 6,000 ticks, a requested 60-second timeout at the compiled 10 ms tick |
| Button-classified wake, both models | Log warning, then reach idle input handling | No background-completion semaphore wait on this path before idle |
| Cable-classified wake, Standard | Log warning, then reach idle input handling | No such wait before idle |
| Album timer wake, both models | Call ordinary pre-sleep instead of proceeding to the completion wait | Successful creation instead reaches a 6,000-tick wait |

Cold boot also reaches idle when task creation succeeds but the modeled
completion wait returns failure. That wait is at Large `0x42013813` / Standard
`0x42013793`; the album wait is at `0x42012a83` / `0x420129e3`. The fixture returns
semaphore outcomes immediately, so these are **requested wait budgets**, not
measured elapsed time. It does not execute album handling after a successful
wait or every first-time/maintenance path.

The selected task requests pass stack-size argument 8,192 and priority 5.
No background worker is run by the fixture. Reaching idle input handling is
therefore an application control-flow checkpoint, not a promise that Wi-Fi,
the local HTTP server, cloud polling or the panel is ready. A future firmware
event should distinguish early-initialization success, task creation, actual
service readiness and recording admission. The existing
[HTTP lifecycle](local-api.md#server-capacity-and-lifecycle) and
[public reachability gate](boot-and-scheduling.md#public-reachability-gate)
remain additional dependencies.

## Coverage and limits

[Numeric cases](startup-admission-cases.json) record 24 Large and 25 Standard
scenarios: fifteen early-init cases, four real entry-to-initializer cases and
five/six main-loop task/wait cases. They execute 701 and 782 distinct instructions
respectively with synthetic memory and external helper results. Standard has
one extra case for its reachable cable-classified boot branch.

The entry success case stops immediately after the fast initializer. Main cases
seed an existing-user state and synthetic semaphore handle; they do not emulate
the RTOS, network, NVS, peripheral drivers or the background worker. No physical
fault, flash erase, reset, recording or backend change occurred. See the
[validation record](validation-2026-10-22.md#startup-failure-propagation-and-readiness-s06e01e02).
