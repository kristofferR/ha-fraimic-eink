# Initialization helpers and model-specific failures

[Research index](README.md) · [Startup caller](startup-and-readiness.md) · [Static coverage](static-coverage.md)

**Static and instruction-fixture evidence, 23 October 2026.** The earlier
startup cases replaced component helpers with synthetic return values. This
pass enters selected helpers in Large 0.2.29 and Standard 0.2.28. A worker's
ability to tolerate a returned error does not establish that the real helper
returns an error for every failure.

## Portal success can contain a null event group

Portal initialization, Large `0x4201da30` / Standard `0x4201da04`, checks NVS,
network-interface and default-event-loop initialization with the SDK error-check
handler. An injected nonzero result reaches that fatal-handler boundary; it is
not an ordinary error returned to the background worker. The fixture stops
before panic handling.

After those stages, the initializer stores the event-group constructor result
without checking it, sets its initialized byte and returns zero. A synthetic
null allocation therefore produces **success with a null event group**. A second
call returns success without trying the allocation again. This is a local
initializer result, not proof that every other recovery path is ineffective.

The ready byte is Large `0x3fca7444` / Standard `0x3fca74b4`; the event-group slot
is `0x3fca7474` / `0x3fca74e4`. Two direct callers per build are the normal and
setup background initializers. The earlier
[no-event-group fallback](startup-and-readiness.md#normal-background-completion-tolerates-many-failures)
remains relevant; there is no new physical allocation-failure evidence.

Configuration initialization (`0x42019670` / `0x42019644`) likewise uses the
fatal check for unrecovered NVS initialization errors. Its caller's synthetic
nonzero-return case must not be described as the real response to that fault.

## Readiness and retry policies differ by component

| Helper | Recovered behavior |
| --- | --- |
| Display manager, `0x42028224` / `0x42026bc4` | Mutex allocation failure returns `0x101` and leaves initialized false. Success sets initialized before calling the state transition helper, ignores that helper's return and returns zero. A later call skips new configuration and allocation. It is not a panel-ready probe. |
| Connectivity manager, `0x4202efdc` / `0x4202d708` | Mutex failure returns `-1`. Binary-semaphore failure deletes and clears the new mutex, leaves initialized false and permits a later retry. Successful initialization clears its cached status/counters and latches initialized. |
| Instruction manager, `0x4202b068` / `0x42029808` | Requires the flash manager's ready state, then directory preparation and embedded-asset installation. Failures set state 2 and return an error; a later call retries. State 1 returns success without revalidating the filesystem. |
| HTTP-abort manager, `0x42025e34` / `0x42024884` | Existing mutex returns success; otherwise create it and return `-1` on failure. This initializes abort bookkeeping, not the network or a request. |
| Microphone, `0x4201fd90` / `0x4201fd64` | A failed PDM initialization returns its error while leaving the successfully created RX-channel pointer in the application slot. There is no channel-delete call in this application failure branch. |

The microphone slots are Large `0x3fca75c4` / Standard `0x3fca7634`. The exact
reference census finds fast startup and factory-microphone start as callers of
this initializer on both builds. A future recovery hook must distinguish a
nonnull allocated channel from a fully configured, usable channel. The fixture
does not establish a physical failed-init/retry outcome or run the hardware
cleanup internals.

## Shared I2C initialization retains its mutex after bus failure

The shared I2C manager is Large `0x42028f38` / Standard `0x4202fd6c`, with the
configuration/install helper at `0x42028ea8` / `0x4202fcdc`. Both select port 1
at **100 kHz**, with SDA/SCL **10/11 on Large** and **9/10 on Standard**. The
24-byte GPIO templates have corresponding pin masks `0xC00` and `0x600`.

The initializer creates a mutex only if absent. It performs preparatory
watchdog/driver/GPIO operations without propagating their results, then returns
the final I2C parameter-config or driver-install error. Those failures leave
the ready flag false but retain the mutex. A successful final install latches
ready; subsequent calls return immediately. The fault cases execute the actual
configuration helper and verify its model-specific parameters.

Large's panel communication code also has a separate I2C initializer at
`0x42022460`. It recognizes the shared manager's ready flag and reuses that bus;
otherwise it has its own GPIO/config/install path and separate ready flag.
This is a static dependency, not evidence that two independent I2C buses exist.

The census finds the shared manager in the accelerometer and battery paths on
both models, plus Large's render worker. These entry checks do not provide a
proven initializer-wide concurrent-operation lock. No concurrent bus startup,
hardware NACK or peripheral reset was induced.

## Buffer and battery initialization remain model-specific

Large's allocator `0x42028d94` requires total free PSRAM of at least 2,304,000
bytes and requests one block of that size. Standard `0x42027734` requires at
least 3,168,576 bytes, then requests 2,120,000 audio bytes and 1,048,576 image
bytes separately. Exactly the threshold passes the size precheck; it does not
guarantee sufficiently large contiguous allocations.

The new cases check no-PSRAM, one-byte-short, allocation failure and exact-free
success on both builds. Standard's second-allocation failure frees and clears
the first allocation and its ready flag. This validates the earlier
[separate-buffer trace](standard-model-comparison.md#separate-recording-and-image-allocations)
under modeled allocation results. Each allocator has one identified direct call
from fast startup; the pass does not infer an exposed stock reallocation API.

Battery-manager initialization is `0x42029af0` / `0x42028330`. Both can return
success despite unavailable I2C or an unusable CW2217 gauge, leaving the gauge
availability flag false. Standard additionally configures GPIO 1 and GPIO 42;
either configuration failure returns `-1`. With both configured, it requests
GPIO 42 high without checking the output-set result, then completes its state
initialization. Large does not contain those extra GPIO steps in this helper.
This is a firmware-behavior comparison, not diagnosis of the physical battery
or permission to change power settings.

## Large PMIC readiness precedes expander success

Large's PMIC initializer `0x42021264` checks the communication I2C helper, then
sets its own ready byte at `0x3fca75d9` **before** calling TCA9534 initialization
at `0x42021a1c`. The TCA9534 routine sets its own byte at `0x3fca75db`, writes
configuration register 3 with value 4, clears its cached output byte, then writes
output register 1 with value 0. Either write failure clears the TCA9534 ready
byte and returns the error. The PMIC initializer propagates that error without
clearing its own ready byte.

Executing both original bodies with either write failing therefore leaves
**PMIC ready and expander not ready**. A second PMIC initialization returns zero
without retrying the expander. Failure of the earlier I2C helper does not latch
PMIC ready. These distinctions matter for any future recovery mechanism; a
nonnull handle or initialized flag is not a hardware-health acknowledgement.

PMIC configuration at `0x420212dc` skips initialization when its ready byte is
already set. It then performs 17 ordered writes, starting at registers
`1, 5, 9, 3, 7, 11, 13, 15, 17, 19, 20, 21, 22, 24, 26, 27, 28`, stopping at
the first returned error. Cases cover failure at each write and success while
the expander remains uninitialized. This establishes the local failure path,
not a physical occurrence or the absence of every other recovery path.

The separate helper at `0x42021694` converts five bytes obtained from the panel
into cached voltage-configuration records through `0x4202151c`. It updates RAM;
it is not itself a write to the panel's OTP. Configuration is subsequently sent
through the PMIC write routine.

## Large SPI failure retains partially initialized resources

Large's SPI initializer `0x42022140` configures GPIOs, initializes host 1 and
adds two SPI devices. Bus-init and device-add errors exit the routine. Preparatory
GPIO errors and a MISO pull configuration error are logged or ignored without
preventing the subsequent setup stages.

If the second device fails, the first device handle remains at `0x3fca7648`
while initialized byte `0x3fca75dc` remains false. There is no device-remove or
bus-free call in this failure path. A synthetic retry in which bus initialization
reports already initialized exits before another device-add attempt. This
case models that SDK result; it does not execute the SDK bus registry.

Success stores the first device as the active handle at `0x3fca75e0`, retains
the second at `0x3fca75e4` and latches ready. A later call skips setup. These
findings are Large-specific and do not imply compatible Standard hardware.

## LED initialization can announce completion without a worker

Large `0x42022d6c` / Standard `0x4202181c` use fatal SDK checks for PWM timer
and channel setup. The cases stop at that handler. Other failures are handled
differently: an unexpected fade-service installation error is logged, mutex
allocation is stored without a null check, and the LED task-creation result is
ignored. The final initialization message still executes for each of those
three injected failures.

The worker request is 4,096 stack bytes, priority 5, core 1. Mutex slots are
Large `0x3fca7660` / Standard `0x3fca76b8`. A success log therefore does not prove
the mutex or worker exists. This is distinct from the
[runtime LED state's own guards](led-and-workflow-state.md), and does not
establish how a physical LED looked during any previous operation.

[Driver instruction cases](driver-initialization-cases.json) cover 32 Large
and six Standard scenarios. Five Large bodies contain 830 decoded instructions;
the shared LED initializer contains 179 per build. The cases execute 787 Large
and 160 Standard distinct sites. GPIO, peripheral, allocation and task outcomes
are synthetic; no hardware initialization or induced device fault occurred.

## First helper-pass validation scope

[Numeric evidence](initializer-cases.json) records eight corresponding helper
pairs totaling 565 instructions per build. Seven pairs match normalized
operations; I2C differs at six GPIO operands. Relocated data, three differing
portal diagnostic line numbers and the GPIO template are separately qualified.
The structurally different PSRAM/battery bodies and existing microphone body
are executed separately, without claiming whole-driver equivalence.

Eighteen Large and twenty-one Standard cases execute 565 and 643 distinct
instruction sites. The extra Standard cases cover second-buffer failure and
its two GPIO-configuration failures. An exact-reference audit covers ten roots
per build, finding 25 Large and 24 Standard direct calls and no exact initialized
function-pointer words for those roots. It does not exclude computed calls;
some Ghidra caller labels are fragments of a larger function.

No device operation, heap exhaustion, filesystem mutation, network change,
flashing or HA implementation occurred. Peripheral SDK and hardware outcomes
remain explicit boundaries, not additional success claims.
