# LAB_NOTES.md

Chronological record of every real hardware experiment. Append only. Each entry
records what we were trying to establish, what we actually ran, what happened,
and what it lets us conclude.

Rule: an entry is written whether the result is interesting or not. A negative
result recorded properly is worth more than a positive result remembered vaguely.

---

## Session 1 - 8th August 2026

**Host:** MacBook Pro, Apple Silicon `T8112` (M2 family), macOS 26.6 build 25G72,
Darwin 25.6.0 arm64.
**Repository state:** initial commit `bb4e964`, working tree previously empty
apart from an empty `README.md`.
**Software:** Python 3.14.6 in `.venv`, `hidapi` 0.15.0 (prebuilt cp314 arm64
wheel).
**EMOTIV software installed or running:** none, at any point.

---

### LN-001 - Identify the receiver

**Time:** approx 12:32pm to 12:38pm AEST.

**Aim.** Establish whether our own code can identify the EMOTIV receiver with no
EMOTIV software, and determine exactly what the hardware is.

**Commands.**

```sh
uname -a; sw_vers
system_profiler SPUSBDataType
ioreg -p IOUSB -l -w0
ioreg -r -c IOUSBHostDevice -a -l
ioreg -r -c IOHIDDevice -a -l
hidutil list
.venv/bin/python experiments/01_detect_device/detect.py
```

**Raw output.** [`captures/usb-enumeration.txt`](../captures/usb-enumeration.txt)
(6825 lines), [`captures/gate1-detect.txt`](../captures/gate1-detect.txt).

**Observations.**

1. `system_profiler SPUSBDataType` returned **empty output with exit status 0**,
   both plain and with `-detailLevel full`. It is unusable on this macOS build.
   `ioreg` works correctly and was used instead. This is a host tooling defect,
   unrelated to the receiver.
2. One EMOTIV device present, behind a Genesys Logic hub at location
   `0x01110000`:
   - `idVendor` `0x21a1`, `idProduct` `0x0001`
   - `Emotiv Systems Inc.` / `EPOC BCI`
   - USB serial `SN20REDACTED0000`
   - `bcdDevice` `0x0003`, `bcdUSB` `0x0200`, full speed 12 Mbit/s
   - `bDeviceClass` 0, composite, one configuration
3. Two HID interfaces, both class 3, subclass 0, protocol 0, one endpoint each:
   - **Interface 0**: usage page `0xf0ff`, usage `0x10`, 3-byte input report,
     no output, no feature. Descriptor 20 bytes.
   - **Interface 1**: usage page `0xffff`, usage `0x02`, **32-byte input
     report**, no output, **6-byte feature report**. Descriptor 28 bytes.
4. Both interfaces show `UsbExclusiveOwner = AppleUserUSBHostHIDDevice`.
5. A `Google Chrome` `AppleUSBHostDeviceUserClient` (pid 1433) was attached at
   device level at first observation. It had disappeared by LN-004 and never
   prevented our access.

**Conclusion.** Gate 1 **PASS**. The receiver is identified independently of
EMOTIV software. Its two interfaces are fully described. The 32-byte input report
on interface 1 is the presumed data stream, matching the classic EPOC packet size
reported in the literature.

macOS owns both HID interfaces, so libusb cannot claim them. HIDAPI is the access
route, and it works.

**Unresolved.** What interface 0's 3-byte report carries. No source in
`RESEARCH.md` describes it.

---

### LN-002 - First attempt to receive packets, headset not powered

**Time:** approx 12:38pm to 12:40pm AEST.
**Headset state:** not powered on.

**Aim.** Receive one raw report.

**Commands.**

```sh
.venv/bin/python experiments/02_raw_packets/capture.py --count 100 \
    --idle-give-up 12 --out captures/run001-ffff
.venv/bin/python experiments/02_raw_packets/capture.py --usage-page 0xf0ff \
    --count 20 --idle-give-up 10 --out captures/run002-f0ff
```

**Result.** Both interfaces opened **without error and without any macOS
permission prompt**. Zero input reports from either, over 12 s and 10 s
respectively.

**Captures.** `captures/run001-ffff.bin`, `captures/run002-f0ff.bin`, both
containing zero records.

**Conclusion.** The open path works. No data. At this point the obvious
explanation was that the headset was off, which was true.

**Note on method.** A capture with zero records is still a result and is stored
as such. `analyse.py` reports it explicitly rather than treating it as a failure.

---

### LN-003 - Confirm nothing else holds the device

**Time:** approx 12:41pm AEST.

**Aim.** Rule out another process having seized the HID device, which would
produce exactly the observed symptom (successful open, no reports).

**Commands.** `ioreg` walk of the EMOTIV subtree looking for
`IOUserClientCreator` and `UsbExclusiveOwner`; `ioreg -l | grep IOHIDLibUserClient`;
`ps` for EMOTIV processes.

**Observations.**

- No `IOHIDLibUserClient` attached to the EMOTIV device at all. The only
  `IOHIDLibUserClient` holders on the machine are `WindowServer` (pid 652), for
  the keyboard and mouse.
