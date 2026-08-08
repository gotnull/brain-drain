# PROTOCOL.md - the protocol as observed on THIS hardware

Device: `21a1:0001`, `Emotiv Systems Inc.` / `EPOC BCI`, USB serial
`SN20REDACTED0000`.

Every field is labelled CONFIRMED, STRONGLY INFERRED, POSSIBLE or UNKNOWN.
"CONFIRMED" means measured on this device, with the capture file named.

Last updated: 8th August 2026.

---

## 1. Transport

| Property | Value | Confidence | Evidence |
|---|---|---|---|
| Interface | HID interface 1, usage page `0xffff`, usage `0x02` | CONFIRMED | report descriptor, `captures/gate1-detect.txt` |
| Report size | 32 bytes, no report ID | CONFIRMED | descriptor declares Report Size 8 x Report Count 32 |
| Report rate | **128.03 reports/sec** measured over 2000 packets | CONFIRMED | `captures/run007-linked.bin` |
| Mean interval | 7.8134 ms, median 7.9794 ms, sd 0.556 ms | CONFIRMED | `analyse.py` |
| Direction | input only. No output reports exist on either interface | CONFIRMED | both descriptors show `MaxOutputReportSize = 0` |
| Feature report | 6 bytes on interface 1 | CONFIRMED | descriptor + successful `GET_FEATURE` |

One report carries one EEG sample per channel, giving a 128 Hz sample rate.
STRONGLY INFERRED: the rate matches exactly and the counter advances once per
report.

### Link state and the feature report

`GET_FEATURE` on interface 1 returns 6 bytes. Two states have been observed:

| Condition | Feature payload | Confidence |
|---|---|---|
| No headset linked | `a0 ff 1f ff 00 00` (constant across 300 polls / 5 min) | CONFIRMED |
| Headset linked and streaming | `21 ff 1f ff 1e 00` | CONFIRMED |

Byte 0 changed `a0` to `21` and byte 4 changed `00` to `1e` when the link came
up. This is a usable link-status indicator. POSSIBLE reading: byte 4 is a signal
or link-quality metric. Not yet tested across distances or orientations.

This contradicts the Emokit documentation, which states the dongle serial is
fetched via a feature report. On this device the feature report is not a serial.
The serial is available directly as the USB `iSerialNumber` string.

---

## 2. Encryption

| Property | Value | Confidence |
|---|---|---|
| Algorithm | AES-128 | CONFIRMED |
| Mode | ECB, no IV, no chaining | CONFIRMED |
| Structure | two independent 16-byte blocks per 32-byte packet | CONFIRMED |
| Key length | 16 bytes | CONFIRMED |
| Key source | last four characters of the USB serial | CONFIRMED |

For serial `SN20REDACTED0000`: the last four characters, values withheld.

**The key for this device, CONFIRMED:**

```
<key redacted>
```

That is Emokit's `crypto_key(is_research=False)` layout:

```
[sn-1, 0x00, sn-2, 'T', sn-3, 0x10, sn-4, 'B',
 sn-1, 0x00, sn-2, 'H', sn-3, 0x00, sn-4, 'P']
```

### How this was established

Not by trusting a source. RESEARCH.md section 4.1 documents that Emokit,
python-emotiv and CyKit contradict each other here, and that the labels
"consumer" and "research" mean different things in different projects. So all
five documented candidate layouts were generated and tested against 1000 real
packets, scored on whether byte 0 of the decrypted output forms a counter
advancing by one modulo 128.

| Candidate | Counter consistency |
|---|---|
| **emokit is_research=False** | **100.00%** |
| emokit is_research=True | 0.40% |
| python-emotiv consumer | 1.57% |
| emokit new_crypto_key | 0.41% |
| emokit epoc_plus | 2.36% |
| undecrypted baseline | 0.79% |

Evidence: `captures/gate4-keysearch.txt`. The result is unambiguous.

Note the project-naming trap this device walks straight into: the winning layout
is the one **Emokit's code** calls consumer, which is the same bytes
**python-emotiv calls "research"**. The label is meaningless; only the bytes
matter.

---

## 3. Decrypted packet structure

### Byte 0 - counter and battery

