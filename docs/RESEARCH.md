# RESEARCH.md - prior art on the EMOTIV EPOC and its wireless protocol

Compiled 8th August 2026 from web sources, repository source files and vendor
documentation. This document records **what other people have found**. It is not
evidence about our hardware. Anything here that we intend to rely on must be
re-established against our own captured packets and recorded in
[`PROTOCOL.md`](PROTOCOL.md).

Confidence labels used throughout:

- **CONFIRMED** - read directly from primary source code or a vendor document.
- **STRONGLY-SOURCED** - multiple independent secondary sources agree.
- **INFERRED** - reasoned from partial evidence.
- **SPECULATIVE** - single unverified claim or community lore.

> Framing warning. "EMOTIV EPOC" spans about a decade of hardware with at least
> three materially different data formats (classic EPOC 32-byte, EPOC+ pre-2016,
> EPOC+ 2016 and later at 64 bytes). Nearly every fact below is revision
> dependent. Sources are frequently repeating each other rather than measuring.

---

## 0. How this applies to OUR device (read this first)

Our receiver enumerates as `21a1:0001`, `Emotiv Systems Inc.` / `EPOC BCI`,
serial `SN20REDACTED0000`. Set against the literature:

| Literature says | Our device | Reading |
|---|---|---|
| Classic dongle is `1234:ED02`, "Receiver Dongle L01" | `21a1:0001`, "EPOC BCI" | **Divergence.** Our VID/PID is not the most-cited one. |
| python-emotiv special-cases `product_id == 0x0001` as a "consumer" headset | PID is `0x0001` | Consistent. A `0x0001` PID is a known EMOTIV variant. |
| Emokit deliberately matches on name strings, not PID, because IDs vary | n/a | Corroborates that VID/PID varies by revision. Do not treat `1234:ED02` as canonical. |
| Classic report is 32 bytes; EPOC+ 2016 and later is 64 bytes | descriptor declares **32-byte** input report | Consistent with **classic EPOC**, not EPOC+ 2016+. |
| Serial format `SN` + `YYYYMMDD` + 6 chars (example `SN20120229000459`) | same shape, 16 chars, values withheld | **Exact structural match.** Supports a 22nd August 2013 build date. |
| Serials beginning `UD2016` route to the EPOC+ key derivation | ours begins `SN`, not `UD2016` | The **classic** key derivation is the one to try first. |
| AES key uses only the last four serial characters | last four withheld | So `sn[-1] redacted`, `sn[-2] redacted`, `sn[-3] redacted`, `sn[-4] redacted`. |

Working position: this is most likely a **classic EPOC** (14 channels, 128 SPS,
14-bit), on a later-VID dongle revision. STRONGLY INFERRED. It is not settled
until we decode real packets.

The `21a1` VID with product string `EPOC BCI` is not well covered by the
community projects, all of which were written against `1234:ED02`. We should
expect to have to adapt rather than copy.

---

## 1. Product lineage

| Model | Era | EEG channels | Output rate | ADC | Link |
|---|---|---|---|---|---|
| EPOC (classic), incl. "Research Edition" | 2009-2014 | 14 + 2 gyro | 128 SPS | 14-bit, approx 0.51 uV/LSB | 2.4 GHz dongle only |
| EPOC+ | 2015-2016+ | 14 + 9-axis motion | 128 or 256 SPS | 14 or 16-bit | dongle + BLE |
| EPOC X | 2020+ | 14 + 9-axis | 128/256 SPS | 14/16-bit | dongle + BLE + USB |
| EPOC Flex | 2018+ | up to 32 | 128 SPS | 14-bit | dongle + BLE |
| Insight | 2015+ | 5 (AF3, AF4, T7, T8, Pz) | 128 SPS | 14-bit | BLE + dongle |

STRONGLY-SOURCED from EMOTIV's comparison page and GitBook technical
specifications. The classic EPOC figures are CONFIRMED by Badcock et al. 2013,
who measured the pipeline independently.

"Research Edition" was a licence and SDK tier, largely the same hardware as the
consumer unit. This matters because the community decoders use "consumer" and
"research" as names for **two different AES key layouts**, and those names are
used inconsistently across projects (see section 4.1).

### Telling generations apart

The most reliable discriminators, in order of usefulness:

1. **Report size once streaming**: 32 bytes = classic, 64 bytes = EPOC+ 2016+.
2. **Dongle serial prefix**: `SN20...` = classic-era, `UD2016...` = EPOC+ 2016+.
3. **Bluetooth**: classic EPOC has none. Dongle-only is a strong classic signal.