- The earlier Chrome user client is gone; pid 1433 no longer exists.
- No EMOTIV software running. Earlier `ps` hits were false positives: the string
  "epoc" matches inside the Chromium flag `--time-ticks-at-unix-epoch`.

**Conclusion.** Nothing is holding the receiver. The silence is not contention.

---

### LN-004 - Capture attempt with the headset switched on

**Time:** approx 12:43pm AEST.
**Headset state:** user reports the headset has been switched on.

**Command.**

```sh
.venv/bin/python -u experiments/02_raw_packets/capture.py --count 100 \
    --idle-give-up 20 --out captures/run004-headset-on
```

**Result.** Zero reports in 20 s.

**Conclusion.** The simple explanation from LN-002 is now insufficient. Switching
the headset on did not bring the link up. Escalated to systematic diagnosis.

---

### LN-005 - Systematic diagnosis

**Time:** approx 12:45pm AEST.
**Command.** `.venv/bin/python -u experiments/02_raw_packets/diagnose.py`
**Output.** [`captures/diagnose-001.txt`](../captures/diagnose-001.txt).

**Q1, control experiment.** Attempted to open and read every non-EMOTIV USB HID
device.

- Devices in the generic desktop usage page (`0x0001`) all failed to open:
  Logitech G502 mouse (all four interfaces) and the RAMA U80-A keyboard
  interfaces. `OSError: open failed`.
- Every vendor-defined usage page device opened successfully: Keyboard Backlight
  (`0xff00`), ROG Aura (`0xff72`), Realtek HID (`0xffda`), U80-A raw HID
  (`0xff60`).
- None produced reports, because nothing was generating input during the window.

**Result: INCONCLUSIVE as a positive control.** But it does establish a real
finding: macOS blocks opening generic-desktop HID devices without Input
Monitoring permission, and does not restrict vendor-usage-page devices. This
explains why the EMOTIV opens freely, and confirms the access model in
`HARDWARE.md`.

**Q2, control-path probe.** `GET_FEATURE` (a control read; it cannot alter device
state) on both EMOTIV interfaces:

```
if1 up=0xffff  GET_FEATURE(id=0) -> 00 a0 ff 1f ff 00 00 00
if0 up=0xf0ff  GET_FEATURE(id=0) -> 00 00 00 00 00 00 00 00
if1/if0        GET_FEATURE(id=1) -> read error
```

The leading `00` is the report ID prepended by hidapi, so interface 1's actual
6-byte feature payload is `a0 ff 1f ff 00 00`.

**This is the single most important observation of the session.** It proves
hidapi is genuinely communicating with this device and getting meaningful
non-zero data back. The device is alive and responsive. Only the interrupt IN
stream is empty.

**Q3.** Both interfaces polled simultaneously for 20 s: zero reports from either.

---

### LN-006 - Five-minute link monitor

**Time:** approx 12:46pm to 12:51pm AEST.
**Headset state:** switched on, per the user.

**Command.**

```sh
.venv/bin/python -u experiments/02_raw_packets/monitor.py --seconds 300 \
    --out captures/monitor001
```

**Output.** `captures/monitor001.log`, `captures/monitor001.bin` (header only,
zero records).

**Result.**

- **Zero input reports in 300 seconds.**
- The 6-byte feature report was polled once per second for the whole window and
  **never changed**, staying at `a0 ff 1f ff 00 00`.

**Conclusion.** Two things follow.

1. The receiver is not merely enumerated, it is *responsive*, continuously, for
   five minutes. This is not a dead dongle and not a driver problem.
2. The feature report is either not a link-status field, or it is one and the
   link genuinely never came up. Either way it gives us a stable baseline: if it
   ever changes, that change is meaningful. Worth re-reading once real data
   flows.

---

### LN-007 - THE LINK CAME UP

**Time:** approx 4:10pm AEST.

**What changed.** The user unplugged the headset's USB cable and set its orange
switch to the **USB logo position** (the switch has a power symbol and a USB
symbol). The headset LED went **solid blue**. The dongle LED went from **flashing
green to solid green with a flicker roughly once per second**.

**This resolves LN-002 through LN-006.** The headset was not transmitting because
of its physical switch position and/or being cabled. The receiver, the driver
stack and our software were all correct the whole time. The earlier conclusion
that "the block is not in software" was right; the specific cause was the switch,
not a flat battery.

**Result.** Immediate, clean streaming:

```
2000 reports in 15.621s  (128.03 reports/sec)
```

