#!/usr/bin/env python3
"""
Gate 2: receive raw reports from the EMOTIV receiver and record them verbatim.

Strictly passive. Opens the HID interface read-only and reads incoming input
reports. Sends nothing: no output reports, no feature writes, no SET_REPORT,
no configuration changes.

Nothing here interprets the bytes. Decoding is a later gate.

Usage:
    python capture.py --count 100 --out ../../captures/run001
    python capture.py --seconds 10 --out ../../captures/run002
    python capture.py --list                 # show selectable interfaces
"""

import argparse
import json
import os
import platform
import struct
import sys
import time

try:
    import hid
except ImportError:
    sys.exit("hidapi not installed. Run: pip install hidapi")

EMOTIV_VID = 0x21A1
MAGIC = b"BDCAP001"          # brain-drain capture, format v1


def find_interfaces(vid=EMOTIV_VID):
    return [d for d in hid.enumerate() if d["vendor_id"] == vid]


def pick_data_interface(devs):
    """The 32-byte input-report interface is the data stream. Prefer it."""
    for d in devs:
        if d.get("usage_page") == 0xFFFF:
            return d
    return devs[0] if devs else None


class CaptureWriter:
    """
    Binary capture container.

      magic     8 bytes   b"BDCAP001"
      meta_len  uint32 LE
      meta      meta_len bytes of UTF-8 JSON
      records   repeated:
                  uint64 LE  monotonic nanoseconds since capture start
                  uint64 LE  wall-clock nanoseconds since Unix epoch
                  uint16 LE  payload length
                  payload    length bytes, exactly as delivered by the OS
    """

    REC = struct.Struct("<QQH")

    def __init__(self, path, meta):
        self.f = open(path, "wb")
        blob = json.dumps(meta, indent=2).encode()
        self.f.write(MAGIC)
        self.f.write(struct.pack("<I", len(blob)))
        self.f.write(blob)

    def write(self, t_mono_ns, t_wall_ns, payload):
        self.f.write(self.REC.pack(t_mono_ns, t_wall_ns, len(payload)))
        self.f.write(payload)
        # Flush every record: a capture that dies to Ctrl-C or SIGTERM must
        # still contain everything it saw. At ~128 reports/sec this is free.
        self.f.flush()

    def close(self):
        self.f.close()