### On the marking `0013374`

Seven digits is the wrong shape for the cryptographic serial, which is a 16
character `SN` or `UD` string read over USB. INFERRED, with high confidence: the
number on the headset body is a unit or asset sticker and is **not** the value
that feeds the AES key. The load-bearing serial is the dongle's USB
`iSerialNumber`, which we have already read.

Note also that EMOTIV serials were reportedly not reliably unique during early
production, so one cracked key could apply to several dongles. STRONGLY-SOURCED
from the Emokit protocol document.

---

## 2. The receiver

- VID `0x1234` / PID `0xED02`, manufacturer "Emotiv Systems Pty Ltd", product
  "Receiver Dongle L01". CONFIRMED from python-emotiv's shipped udev rule
  (`ID_VENDOR_ID=1234`, `ID_MODEL_ID=ed02`) and DeviceHunt's registry entry.
- An alternative PID `0x0001` exists and is treated by python-emotiv as a
  "consumer headset". CONFIRMED from `emotiv/epoc.py`.
- Emokit does not hard-code any PID. It matches on manufacturer and product
  strings containing "emotiv", "epoc" or "brain waves", and also accepts the
  literal product string `"00000000000"` and "EEG Signals". CONFIRMED from
  `util.py device_is_emotiv`. This is direct evidence that IDs and strings vary
  across revisions.
- Enumerates as USB HID, interface class `03`. Communication is **read-only** in
  all community implementations: nothing is ever written to dongle or headset.
  CONFIRMED from the udev rule and the Emokit protocol document.
- The dongle serial is obtainable via a HID **feature report**. CONFIRMED from
  the Emokit protocol document. Worth noting against our own observation that
  interface 1 declares a 6-byte feature report and returns non-zero data.
- Report cadence: classic dongle emits one 32-byte input report per EEG sample at
  128 Hz. Tools often observe 33 bytes because a leading report-ID `0x00` is
  prepended; Emokit's `validate_data` inserts one so the length becomes 33.
  PyWinUSB delivers 33, PyUSB 32. CONFIRMED from `util.py`.
- Chipset: commonly assumed to be a Nordic nRF24LU1+ class part (2.4 GHz radio
  plus 8051 plus USB in one package), which fits the observed behaviour, but no
  accessible teardown confirms it. SPECULATIVE. FCC filings exist that would
  settle it from internal photos: EPOC+ is `2ADIH-EPOC02`, EPOC X is
  `2ADIH-EPOC03`.

---

## 3. The classic EPOC packet protocol

All CONFIRMED against Emokit source unless noted. Bit indices are into the
32-byte decrypted payload.

### Framing and crypto

- 32-byte encrypted report, one per sample, 128 per second.
- AES-128 in **ECB** mode, 16-byte blocks. Each packet is two blocks decrypted
  independently: `decrypt(data[:16]) + decrypt(data[16:])`. No IV. Emokit issue
  147 states plainly that ECB uses no IV. This is a real weakness and it is also
  why decryption can be verified block by block.

### Byte 0: counter and battery

Low 7 bits are a packet counter cycling 0 to 127. When the top bit (`0x80`) is
set the byte instead carries battery level, and implementations emit a synthetic
counter of 128 for that packet.

Battery lookup table from `battery.py`, raw byte to percent. It is a hand-built
table, so it is empirical rather than a formula:

```
255-248 -> 100    243 -> 85    238 -> 62    233 -> 12    228 -> 2
247 -> 99         242 -> 82    237 -> 55    232 -> 6     227 -> 2
246 -> 97         241 -> 77    236 -> 46    231 -> 4     226 -> 1
245 -> 93         240 -> 72    235 -> 32    230 -> 3     225 -> 0
244 -> 89         239 -> 66    234 -> 20    229 -> 2     224 -> 0
```

### EEG sample extraction

Each channel is 14 bits gathered from non-contiguous bit positions. The
extractor, CONFIRMED verbatim from `util.py`:

```python
level = 0
for i in range(13, -1, -1):        # MSB first
    level <<= 1
    b = (bits[i] // 8) + 1         # +1 skips the prepended report-id byte
    o = bits[i] % 8
    level |= (data[b] >> o) & 1
return level * 0.5151515151        # scale to microvolts
```

Bit table `sensors_14_bits`, CONFIRMED verbatim from `sensors.py`:

