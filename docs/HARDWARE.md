# HARDWARE.md - the exact physical device in front of us

Living document. Every claim carries a confidence label:

- **CONFIRMED** - directly observed on this hardware, output saved in `captures/`.
- **STRONGLY INFERRED** - not directly observed, but the observed evidence admits
  few alternatives.
- **POSSIBLE** - a plausible reading of the evidence, untested.
- **UNKNOWN** - we do not know.

Last updated: 8th August 2026.

---

## 1. Host machine

| Property | Value | Confidence |
|---|---|---|
| Model | Apple Silicon, SoC `T8112` (Apple M2 family) | CONFIRMED |
| OS | macOS 26.6, build 25G72 | CONFIRMED |
| Kernel | Darwin 25.6.0, `arm64` | CONFIRMED |
| USB controllers | two `AppleT8112USBXHCI` root controllers | CONFIRMED |

The receiver is attached behind a Genesys Logic `USB2.1 Hub` (`05e3:0610`) on the
second controller, at location ID `0x01110000`. CONFIRMED.

### macOS tooling note

`system_profiler SPUSBDataType` returns **empty output with exit status 0** on
this macOS build. It is not usable for USB enumeration here. All enumeration in
this project uses `ioreg` (and `hidapi` for HID specifics), which work correctly.
CONFIRMED. This is a host tooling defect, not a property of the receiver.

---

## 2. The USB receiver (dongle)

Everything in this section is CONFIRMED by direct enumeration. Raw output is in
[`captures/usb-enumeration.txt`](../captures/usb-enumeration.txt) and
[`captures/gate1-detect.txt`](../captures/gate1-detect.txt).

### Device descriptor

| Field | Value |
|---|---|
| `idVendor` | `0x21a1` (8609) |
| `idProduct` | `0x0001` |
| Vendor string | `Emotiv Systems Inc.` |
| Product string | `EPOC BCI` |
| Serial string | `SN20REDACTED0000` |
| `bcdDevice` | `0x0003` |
| `bcdUSB` | `0x0200` |
| `bDeviceClass` | `0` (class defined per interface) |
| `bDeviceSubClass` / `bDeviceProtocol` | `0` / `0` |
| `bMaxPacketSize0` | `8` |
| `bNumConfigurations` | `1` |
| Enumerated speed | full speed, 12 Mbit/s (`USBSpeed = 1`) |
| `iManufacturer` / `iProduct` / `iSerialNumber` | `1` / `2` / `3` |
| USB device signature | `a12101000300534e3230524544414354454430303030000000030000` |

Note `bDeviceClass = 0` with two HID interfaces: macOS attaches
`AppleUSBHostCompositeDevice`, so this is a composite device. CONFIRMED.

Note the mismatch between `bcdUSB = 0x0200` and full-speed operation. Declaring
USB 2.0 compliance does not oblige a device to run at high speed; a 12 Mbit/s
full-speed link is entirely adequate for this data rate. Not anomalous.

### Interface 0

| Field | Value |
|---|---|
| `bInterfaceNumber` | `0` |
| `bInterfaceClass` | `3` (HID) |
| `bInterfaceSubClass` | `0` (**not** boot protocol) |
| `bInterfaceProtocol` | `0` (neither keyboard nor mouse) |
| `bNumEndpoints` | `1` |
| `iInterface` | `0` (no string) |
| HID usage page | `0xf0ff` (vendor defined) |
| HID usage | `0x10` |
| Max input report | **3 bytes** |
| Max output report | 0 |
| Max feature report | 0 |
| `ReportInterval` | 1000 us (1 kHz polling interval) |

Report descriptor, 20 bytes, `06fff00910a1000911750895031581257f8102c0`:

```
06 ff f0   Usage Page (vendor defined 0xF0FF)
09 10      Usage (0x10)
a1 00      Collection (Physical)
09 11        Usage (0x11)
75 08        Report Size  (8 bits)
95 03        Report Count (3)          -> 3-byte input report, no report ID
15 81        Logical Minimum (-127)
25 7f        Logical Maximum (127)
81 02        Input (Data, Var, Abs)
c0         End Collection
```

### Interface 1 - the data interface

| Field | Value |
|---|---|
| `bInterfaceNumber` | `1` |
| `bInterfaceClass` | `3` (HID) |
| `bInterfaceSubClass` | `0` (**not** boot protocol) |
| `bInterfaceProtocol` | `0` |
| `bNumEndpoints` | `1` |
| `iInterface` | `4` (has a string descriptor, contents not yet read) |
| HID usage page | `0xffff` (vendor defined) |
| HID usage | `0x02` |
| Max input report | **32 bytes** |
| Max output report | 0 |
| Max feature report | **6 bytes** |
| `ReportInterval` | 1000 us |

Report descriptor, 28 bytes, `06ffff0902a1000903750895201581257f8102090475089506b102c0`:

```
06 ff ff   Usage Page (vendor defined 0xFFFF)
09 02      Usage (0x02)
a1 00      Collection (Physical)
09 03        Usage (0x03)
75 08        Report Size  (8 bits)
95 20        Report Count (32)         -> 32-byte input report, no report ID
15 81        Logical Minimum (-127)
25 7f        Logical Maximum (127)
81 02        Input (Data, Var, Abs)
09 04        Usage (0x04)
75 08        Report Size  (8 bits)
95 06        Report Count (6)          -> 6-byte feature report
b1 02        Feature (Data, Var, Abs)
c0         End Collection
```