def read_capture(path):
    """Read back a capture file. Returns (meta, [(t_mono_ns, t_wall_ns, payload)])."""
    with open(path, "rb") as f:
        if f.read(8) != MAGIC:
            raise ValueError(f"{path}: not a BDCAP001 capture")
        (mlen,) = struct.unpack("<I", f.read(4))
        meta = json.loads(f.read(mlen))
        recs = []
        while True:
            head = f.read(CaptureWriter.REC.size)
            if len(head) < CaptureWriter.REC.size:
                break
            tm, tw, n = CaptureWriter.REC.unpack(head)
            recs.append((tm, tw, f.read(n)))
    return meta, recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="list EMOTIV HID interfaces and exit")
    ap.add_argument("--count", type=int, default=100, help="stop after N reports")
    ap.add_argument("--seconds", type=float, default=None, help="stop after N seconds instead")
    ap.add_argument("--out", default=None, help="output basename (writes .bin and .hex)")
    ap.add_argument("--usage-page", type=lambda s: int(s, 0), default=None,
                    help="select interface by usage page, e.g. 0xffff or 0xf0ff")
    ap.add_argument("--timeout", type=int, default=2000, help="per-read timeout in ms")
    ap.add_argument("--idle-give-up", type=float, default=10.0,
                    help="abort if no report arrives within this many seconds")
    args = ap.parse_args()

    devs = find_interfaces()
    if not devs:
        sys.exit("No EMOTIV device (VID 0x21a1) found. Is the dongle plugged in?")

    if args.list:
        for d in devs:
            print(f"interface={d.get('interface_number')} "
                  f"usage_page={d.get('usage_page'):#06x} usage={d.get('usage'):#06x} "
                  f"path={d['path'].decode(errors='replace')} "
                  f"serial={d.get('serial_number')!r}")
        return 0

    if args.usage_page is not None:
        sel = [d for d in devs if d.get("usage_page") == args.usage_page]
        if not sel:
            sys.exit(f"No EMOTIV interface with usage page {args.usage_page:#06x}")
        dev_info = sel[0]
    else:
        dev_info = pick_data_interface(devs)

    print(f"Opening: VID {dev_info['vendor_id']:#06x} PID {dev_info['product_id']:#06x} "
          f"interface {dev_info.get('interface_number')} "
          f"usage_page {dev_info.get('usage_page'):#06x} "
          f"serial {dev_info.get('serial_number')!r}")

    dev = hid.device()
    try:
        dev.open_path(dev_info["path"])
    except Exception as e:  # noqa: BLE001
        print(f"\nFAILED TO OPEN: {e}", file=sys.stderr)
        print("\nDiagnosis hints:", file=sys.stderr)
        print("  - macOS may require Input Monitoring permission for the terminal app", file=sys.stderr)
        print("    (System Settings > Privacy & Security > Input Monitoring).", file=sys.stderr)
        print("  - Another process may hold the device open (EMOTIV software, a browser", file=sys.stderr)
        print("    tab using WebHID/WebUSB, etc).", file=sys.stderr)
        return 2

    dev.set_nonblocking(0)  # blocking reads, bounded by --timeout

    meta = {
        "capture_format": "BDCAP001",
        "captured_local": time.strftime("%d %B %Y %I:%M%p %Z"),
        "captured_unix": time.time(),
        "host": platform.platform(),
        "python": platform.python_version(),
        "hidapi": getattr(hid, "__version__", "unknown"),
        "device": {
            "vendor_id": dev_info["vendor_id"],
            "product_id": dev_info["product_id"],
            "manufacturer": dev_info.get("manufacturer_string"),
            "product": dev_info.get("product_string"),
            "serial_number": dev_info.get("serial_number"),
            "release_number": dev_info.get("release_number"),
            "interface_number": dev_info.get("interface_number"),
            "usage_page": dev_info.get("usage_page"),
            "usage": dev_info.get("usage"),
        },
        "note": "Raw HID input reports, uninterpreted. Read-only session.",
    }

    writer = None
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        writer = CaptureWriter(args.out + ".bin", meta)
        hexf = open(args.out + ".hex", "w")
        hexf.write(f"# {json.dumps(meta)}\n")
        hexf.write("# idx  t_mono_ms   dt_ms   len  payload\n")
    else:
        hexf = None

    print(f"Reading (timeout {args.timeout} ms, give up after "
          f"{args.idle_give_up}s of silence)...\n")

    t0 = time.perf_counter_ns()
    last = None
    n = 0
    idle_start = time.perf_counter()
    try:
        while True:
            if args.seconds is not None:
                if (time.perf_counter_ns() - t0) / 1e9 >= args.seconds:
                    break
            elif n >= args.count:
                break

            data = dev.read(64, timeout_ms=args.timeout)
            t = time.perf_counter_ns()
            if not data:
                if time.perf_counter() - idle_start > args.idle_give_up:
                    print(f"\nNo reports for {args.idle_give_up}s - giving up.")
                    break
                continue

            idle_start = time.perf_counter()
            payload = bytes(data)
            tm = t - t0
            tw = time.time_ns()
            if writer:
                writer.write(tm, tw, payload)
            dt = "" if last is None else f"{(tm - last)/1e6:8.3f}"
            last = tm
            if hexf:
                hexf.write(f"{n:5d} {tm/1e6:11.3f} {dt:>8} {len(payload):4d}  "
                           f"{payload.hex(' ')}\n")
            if n < 12 or n % 50 == 0:
                print(f"[{n:4d}] t={tm/1e6:10.3f}ms dt={dt:>8} len={len(payload):3d} "
                      f"{payload.hex(' ')}")
            n += 1
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        dev.close()
        if writer:
            writer.close()
        if hexf:
            hexf.close()

    dur = (time.perf_counter_ns() - t0) / 1e9
    print(f"\n{n} reports in {dur:.3f}s", end="")
    if n and dur > 0:
        print(f"  ({n/dur:.2f} reports/sec)")
    else:
        print()
    if args.out:
        print(f"Wrote {args.out}.bin and {args.out}.hex")
    return 0 if n else 3


if __name__ == "__main__":
    sys.exit(main())