```
F3  = [10,11,12,13,14,15,0,1,2,3,4,5,6,7]
FC5 = [28,29,30,31,16,17,18,19,20,21,22,23,8,9]
AF3 = [46,47,32,33,34,35,36,37,38,39,24,25,26,27]
F7  = [48,49,50,51,52,53,54,55,40,41,42,43,44,45]
T7  = [66,67,68,69,70,71,56,57,58,59,60,61,62,63]
P7  = [84,85,86,87,72,73,74,75,76,77,78,79,64,65]
O1  = [102,103,88,89,90,91,92,93,94,95,80,81,82,83]
O2  = [140,141,142,143,128,129,130,131,132,133,134,135,120,121]
P8  = [158,159,144,145,146,147,148,149,150,151,136,137,138,139]
T8  = [160,161,162,163,164,165,166,167,152,153,154,155,156,157]
F8  = [178,179,180,181,182,183,168,169,170,171,172,173,174,175]
AF4 = [196,197,198,199,184,185,186,187,188,189,190,191,176,177]
FC6 = [214,215,200,201,202,203,204,205,206,207,192,193,194,195]
F4  = [216,217,218,219,220,221,222,223,208,209,210,211,212,213]
GYRO_X = [224..239]
GYRO_Y = [248,249,250,251,252,253,254,255,240,241,242,243,244,245,246,247]
```

The 14 electrodes are AF3, F7, F3, FC5, T7, P7, O1, O2, P8, T8, FC6, F4, F8,
AF4. That is the human-facing order. The on-wire field order differs and is
given by the bit table above.

### Motion

python-emotiv computes `gyroX = (data[29] << 4) | (data[31] >> 4)` and
`gyroY = (data[30] << 4) | (data[31] & 0x0F)`. CONFIRMED from its source.

**Contradiction worth flagging:** Emokit's `get_gyro` in current master is a stub
that returns the constant 42. Its gyro decoding is broken or disabled. Do not
copy Emokit for motion.

### Contact quality

One 14-bit quality value per packet at bits 99 to 112. Which electrode it refers
to is selected by the packet counter, so quality is time-multiplexed across
packets. Mapping, CONFIRMED verbatim:

```
0/64:F3   1/65:FC5  2/66:AF3  3/67:F7   4/68:T7   5/69:P7   6/70:O1
7/71:O2   8/72:P8   9/73:T8   10/74:F8  11/75:AF4 12/76/80:FC6
13/77:F4  14/78:F8  15/79:AF4
```

Scaling: divide by about 540 on the old model, or 1024 on newer ones. Values near
0.8 to 1.0 indicate good contact. The divisor is empirical and approximate.

### EPOC+ differences

- EPOC+ 2016 and later uses 64-byte reports and a different key derivation.
  Emokit's README says this is explicitly unsupported.
- EPOC+ adds 256 SPS and a 16-bit sample mode. CyKit reads 16-bit big-endian
  pairs and converts with
  `(v1*0.128205128205129 + 4201.02564096001) + (v2-128)*32.82051289`. CONFIRMED
  from `Py3/eeg.py`.

---

## 4. Prior projects

### Emokit (`github.com/openyou/emokit`)

The origin. First cracked by Cody Brocious ("daeken") in 2010, who broke both the
AES and the framing. The maintained fork is under `openyou`; the C bindings moved
to `openyou/emokit-c`.

Relevant files:

- `python/emokit/util.py` - key derivation (`crypto_key`, `new_crypto_key`,
  `epoc_plus_crypto_key`), `get_level` bit extraction, and the stubbed `get_gyro`
- `python/emokit/sensors.py` - `sensors_14_bits`, `quality_bits`,
  `sensor_quality_bit`
- `python/emokit/decrypter.py` - AES-ECB, two blocks per packet, key routing
- `python/emokit/battery.py` - the battery lookup table

It ships brute-forcers (`key_solver_bruteforce*.py`) precisely because which key
variant is correct is uncertain in practice. That is a strong hint about how to
approach our own hardware: enumerate candidate keys and let the data decide.

Status: works for classic EPOC and pre-2016 EPOC+. Explicitly does not support
EPOC+ 2016+. Gyro decode is broken in master. Requires HIDAPI on macOS and Linux.

### python-emotiv (`github.com/ozancaglayan/python-emotiv`)

An independent Linux implementation over PyUSB/libusb, built for BeagleBone and
Raspberry Pi SSVEP work. Logic in `emotiv/epoc.py` (`setup_encryption`) and
`emotiv/utils.py` (`get_level`). Ships a udev rule and an LSL bridge.