Reading of the `15 81` / `25 7f` items: HID logical minimum and maximum are
signed, so `0x81` is -127 and `0x7f` is 127. A -127..127 range on an 8-bit field
is a sloppy vendor way of writing "one byte". It does **not** mean the payload is
signed or that values above 127 cannot occur. We will treat payload bytes as
unsigned octets and let measurement decide.

### What this tells us

- **The 32-byte input report on interface 1 is the data stream.** STRONGLY
  INFERRED. It is the only wide periodic input on the device, and 32 bytes is the
  packet size long reported by community work on the EPOC.
- **There are no output reports at all on either interface.** CONFIRMED from both
  report descriptors (`MaxOutputReportSize = 0`). Any host-to-dongle command
  would therefore have to travel as a **feature report** (interface 1 declares a
  6-byte feature report) or as a raw control transfer. Nothing has been sent.
- **Interface 0's 3-byte report is not yet explained.** UNKNOWN. A dongle link or
  status channel is a reasonable guess but is not evidence.
- **Neither interface is a boot-protocol keyboard or mouse** (`bInterfaceSubClass
  = 0`, `bInterfaceProtocol = 0`, vendor-defined usage pages). CONFIRMED. This
  matters on macOS: it is very likely why opening the device required no Input
  Monitoring permission. STRONGLY INFERRED.

### Access route: HID only, not libusb

Both interfaces report `UsbExclusiveOwner = AppleUserUSBHostHIDDevice`. CONFIRMED.

macOS binds its own HID driver to any HID-class interface and provides no
supported way to detach it. libusb/pyusb therefore **cannot** claim these
interfaces on macOS. The IOKit HID API (via `hidapi`) is the access route, and it
works: the device opened without error and without any TCC permission prompt.
CONFIRMED.

A `Google Chrome` `AppleUSBHostDeviceUserClient` (pid 1433) is also attached at
the *device* level. It does not claim either interface and did not prevent our
HID open. Worth remembering as a variable if behaviour ever changes.

---

## 3. Identity: what is this headset?

### The USB serial `SN20REDACTED0000`

CONFIRMED as the string the dongle reports in `iSerialNumber`.

Structure, STRONGLY INFERRED from its shape alone:

```
SN 2013 08 22 0688 GM
|  |    |  |  |    |
|  |    |  |  |    +-- two-letter suffix, meaning unknown
|  |    |  |  +------- unit / sequence number within the day or batch
|  |    |  +---------- day   (22)
|  |    +------------- month (08)
|  +------------------ year  (2013)
+--------------------- literal "SN"
```

If that reading is right, this dongle was manufactured on or around
**22nd August 2013**. POSSIBLE, not confirmed. The date interpretation is a
pattern match on an eight-digit `YYYYMMDD` field and nothing more. It is
consistent with the classic EPOC production era, which is weak corroboration.

**Why this string matters beyond identification:** community reverse-engineering
work on the EPOC holds that the AES key used to encrypt the wireless payload is
derived from the device serial number. If that is true here, this exact string is
key material and we will need it byte-for-byte. Pending confirmation against
`docs/RESEARCH.md` and, ultimately, against real captured packets. Not yet
verified on this hardware.

### The headset marking `0013374`

The user reports the headset is physically marked `EMOTIV EPOC 0013374`.

- It is **not** the dongle's USB serial. CONFIRMED (they do not match).
- What it actually is: **UNKNOWN**. Candidate readings, none tested:
  - a headset serial or asset number in a different scheme from the dongle's
  - a production/batch number
  - a model or SKU identifier
  - a retailer or institutional asset tag

Do not treat `0013374` as a model number. Resolving this needs either the headset
powered on (so we can see whether it reports its own identity) or a photograph of
the label in context. Open question.

### Which EPOC generation is this?

**Not yet established.** The honest position:

- `21a1:0001` with product string `EPOC BCI`, `bcdDevice 0x0003`, and a 2013-era
  serial is consistent with the **classic EPOC** rather than the later EPOC+ or
  EPOC X. STRONGLY INFERRED, pending the cross-check in `docs/RESEARCH.md`.
- The 32-byte input report is consistent with the classic EPOC packet size
  reported by community work. Corroborating, not decisive.
- We have **not** confirmed channel count, sampling rate, ADC resolution or
  encryption on this device. Those are properties of the radio payload, and we
  have not yet received a single radio payload.

Deciding the generation from the dongle alone would be inference stacked on
inference. It gets settled at Gate 3 and Gate 4, from real packets.

---

## 4. Current state of the headset link

As of 8th August 2026 the receiver is plugged in and fully enumerated, but has
delivered **zero input reports** on either interface across three capture
attempts. See `docs/LAB_NOTES.md` LN-002 and LN-003.

The receiver forwards what it hears over its 2.4 GHz link. With no powered,
paired headset transmitting, silence is the expected result. This is the leading
explanation but it is **not yet proven**, because the discriminating test
(headset switched on) has not been run.

Alternatives not yet excluded:

1. Headset powered off, flat, or out of range. Most likely.
2. The receiver requires an initialisation command before it will stream. We have
   deliberately sent nothing, so this remains open. Note that the absence of any
   output report in the descriptors means such a command could only be a feature
   report or a raw control transfer.
3. Headset and dongle not paired to each other.
4. Reports are being delivered somewhere we are not looking.

Hypothesis 1 is cheap to test and must be ruled out before anything else is tried.
