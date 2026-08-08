# ROADMAP.md

Gates, not phases. A gate is closed only when it has been **demonstrated on this
physical hardware**. Old documentation asserting that something works is not a
gate. Neither is code that compiles.

Each gate states what it establishes, what would count as evidence, and what
would falsify it.

Status as of 8th August 2026.

---

## Gate 1 - Receiver enumerated independently  `PASSED`

**Establishes:** our own software can find and describe the EMOTIV receiver with
no EMOTIV software present.

**Evidence:** `experiments/01_detect_device/detect.py` identifies
`21a1:0001` `Emotiv Systems Inc.` / `EPOC BCI`, serial `SN20REDACTED0000`, and
reads both HID report descriptors. Output saved to `captures/gate1-detect.txt`
and `captures/usb-enumeration.txt`. See LAB_NOTES LN-001.

**Closed:** 8th August 2026.

---

## Gate 2 - Raw packets captured  `PASSED`

**Establishes:** the receiver actually delivers wireless data to us, at some
observable size and rate.

**Evidence required:** a non-empty `BDCAP001` capture containing input reports
from the headset, with timestamps, plus the measured report length and rate.

**Evidence:** `captures/run007-linked.bin`, 2000 packets, all exactly 32 bytes,
**128.03 reports/sec**. See LAB_NOTES LN-007.

**What was actually blocking it.** Not a flat battery, and not software. The
headset's orange switch has a power symbol and a USB symbol; the link came up
when it was set to the USB position with the charging cable unplugged. Headset
LED went solid blue, dongle LED went from flashing green to solid.

The earlier diagnosis that "the block is not in software" was correct. The
specific cause was the switch position, which no amount of host-side
investigation could have revealed.

**Bonus finding:** the 6-byte feature report distinguishes link states, giving a
cheap link-status probe:

| Condition | Feature payload |
|---|---|
| unlinked | `a0 ff 1f ff 00 00` |
| linked | `21 ff 1f ff 1e 00` |

**Closed:** 8th August 2026.

---

## Gate 3 - Packet framing established  `PASSED`

**Establishes:** we know the packet boundary, size and cadence, and which byte
positions are static, which vary, and which behave like a counter, without yet
claiming what any of them mean.

**Evidence required:** `analyse.py` output over a few thousand packets showing a
stable report length, a stable inter-packet interval, and an identified
counter-like field. Headset-on, headset-off and dongle-only conditions compared.

**Evidence:** `analyse.py` over 2000 packets. Report length constant at 32 bytes.
Rate 127.986/sec, inter-packet interval mean 7.8134 ms, sd 0.556 ms.

**Every** byte position took all 256 values with a mean near 128, no constants
and no counters, which is the signature of an encrypted payload. That confirmed
encryption from our own data before any key was tried. See LAB_NOTES LN-008.

**Closed:** 8th August 2026.

---

## Gate 4 - Packets decoded to plausible channel values  `HALF CLOSED`

**Establishes:** we can turn packets into numbers that behave like EEG.

**Evidence required, all of it:**

- a monotonically advancing packet counter across a long capture
- values in a physiologically plausible range once scaled
- a stable sample rate
- a specific channel responding when its electrode is touched or pressed
- motion fields changing when, and only when, the headset is moved
- a battery field that is stable and plausible

### Part A - decryption  `PASSED`

All five documented key layouts were generated from serial characters `8`, `8`,
`G`, `M` and tested against 1000 real packets. No implementation was trusted;
the data chose.

| Candidate | Counter consistency |
|---|---|
| **emokit is_research=False** | **100.00%** |
| emokit is_research=True | 0.40% |
| python-emotiv consumer | 1.57% |
| emokit new_crypto_key | 0.41% |
| emokit epoc_plus | 2.36% |
| undecrypted baseline | 0.79% |

**Key CONFIRMED: `<32-hex-key-redacted----------->`.**

Corroborated independently: battery packets appear exactly 8 times in 1000 (one
per 128-packet cycle), all carrying raw `246`, about 97% charge. A wrong key
could not produce both a perfect counter and a correctly-cadenced battery byte.
See LAB_NOTES LN-009.