**Not usable on macOS as written.** It calls `detach_kernel_driver` and
`claim_interface`, which macOS does not permit for HID-class interfaces. This
matches what we observed directly: both our interfaces report
`UsbExclusiveOwner = AppleUserUSBHostHIDDevice`.

Its "consumer" and "research" key labels are swapped relative to Emokit. See
below.

### CyKit (`github.com/CymatiCorp/CyKit`)

The most complete community decoder for newer hardware. Handles classic EPOC,
EPOC+ at 128 and 256 Hz in 14 and 16-bit modes, and Insight. Decode lives in
`Py3/eeg.py` (`convertEPOC`, `convertEPOC_PLUS`, and the `Setup()` key tables).
Streams over TCP to browser or OpenViBE clients. Windows-first; `tahesse/CyKITv2`
is a community branch for macOS and Linux. README states it does not work with
EPOC X.

Its model numbering, CONFIRMED from source: 1 = EPOC premium/research 128 Hz,
2 = EPOC consumer 128 Hz, 3 and 4 = Insight, 5 = EPOC+ premium 256 Hz 16-bit,
6 = EPOC+ consumer 256 Hz 16-bit, 7 = EPOC+ 14-bit 128 Hz.

### Others

- Forks: `cmcneil/emokit` (refactor), `a455bcd9/emokit` (EPOC+ focus), plus
  several mirrors.
- **BrainFlow**: integrates EMOTIV only through the Cortex API, not by talking to
  the dongle. There is no BrainFlow board that opens the HID dongle and decrypts
  AES itself. INFERRED but strong: no raw-dongle driver was found, and EMOTIV
  lists BrainFlow alongside LSL and OSC as things layered on EmotivPRO.
- **OpenViBE**: had a native EPOC driver requiring the EMOTIV Research Edition
  SDK 3.3.3. That SDK was discontinued and the 64-bit OpenViBE build dropped the
  driver. Current advice is to go through EMOTIV's LSL output. STRONGLY-SOURCED
  from Inria pages and forums, around 2018.
- **Lab Streaming Layer**: `github.com/Emotiv/labstreaminglayer` is official and
  depends on EmotivPRO. python-emotiv's LSL bridge is unofficial and works off
  the raw dongle on Linux.
- **Rust**: no maintained crate for direct raw-dongle EMOTIV access was found.
  INFERRED from absence after targeted search. Perfectly feasible to write with
  `hidapi` plus an AES crate.
- **Cortex API / legacy SDK**: Cortex is a local WebSocket JSON-RPC service that
  authenticates against EMOTIV's cloud and needs a registered app id and secret.
  Raw EEG needs a paid EmotivPRO licence, and third-party apps need a
  Premium/Developer licence. The legacy EmoEngine SDK is discontinued.

### What works without any EMOTIV software

This is the important practical finding, and it is CONFIRMED by the mere
existence and operation of Emokit, CyKit and python-emotiv: reading the HID
dongle and decrypting locally requires **no EMOTIV software, no licence, no
account and no internet**. Everything in our roadmap through to a working BCI is
achievable on that basis.

Conversely, anything routed through Cortex or EmotivPRO carries a licence and
subscription dependency. We are deliberately not going that way.

### Academic

- **Badcock et al. 2013** (PeerJ) validated the EPOC for auditory ERPs and
  documents the signal pipeline: 2048 Hz internal sampling, 14-bit, about
  0.51 uV resolution, downsampled to 128 Hz, 5th-order sinc filter, dual 50/60 Hz
  notch, 0.16 to 43 Hz bandpass. Late ERP components (P1, N1, P2, N2, P3) were
  reliable; MMN was not.
- **Duvinage et al. 2013** evaluated EPOC P300 performance and flagged
  sampling-rate limits.

The 0.16 to 43 Hz analogue bandpass matters for us: it means the alpha band at
8 to 13 Hz passes cleanly, so the eyes-open versus eyes-closed experiment at
Gate 7 is well within the instrument's range.

---

## 4.1 The key-derivation contradiction (important)

Notation: `sn[-1]` is the last serial character. Literals are ASCII: `H`=0x48,
`T`=0x54, `B`=0x42, `P`=0x50, `D`=0x44, `X`=0x58. The key is 16 bytes, AES-128.

**Emokit `crypto_key`** (CONFIRMED verbatim from `util.py`):

- `is_research=False`:
  `[sn-1, 0x00, sn-2, 'T', sn-3, 0x10, sn-4, 'B', sn-1, 0x00, sn-2, 'H', sn-3, 0x00, sn-4, 'P']`
