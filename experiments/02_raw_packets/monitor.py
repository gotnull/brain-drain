#!/usr/bin/env python3
"""
Long-running link monitor. Read-only.

Two jobs at once:
  1. Read input reports from interface 1 (the 32-byte data interface) and record
     any that arrive, to a BDCAP001 capture.
  2. Poll interface 1's 6-byte FEATURE report once a second and log every change.

Job 2 is the interesting one while the link is down. GET_FEATURE is a control
READ - it cannot change device state - and it is the only channel that responded
at all when the receiver was silent. If any byte of it changes when the headset
is switched on, powered down, or comes into range, we have found a link-status
field and a cheap way to tell "receiver alive but no headset" from "headset
linked".

Sends no output reports, no SET_FEATURE, no configuration commands.

Usage:
    python monitor.py --seconds 120 --out ../../captures/monitor001
"""

import argparse
import sys
import time

try:
    import hid
except ImportError:
    sys.exit("hidapi not installed")

from capture import CaptureWriter

EMOTIV_VID = 0x21A1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=120.0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--feature-period", type=float, default=1.0)
    args = ap.parse_args()

    devs = [d for d in hid.enumerate() if d["vendor_id"] == EMOTIV_VID]
    data_if = next((d for d in devs if d.get("usage_page") == 0xFFFF), None)
    if data_if is None:
        sys.exit("EMOTIV 0xffff data interface not found")

    dev = hid.device()
    dev.open_path(data_if["path"])
    dev.set_nonblocking(1)

    writer = None
    if args.out:
        writer = CaptureWriter(args.out + ".bin", {
            "capture_format": "BDCAP001",
            "captured_local": time.strftime("%d %B %Y %I:%M%p %Z"),
            "host": "monitor.py long link watch",
            "device": {k: data_if.get(k) for k in
                       ("vendor_id", "product_id", "serial_number",
                        "interface_number", "usage_page")},
            "note": "Read-only link monitor. Feature polling logged separately.",
        })

    print(f"Monitoring for {args.seconds:.0f}s. Input reports + feature polling.")
    print(f"Feature report polled every {args.feature_period:.1f}s; "
          f"only CHANGES are printed.\n")

    t0 = time.perf_counter()
    n = 0
    last_feature = None
    next_poll = 0.0
    try:
        while True:
            el = time.perf_counter() - t0
            if el >= args.seconds:
                break

            data = dev.read(64)
            if data:
                payload = bytes(data)
                if writer:
                    writer.write(int(el * 1e9), time.time_ns(), payload)
                if n < 20:
                    print(f"  INPUT [{n:4d}] t={el:8.3f}s len={len(payload):3d} "
                          f"{payload.hex(' ')}")
                elif n % 128 == 0:
                    print(f"  INPUT [{n:4d}] t={el:8.3f}s "
                          f"(~{n/max(el,1e-9):.1f}/s)")
                n += 1
                continue

            if el >= next_poll:
                next_poll = el + args.feature_period
                try:
                    f = bytes(dev.get_feature_report(0, 8))
                except Exception as e:  # noqa: BLE001
                    f = f"error: {e}".encode()
                if f != last_feature:
                    tag = "initial" if last_feature is None else "CHANGED"
                    print(f"  FEATURE t={el:8.3f}s [{tag}] {f.hex(' ')}")
                    last_feature = f
            time.sleep(0.001)
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        dev.close()
        if writer:
            writer.close()

    el = time.perf_counter() - t0
    print(f"\n{n} input reports in {el:.1f}s")
    if n:
        print(f"rate: {n/el:.2f}/s")
        print("LINK IS UP. Proceed to analyse.py.")
    else:
        print("NO INPUT REPORTS. Receiver enumerated and responds on its control")
        print("path, but the radio delivered nothing for the whole window.")
    return 0 if n else 3


if __name__ == "__main__":
    sys.exit(main())