**Capture.** `captures/run007-linked.bin` (2000 packets),
`captures/mon002.bin` (the user's own 300 s monitor run).

**Feature report changed too**, which is a genuinely useful discovery:

| Condition | Feature payload |
|---|---|
| unlinked | `a0 ff 1f ff 00 00` |
| linked | `21 ff 1f ff 1e 00` |

Byte 0 `a0` to `21`, byte 4 `00` to `1e`. This is a cheap link-status probe.

**Gate 2 PASS. Gate 3 PASS.**

---

### LN-008 - Framing analysis

**Command.** `analyse.py captures/run007-linked.bin`

**Observations.**

- 2000 reports, all exactly 32 bytes, 127.986 reports/sec.
- Inter-packet interval: mean 7.8134 ms, median 7.9794 ms, sd 0.556 ms.
- **Every one of the 32 byte positions takes all 256 values with a mean near 128
  and no counter behaviour.** Zero constant bytes, zero counter-like bytes.

**Conclusion.** The payload is uniformly random at every position, which is the
signature of encryption. This independently confirms the literature's claim that
the payload is encrypted, before we tried a single key.

---

### LN-009 - AES key search

**Command.** `decode.py captures/run007-linked.bin`
**Output.** `captures/gate4-keysearch.txt`

**Method.** All five documented key layouts generated from serial characters
the last four serial characters, each tested against 1000 real packets. Score is the fraction
of consecutive packets whose decrypted byte 0 advances by one modulo 128.

| Candidate | Score |
|---|---|
| **emokit is_research=False** | **100.00%** |
| emokit is_research=True | 0.40% |
| python-emotiv consumer | 1.57% |
| emokit new_crypto_key | 0.41% |
| emokit epoc_plus | 2.36% |
| undecrypted baseline | 0.79% |

**Key CONFIRMED: `<32-hex-key-redacted----------->`.**

Corroborating evidence, independent of the counter test: battery packets appear 8
times in 1000 (0.80%, exactly one per 128-packet cycle) and all carry raw value
`246`, which maps to about 97% on Emokit's table. A wrong key could not produce
both a perfect counter and a correctly-cadenced constant battery byte.

**Method note.** The first version of the scorer credited any packet whose byte 0
had its high bit set, which inflated the undecrypted baseline to 50.59% and made
the test look far less sharp than it is. Fixed to skip battery packets rather
than count them as successes; the baseline then fell to 0.79%. The winner was
100% either way, but the corrected version shows how decisive the test actually
is. Worth remembering: a scoring function that flatters random data hides the
strength of a real result.

---

### LN-010 - Channel extraction attempt, unresolved

**Commands.** `channels.py` and `scan_layout.py` on `run007-linked.bin`.
**Output.** `captures/gate4-channels.txt`, `captures/gate4-layout-scan.txt`.

**Result.** Emokit's `sensors_14_bits` table, adapted for our lack of a prepended
report-ID byte, gives **0 of 14 channels** with lag-1 autocorrelation above 0.9.
An empirical scan of every contiguous 12, 14 and 16-bit field at every bit offset
found only one field above 0.9, and that was byte 0, the counter itself.

**Confound, and the reason this is not yet a conclusion.** The capture was taken
with the headset switched on but not worn with wetted electrodes. Per-channel
statistics show values railing between about 30 and 16350, the signature of
floating inputs. With no scalp contact there is no band-limited signal for the
autocorrelation test to detect, so the test **cannot currently distinguish a
wrong bit table from an absent signal**. Reporting this as "the bit table is
wrong" would be overclaiming.

**One suggestive field.** A 16-bit field at bit offset 163 (byte 20, bit 3) has
mean 1185 with standard deviation 26.6 and range 1099 to 1267, while every other
candidate field swings across thousands. A narrow stable range is what a
connected channel looks like. POSSIBLE, unconfirmed.

**Conclusion.** Gate 4 is half closed: decryption CONFIRMED, channel mapping
UNKNOWN. The next capture must be taken with the headset properly worn and the
felt pads wetted with saline. This is a hardware-preparation problem, not a
search problem.

---

## Current position

Gates 1, 2 and 3 passed. Gate 4 half closed: the AES key is confirmed, the
channel mapping is not.

**Settled facts about this device:**

- 32-byte HID input reports on interface 1 at 128.03 Hz. Measured.
- Payload is AES-128-ECB, two independent 16-byte blocks per packet.
- Key `<32-hex-key-redacted----------->`, derived from serial chars `8 8 G M`.
- Byte 0 is a counter advancing +1 mod 128, 100.00% consistent.
- One battery packet per 128, raw `246`, about 97% charge.
- Feature report distinguishes linked (`21 ff 1f ff 1e 00`) from unlinked
  (`a0 ff 1f ff 00 00`).

**Not settled:** which bits form which electrode.

## Open questions

- What is the real channel bit layout? Emokit's table does not fit, but the only
  capture so far has no electrode contact, so the test is inconclusive.
- What does interface 0's 3-byte report carry? It stayed silent even while
  interface 1 streamed at 128 Hz.
- What is feature byte 4 (`00` unlinked, `1e` linked)? Signal strength is a
  plausible reading, untested.
- What are the constant payload bytes 14, 15, 16, 22 and 29?

## Next experiment

Wet the felt sensor pads with saline, fit the headset properly, confirm contact,
then capture 60 seconds and re-run `channels.py` and `scan_layout.py`. With real
scalp contact the autocorrelation test becomes decisive: real channels will show
lag-1 autocorrelation well above 0.9 and the correct bit layout will stand out.