- `is_research=True`:
  `[sn-1, 0x00, sn-2, 'H', sn-1, 0x00, sn-2, 'T', sn-3, 0x10, sn-4, 'B', sn-3, 0x00, sn-4, 'P']`

**python-emotiv `setup_encryption`** (CONFIRMED verbatim from `epoc.py`):

- `"consumer"`:
  `[sn-1, 0x00, sn-2, 'H', sn-3, 0x00, sn-4, 'T', sn-1, 0x10, sn-2, 'B', sn-3, 0x00, sn-4, 'P']`
- `"research"`:
  `[sn-1, 0x00, sn-2, 'T', sn-3, 0x10, sn-4, 'B', sn-1, 0x00, sn-2, 'H', sn-3, 0x00, sn-4, 'P']`

The contradiction, established by direct comparison:

- python-emotiv's **"research"** is byte-for-byte identical to Emokit's
  **`is_research=False`**.
- python-emotiv's **"consumer"** matches the Emokit *protocol document's*
  "consumer" layout, which is **not** what Emokit's own *code* calls consumer.
- CyKit agrees with Emokit's code, not with python-emotiv.

So the words "consumer" and "research" are used inconsistently across projects,
**and** the serial-byte permutation itself differs between the two families.

Practical consequence for us: do not trust any single project's labels. There are
only a handful of candidate keys, all built from the last four serial characters
plus fixed literals. The correct approach is to generate every candidate and
select the one that decrypts to physiologically plausible EEG with a
monotonically advancing counter. Emokit ships a brute-forcer for exactly this
reason.

Newer derivations, CONFIRMED verbatim from Emokit:

- `new_crypto_key` (pure serial permutation, no literals):
  `[sn-1, sn-2, sn-2, sn-3, sn-3, sn-3, sn-2, sn-4, sn-1, sn-4, sn-2, sn-2, sn-4, sn-4, sn-2, sn-1]`
- `epoc_plus_crypto_key`:
  `[sn-1, 0x00, sn-2, 0x15, sn-3, 0x00, sn-4, 0x0C, sn-3, 0x00, sn-2, 'D', sn-1, 0x00, sn-2, 'X']`

`decrypter.py` routes serials starting `UD2016` to the newer functions and
everything else to `crypto_key`. **Our serial starts `SN`, so the classic path
applies.**

---

## 5. macOS specifics

- **Use HIDAPI, not libusb.** macOS binds its own HID driver to HID-class
  interfaces and offers no supported way to detach it. python-emotiv's
  `detach_kernel_driver` approach cannot work here. STRONGLY-SOURCED from the
  libusb and hidapi issue trackers, and CONFIRMED independently by our own
  observation of `UsbExclusiveOwner = AppleUserUSBHostHIDDevice`.
- HIDAPI opens the device non-exclusively through IOHIDManager and receives input
  reports via a callback on a run loop. This is why HIDAPI works where raw libusb
  interrupt transfers fail.
- Recent macOS requires **Input Monitoring** permission for HID devices in the
  generic desktop usage page (keyboards, mice). Vendor-defined usage pages
  generally do not require it. Our own measurement supports this: opening the
  Logitech mouse and the keyboard failed, while every vendor-usage-page device,
  including the EMOTIV, opened without any permission prompt.
- Enumerate with `ioreg -p IOUSB -l -w0`. Note that on macOS 26.6
  `system_profiler SPUSBDataType` returns empty output, so it is not usable here.

---

## 6. Source list

