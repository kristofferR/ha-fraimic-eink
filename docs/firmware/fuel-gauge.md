# Fuel-gauge initialization and read consistency

[Research index](README.md) · [Hardware](hardware-and-layout.md) · [Initializer audit](initialization-helpers.md)

**Static and instruction-fixture evidence, 23 October 2026.** These findings
describe the CW2217 driver in the pinned applications. They do not establish
the installed battery arrangement, calibration accuracy or cause of battery
drain. No device register or battery profile was changed.

## Profile acceptance checks eight bytes, programming writes eighty

Profile checking is Large `0x420316e0` / Standard `0x420301a4`. It first reads
mode register `0x08`; nonzero returns 1. It then reads register `0x0b`; an unset
high bit returns 2. It compares **only the first eight profile bytes**, at
registers `0x10` through `0x17`, against its cached profile. A mismatch returns
3; an I2C error propagates; eight matching bytes return zero.

The profile writer, Large `0x420314b8` / Standard `0x4202ff7c`, writes **80
bytes** at registers `0x10` through `0x5f`, stopping on the first returned error.
Consequently successful profile checking does not prove that the other 72
bytes match. The instruction cases accept a synthetic mismatch at byte 8 or
79 because neither is read, and reject mismatches at byte 0 or 7.

This is an acceptance-policy limitation, not evidence that the fitted gauge has
an incorrect profile. The configured profile is copied into RAM at Large
`0x3fcaca98` / Standard `0x3fcacb00`; the public evidence includes no profile
payload or proposed replacement.

## Configuration and readiness are bounded separately

Configuration, Large `0x420315f4` / Standard `0x420300b8`, requests sleep, writes
the profile, writes update/configuration registers and requests active mode.
It then reads register `0xa7` up to **100 times**, looking for bits `0x0c` both
set. Each attempt requests a five-tick delay; success adds another five-tick
delay. Exhaustion requests active mode again and returns `0x107`.

The fixture checks readiness on attempts 1 and 100 and no readiness in the
100-attempt budget. The requested delays are not a wall-clock upper bound:
I2C operations, logging and task scheduling add time. The outer initializer
can make up to three state-check/configuration cycles; this is separate from
the 100-read inner loop.

## A third sample is accepted without another equality check

The two-byte read helper is Large `0x42031850` / Standard `0x42030314`. It reads
the register pair twice. If the values match, it returns that value. If they
differ, it reads once more and returns the third value **without requiring it
to match either previous sample**. The intervening delay requests are zero
ticks, so they do not specify a positive settling interval.

The cases cover matching samples, three different values, and failure on each
read. A failed read returns its error without changing the caller's output in
these cases. A consumer must still check that error; some higher-level telemetry
wrappers initialize a temporary to zero and ignore the driver's return.

For example, Large wrappers `0x4202a7dc`, `0x4202a7fc`, `0x4202a820` and
`0x4202a840` return initialized defaults when the gauge is absent or a driver
read fails without writing output. These correspond to temperature, current,
cycle count and state-of-health reads. A zero is therefore not sufficient to
distinguish a valid measurement from unavailable data. This wrapper finding
is Large-specific; it is separate from the paired low-level read comparison.

[Numeric evidence](wifi-gauge-cases.json) records the complete paired CFGs and
fourteen gauge cases per build, alongside the Wi-Fi cases. Register contents,
I2C results and timing are synthetic. Physical readings and calibration remain
explicitly deferred.