| Property | Value | Confidence |
|---|---|---|
| Low 7 bits, when < 128 | packet counter, advances +1 modulo 128 | CONFIRMED |
| Counter consistency | 100.00% over 1000 packets | CONFIRMED |
| When >= 128 | battery packet, not a counter | CONFIRMED |
| Battery packet frequency | 8 in 1000 packets (0.80%), i.e. one per 128 | CONFIRMED |
| Battery raw value observed | `246` consistently | CONFIRMED |
| Battery interpretation | approximately 97% via Emokit's empirical lookup | STRONGLY INFERRED |

The 1-in-128 cadence is exactly right for a battery reading substituted once per
counter cycle, and it corroborates the counter interpretation independently.

### Bytes 1-31 - payload

**Structure is visible but the channel mapping is NOT yet solved.** What is
CONFIRMED about the payload:

Consistently constant or near-constant byte positions across packets: bytes 14,
15 (`00 00`), byte 16 (`02`), byte 22 (`7c`), byte 29 (`69`), byte 1 (`6f`),
byte 8 (`82`). Sample decrypted packets:

```
c= 53  35 6f be 00 67 26 9d f4 82 e2 2c d9 3e 80 00 00 02 21 b7 e0 20 91 7c e6 0d 07 5b df dd 69 6a 40
c= 54  36 6f d6 00 67 26 9d f3 82 f2 2c a9 3f 40 00 00 02 22 17 e0 20 93 7c be 0d 27 59 df e0 69 69 3f
c= 55  37 6f d6 00 57 26 dd f4 82 da 2c c9 3f 80 00 00 02 22 67 e1 e0 96 7c a2 0c b7 58 df e1 69 6a 20
```

This is plainly structured data, not noise. Decryption is correct.

### Channel mapping - UNKNOWN

The Emokit `sensors_14_bits` table (RESEARCH.md section 3.3), adapted for our
lack of a prepended report-ID byte, gives **0 of 14 channels** with lag-1
autocorrelation above 0.9. Evidence: `captures/gate4-channels.txt`.

An empirical scan of every contiguous 12, 14 and 16-bit field at every bit offset
found only one field above 0.9, and that was byte 0, the counter itself.
Evidence: `captures/gate4-layout-scan.txt`.

**Important confound.** This result does not yet prove the bit table is wrong.
The capture was taken with the headset switched on but almost certainly not worn
with wetted electrodes. The per-channel statistics show values railing between
about 30 and 16350, which is the signature of floating, unconnected inputs rather
than of EEG. With no scalp contact there is no band-limited signal for the
autocorrelation test to detect, so the test cannot currently distinguish "wrong
bit table" from "no signal present".

One field is suggestive: a 16-bit field at bit offset 163 (byte 20, bit 3) has
mean 1185 with a standard deviation of only 26.6, range 1099 to 1267, while every
other candidate field swings across thousands. A narrow, stable range is what a
connected channel looks like. POSSIBLE, needs a contact capture to confirm.

**This is resolved by a better capture, not by more searching.** See ROADMAP
Gate 4.

### Gyro, motion and contact quality - UNKNOWN

Not investigated. Any conclusion would depend on the channel mapping, which is
unresolved. Note that RESEARCH.md records Emokit's gyro decoder as a stub that
returns a constant, so it is not a usable reference.

---

## 4. What differs from the published literature

Recorded because it matters for anyone reusing community code on this dongle.

| Literature | This device |
|---|---|
| Dongle is `1234:ED02`, "Receiver Dongle L01" | `21a1:0001`, "EPOC BCI" |
| Reports arrive as 33 bytes with a prepended report ID | 32 bytes, no report ID (descriptor declares none) |
| Dongle serial is read via a feature report | feature report is not a serial; use USB `iSerialNumber` |
| One documented HID interface | two interfaces; the 3-byte `0xf0ff` interface is undocumented anywhere |
| Emokit `sensors_14_bits` decodes channels | does not fit here, at least not on a no-contact capture |

The AES key derivation, the packet size, the 128 Hz rate, the counter and the
battery cadence all match the classic EPOC literature exactly. The channel
packing is the one place this device may genuinely differ.

---

## 5. Open questions

1. What is the real channel bit layout? Blocked on a capture with proper
   electrode contact.
2. What does interface 0's 3-byte input report carry? It produced nothing even
   while interface 1 streamed at 128 Hz.
3. What is byte 4 of the feature report (`00` unlinked, `1e` linked)? Signal
   strength is a plausible reading.
4. What are the constant payload bytes (14, 15, 16, 22, 29) for? Padding, fixed
   headers, or references.
