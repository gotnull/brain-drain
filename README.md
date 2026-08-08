# brain-drain

Reverse engineering an EMOTIV EPOC EEG headset from the first USB byte upward,
and building a working brain-computer interface on top of it, one experimentally
verified step at a time.

No EMOTIV software, no licence, no subscription, no cloud account.

## Status

**Gates 1, 2 and 3 passed. Gate 4 half closed: stream decrypted, channels not yet
mapped.**

We are receiving live 32-byte packets at 128.03 Hz and decrypting them. The AES
key for this headset is confirmed, the packet counter is 100% consistent, and the
battery reads 97%. What remains is working out which bits form which electrode.

See [docs/PROTOCOL.md](docs/PROTOCOL.md) for the protocol as measured,
[docs/ROADMAP.md](docs/ROADMAP.md) for gate status, and
[docs/LAB_NOTES.md](docs/LAB_NOTES.md) for the full experimental record.

### The stream

| | |
|---|---|
| Rate | 128.03 reports/sec, 32 bytes each |
| Encryption | AES-128-ECB, two independent 16-byte blocks per packet |
| Key | `<32-hex-key-redacted----------->`, from serial characters `8 8 G M` |
| Byte 0 | counter, +1 modulo 128, 100.00% consistent |
| Battery | one packet per 128, raw `246`, about 97% |
| Link status | feature report reads `21 ff 1f ff 1e 00` linked, `a0 ff 1f ff 00 00` unlinked |

The key was not copied from any project. Emokit, python-emotiv and CyKit
contradict each other on the layout, so all five documented candidates were
generated and tested against real packets. The winner scored 100.00%; the next
best scored 2.36%.

### The receiver

The receiver is a USB composite HID device:

| | |
|---|---|
| VID / PID | `0x21a1` / `0x0001` |
| Strings | `Emotiv Systems Inc.` / `EPOC BCI` |
| USB serial | `SN20REDACTED0000` |
| Interface 0 | HID, usage page `0xf0ff`, 3-byte input report |
| Interface 1 | HID, usage page `0xffff`, **32-byte input report**, 6-byte feature report |
| Access route | HIDAPI. macOS owns both interfaces, so libusb cannot claim them |

The 32-byte input report matches the classic EPOC packet size, and the serial
format matches the classic-era `SN` + `YYYYMMDD` + 6-character pattern rather
than the EPOC+ `UD2016` pattern. Working position: this is a classic EPOC on a
later dongle revision. Not yet proven.

## Documents

| Document | What it is |
|---|---|
| [docs/HARDWARE.md](docs/HARDWARE.md) | What this exact physical device is, every claim confidence-labelled |
| [docs/RESEARCH.md](docs/RESEARCH.md) | Prior art: source-by-source, with the contradictions between projects called out |
| [docs/ROADMAP.md](docs/ROADMAP.md) | The ten gates, what closes each one, and what would falsify it |
| [docs/LAB_NOTES.md](docs/LAB_NOTES.md) | Every hardware run, including the failed ones |
| `docs/PROTOCOL.md` | Our own protocol spec. Not written yet: it needs real packets first |

## Experiments

| Directory | Gate | What it proves |
|---|---|---|
| [experiments/01_detect_device/](experiments/01_detect_device/) | 1 | We can identify the receiver without EMOTIV software |
| [experiments/02_raw_packets/](experiments/02_raw_packets/) | 2 | Capture, diagnose and monitor raw HID reports |

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install hidapi
```

That is the whole dependency list.

## Use

```sh
# Gate 1: identify the receiver
.venv/bin/python experiments/01_detect_device/detect.py

# Gate 2: capture raw reports
.venv/bin/python experiments/02_raw_packets/capture.py --count 100 --out captures/run
.venv/bin/python experiments/02_raw_packets/analyse.py captures/run.bin

# If the receiver is silent, work out why
.venv/bin/python experiments/02_raw_packets/diagnose.py
.venv/bin/python experiments/02_raw_packets/monitor.py --seconds 300 --out captures/mon
```

## Principles

**Passive until proven safe.** Nothing in this repository writes to the headset
or receiver. No output reports, no `SET_FEATURE`, no configuration, no firmware,
no pairing changes, no fuzzing. Descriptor reads and `GET_FEATURE` reads only.
The hardware stays in its working state.

**Measurement before belief.** Old repositories are treated as hypotheses to
test, not as truth to copy. `docs/RESEARCH.md` documents a genuine contradiction
between Emokit, python-emotiv and CyKit over the AES key layout, including
projects using the same words for different things. We will resolve it against
our own captured packets rather than picking a side.

**Every claim is labelled.** CONFIRMED, STRONGLY INFERRED, POSSIBLE, or UNKNOWN.
Guesses are never presented as facts.

**Negative results are results.** A capture containing zero packets is stored and
analysed as data, not discarded as a failure.

**Layers stay separate.**

```
USB/HID -> raw packet -> decoder -> EEG sample -> record/replay
        -> signal processing -> visualisation -> BCI
```

Replay from a capture file must be indistinguishable from live hardware to
everything downstream, so that experiments remain repeatable without the headset.

**Say what the signal actually is.** Detecting a jaw clench or a blink through an
EEG headset is EMG or EOG, not mind reading. Both are interesting. Only one of
them is a brain-computer interface.