| Source | URL | What it gave us | Verified? |
|---|---|---|---|
| Emokit protocol doc | `github.com/openyou/emokit/blob/master/doc/emotiv_protocol.asciidoc` | framing, quality, battery | mixes measured and inferred |
| Emokit `util.py` | same repo | key derivation, `get_level`, gyro stub | CONFIRMED, read verbatim |
| Emokit `sensors.py` | same repo | bit tables, quality mapping | CONFIRMED verbatim |
| Emokit `battery.py` | same repo | battery lookup table | CONFIRMED, empirical table |
| Emokit `decrypter.py` | same repo | AES-ECB, 2 blocks, UD2016 routing | CONFIRMED |
| Emokit issue 147 | `github.com/openyou/emokit/issues/147` | ECB uses no IV | developer statement |
| daeken original | `github.com/daeken/Emokit`, daeken.com blog, 2010 | first AES break | foundational |
| python-emotiv | `github.com/ozancaglayan/python-emotiv` | key layout, gyro, udev, VID/PID, PID 0x0001 | CONFIRMED code, Linux only |
| CyKit | `github.com/CymatiCorp/CyKit`, `Py3/eeg.py` | EPOC+ 16-bit, model scheme | CONFIRMED code |
| mindgardenai EPOC+ reader | `mindgardenai.com/blog/2024-12-12-emotiv-data-reader/`, 12th Dec 2024 | HIDAPI + AES approach | not independently dated |
| Wimmer teardown | `raphaelwimmer.wordpress.com`, 13th Sept 2010 | protocol level only | no silicon detail |
| EMOTIV comparison / GitBook | `emotiv.com/comparison`, `emotiv.gitbook.io` | channels, rates, connectivity | vendor spec |
| EMOTIV KB | emotiv.com support articles | licensing, connectivity | vendor spec |
| Cortex API | `emotiv.gitbook.io/cortex-api` | app id/secret, licence gating | vendor spec |
| OpenViBE | `openvibe.inria.fr` | SDK 3.3.3 requirement, driver dropped | ~2018 |
| Official LSL | `github.com/Emotiv/labstreaminglayer` | EmotivPRO LSL outlet | vendor repo |
| FCC filings | `fccid.io/2ADIH-EPOC02`, `fcc.report/FCC-ID/2ADIH-EPOC03` | internal photos exist | not yet inspected |
| DeviceHunt | `devicehunt.com/view/type/usb/vendor/1234/device/ED02` | VID/PID registry | third-party registry |
| Badcock et al. 2013 | PeerJ art. 907 | measured 2048 Hz, 14-bit, 0.51 uV, filters | peer reviewed |
| hidapi / libusb trackers | `github.com/libusb/hidapi` issue 239 | macOS HID access | maintainer discussion |

---

## 7. Confidence summary

| Finding | Confidence |
|---|---|
| Classic EPOC = 14 EEG at 128 SPS, 14-bit, approx 0.51 uV | CONFIRMED |
| EPOC+/X selectable 128/256 SPS, 16-bit mode | STRONGLY-SOURCED |
| Classic EPOC is dongle-only; EPOC+/X add BLE | STRONGLY-SOURCED |
| Dongle VID `1234`/PID `ED02` is the commonly cited pair | CONFIRMED |
| Alternate PID `0x0001` exists | CONFIRMED |
| VID/PID and product strings vary by revision | CONFIRMED |
| Enumerates as USB HID, community access is read-only | CONFIRMED |
| Classic report = 32 bytes at 128 Hz | CONFIRMED |
| EPOC+ 2016+ report = 64 bytes | CONFIRMED |
| AES-128 ECB, 16-byte blocks, 2 per packet, no IV | CONFIRMED |
| Key uses only last 4 chars of dongle serial | CONFIRMED |
| "consumer"/"research" labels are inconsistent across projects | CONFIRMED by comparison |
| 14-bit sensor bit table and `get_level` | CONFIRMED |
| Counter byte low 7 bits = sequence, high bit = battery | CONFIRMED |
| Battery lookup table | CONFIRMED, empirical |
| Quality multiplexed by counter, bits 99-112 | CONFIRMED |
| Emokit gyro is stubbed and broken | CONFIRMED |
| BrainFlow reaches EMOTIV only via Cortex | INFERRED, strong |
| No maintained Rust raw-dongle project | INFERRED from absence |
| Raw dongle decode needs no EMOTIV software or licence | CONFIRMED |
| macOS requires HIDAPI, not libusb | STRONGLY-SOURCED, and confirmed by us |
| `0013374` is a unit sticker, not the crypto serial | INFERRED |
| Dongle silicon is nRF24LU1+ class | SPECULATIVE |

---

## 8. Open questions to settle on our hardware

1. Does our `21a1:0001` dongle actually emit 32-byte reports at 128 Hz? The
   descriptor says 32 bytes. Unverified until packets flow.
2. Which key variant decrypts our stream, given serial characters `8`, `8`,
   `G`, `M`? To be settled by generating all candidates and testing.
3. Is our headset genuinely 14-channel classic EPOC? Decode will tell us.
4. What is interface 0's 3-byte report for? No source describes it. Our device
   has a documented interface the literature does not cover.
5. What is in the 6-byte feature report on interface 1? Emokit says the serial is
   fetched via a feature report, but ours returned `a0 ff 1f ff 00 00`, which is
   not a serial. Unexplained.
