# Experiment 02 - receive raw reports

## What this proves

That the receiver actually delivers data to us, and what that data looks like
structurally. Nothing is decoded here. The output is bytes and timestamps.

This is Gate 2.

## Passivity

`capture.py` opens the HID interface and only reads. It sends no output
reports, no feature writes, no SET_REPORT and no configuration commands. If the
receiver needs to be nudged into streaming, this program will not do it - that
would be a separate, deliberate, documented experiment.

## Tools

### `capture.py`

Opens an EMOTIV HID interface and records every input report verbatim with two
timestamps: a monotonic clock (for interval maths) and a wall clock (for
correlating with lab notes).

```sh
../../.venv/bin/python capture.py --list
../../.venv/bin/python capture.py --count 100 --out ../../captures/run001
../../.venv/bin/python capture.py --seconds 30 --out ../../captures/run002
../../.venv/bin/python capture.py --usage-page 0xf0ff --count 20 --out ../../captures/run003
```

By default it selects the interface with usage page `0xffff`, which is the one
whose report descriptor declares a 32-byte input report.

Exit status: 0 if any report was captured, 2 if the device could not be opened,
3 if it opened but produced nothing.

### `analyse.py`

Reads a capture back and reports structure only: report lengths, packets per
second, inter-packet interval statistics, per-byte value ranges, which byte
positions are constant, and which behave like a counter.

```sh
../../.venv/bin/python analyse.py ../../captures/run001-ffff.bin
```

## Capture file format (`BDCAP001`)

Deliberately trivial so it can be read by anything later, including a replay
layer that needs no hardware.

```
magic     8 bytes    b"BDCAP001"
meta_len  uint32 LE
meta      meta_len bytes of UTF-8 JSON (host, device identity, timestamps)
records   repeated until EOF:
            uint64 LE  monotonic nanoseconds since capture start
            uint64 LE  wall-clock nanoseconds since the Unix epoch
            uint16 LE  payload length
            payload    exactly the bytes the OS delivered
```

A `.hex` sidecar with the same data in human-readable form is written alongside.
Console output is never the only record.

## Result on this hardware

NOT YET PASSED as of 8th August 2026. The interface opens without error but
delivers zero input reports, on both the `0xffff` and `0xf0ff` interfaces, with
the headset not powered on. See [docs/LAB_NOTES.md](../../docs/LAB_NOTES.md)
entries LN-002 and LN-003.

A capture containing zero records is still a recorded result. `analyse.py`
reports it as such rather than treating it as a tooling failure.
