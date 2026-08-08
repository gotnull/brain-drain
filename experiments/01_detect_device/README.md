# Experiment 01 - detect the EMOTIV receiver

## What this proves

That our own code, with no EMOTIV software installed or running, can find the
EMOTIV wireless receiver on this machine and read back everything the operating
system knows about it.

This is Gate 1. It proves nothing about EEG, the headset, or the radio protocol.
It only proves the USB receiver exists and is reachable by us.

## What it does

1. Enumerates every HID device via `hidapi`.
2. Flags plausible EMOTIV devices by VID/PID and by manufacturer/product string.
3. Prints VID, PID, manufacturer, product, serial, bcdDevice, interface number,
   HID usage page and usage, and the OS device path.
4. Opens each candidate read-only purely to fetch its HID report descriptor,
   then decodes that descriptor into items.

## Passivity

Read-only. It issues no output reports, no SET_REPORT, no feature writes and no
configuration changes. Fetching a report descriptor is a standard GET_DESCRIPTOR
control read. Use `--no-open` to skip even that and do pure enumeration.

## Run

```sh
../../.venv/bin/python detect.py            # human-readable
../../.venv/bin/python detect.py --json     # machine-readable
../../.venv/bin/python detect.py --no-open  # enumeration only, never opens
```

Exit status is 0 if at least one candidate was found, 1 otherwise.

## Result on this hardware

PASS, 8th August 2026. See [docs/LAB_NOTES.md](../../docs/LAB_NOTES.md) entry
LN-001 and the saved output in [captures/gate1-detect.txt](../../captures/gate1-detect.txt).

Two HID interfaces were found on one physical device, VID `0x21a1`
PID `0x0001`, `Emotiv Systems Inc.` / `EPOC BCI`, USB serial `SN20REDACTED0000`.