### Part B - channel mapping  `NOT PASSED`

Emokit's `sensors_14_bits` table gives **0 of 14** channels with lag-1
autocorrelation above 0.9. An empirical scan of every contiguous 12, 14 and
16-bit field at every bit offset found only the counter.

**But this is not yet a valid negative.** The capture was taken with the headset
switched on but not worn with wetted electrodes, and the per-channel statistics
show values railing between about 30 and 16350, which is what floating inputs
look like. With no scalp contact there is no band-limited signal for the
autocorrelation test to detect, so it currently cannot distinguish a wrong bit
table from an absent signal. See LAB_NOTES LN-010.

**Next action:** wet the felt pads with saline, fit the headset properly, capture
60 seconds, re-run `channels.py` and `scan_layout.py`. This is a
hardware-preparation step, not a search problem.

**Deliverable:** [`docs/PROTOCOL.md`](PROTOCOL.md), written and current.

---

## Gate 5 - Channel and electrode mapping confirmed  `NOT STARTED`

**Establishes:** which decoded channel corresponds to which physical electrode.

**Evidence required:** touching or lightly pressing an individual electrode
produces a response in the expected channel and not in others. This must be done
per electrode, not assumed from a table.

---

## Gate 6 - Stable multichannel visualisation  `NOT STARTED`

**Establishes:** a clean acquisition to display pipeline that runs for minutes
without drift, stalls or dropped packets, and that can replay a recording with no
hardware attached.

**Architectural requirement:** acquisition, decoding, recording, processing and
display stay separate. Replay from a capture file must be indistinguishable from
live input to everything downstream. This is what makes every later gate
repeatable.

---

## Gate 7 - A known physiological effect reproduced  `NOT STARTED`

**Establishes:** the whole pipeline can observe real brain activity, not noise or
artefact.

**Experiment:** occipital alpha, eyes open versus eyes closed. Alpha at roughly
8 to 13 Hz should rise when the eyes close. O1 and O2 are the relevant
electrodes.

Badcock et al. 2013 report the EPOC's analogue path as 0.16 to 43 Hz bandpass, so
the alpha band passes cleanly. The instrument is capable of this.

**Method requirement:** the expected result must not be hard-coded anywhere. Run
both conditions, compute power spectral density, plot both, and report what is
actually there. A null result is a legitimate outcome and gets recorded as one.

**Must also distinguish** genuine EEG from eye movement, blinks, facial muscle
activity, jaw clenching, mains hum at 50 Hz, electrode movement and headset
motion. Each of those is a worthwhile experiment in its own right, and each is a
way of being fooled.

---

## Gate 8 - Intentional binary signal classified in real time  `NOT STARTED`

**Establishes:** a deliberate mental or physical action can be detected live.

**Honesty requirement:** we will state plainly whether a given signal is cortical
EEG or an EMG/EOG artefact. Detecting a jaw clench or a blink with an EEG headset
is useful and interesting, and it is **not** mind reading. Both kinds of result
are welcome; mislabelling them is not.

Candidates will be ranked by ease, reliability, training required, latency, EEG
authenticity and computational cost before one is chosen.

---

## Gate 9 - A small BCI-controlled application  `NOT STARTED`

Deliberately tiny. One binary state, driven by the Gate 8 classifier, with
honest latency and error-rate figures reported alongside it.

---

## Gate 10 - More sophisticated experiments  `NOT STARTED`

SSVEP, P300, motor imagery, multi-class control. Only after Gates 7 and 8 hold up
across sessions and across days, not just once.

---

## Working rules

1. Measurement, then hypothesis, then experiment, then evidence. Never guess
   forward.
2. Build one gate at a time. Do not build five gates ahead.
3. Every hardware run gets a LAB_NOTES entry, including the boring and failed
   ones.
4. Console output is never the only record. Everything gets a capture file.
5. Passive until we understand what a write would do. The device stays in its
   working state.
6. A gate that depends on a claim from old documentation is not closed until that
   claim is demonstrated here.
