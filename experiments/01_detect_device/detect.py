#!/usr/bin/env python3
"""
Gate 1: prove we can identify the EMOTIV receiver without any EMOTIV software.

Passive only. Enumerates HID devices, flags plausible EMOTIV receivers, and
prints everything the OS will tell us about them. Opens candidate devices
read-only solely to request the HID report descriptor (a GET_DESCRIPTOR control
read - no output reports, no feature writes, no configuration changes).

Usage:
    python detect.py            # enumerate + report
    python detect.py --json     # machine-readable output
    python detect.py --no-open  # skip the report-descriptor read (pure enumeration)
"""

import argparse
import json
import platform
import sys

try:
    import hid
except ImportError:
    sys.exit("hidapi not installed. Run: pip install hidapi")

# Vendor/product IDs historically associated with EMOTIV receivers.
# Sourced from community reverse-engineering projects; treat as candidates to
# check, not as ground truth. Only what we observe on this machine is evidence.
KNOWN_EMOTIV_IDS = {
    (0x21A1, 0x0001): "Emotiv Systems - EPOC / EPOC BCI receiver",
    (0x21A1, 0x0002): "Emotiv Systems - reported EPOC variant",
    (0x1234, 0xED02): "Emotiv EPOC developer/consumer dongle (older reports)",
    (0x1234, 0x0000): "Emotiv (older reports)",
    (0xED02, 0x1234): "byte-swapped report seen in some docs",
}

NAME_HINTS = ("emotiv", "epoc", "insight", "brain")


def looks_like_emotiv(d):
    """Return (is_candidate, reason)."""
    vid, pid = d.get("vendor_id"), d.get("product_id")
    if (vid, pid) in KNOWN_EMOTIV_IDS:
        return True, f"VID/PID matches known list: {KNOWN_EMOTIV_IDS[(vid, pid)]}"
    if vid == 0x21A1:
        return True, "vendor ID 0x21a1 is allocated to Emotiv Systems"
    blob = " ".join(
        str(d.get(k) or "") for k in ("manufacturer_string", "product_string")
    ).lower()
    for hint in NAME_HINTS:
        if hint in blob:
            return True, f"product/manufacturer string contains {hint!r}"
    return False, ""


def report_descriptor(path):
    """Passively read the HID report descriptor. Returns bytes or an error string."""
    dev = hid.device()
    try:
        dev.open_path(path)
    except Exception as e:  # noqa: BLE001
        return f"<could not open: {e}>"
    try:
        get = getattr(dev, "get_report_descriptor", None)
        if get is None:
            return "<hidapi build has no get_report_descriptor>"
        return bytes(get())
    except Exception as e:  # noqa: BLE001
        return f"<descriptor read failed: {e}>"
    finally:
        dev.close()


def decode_report_descriptor(rd):
    """Minimal HID report-descriptor item walker. Enough to see usages and sizes."""
    TYPES = {0: "Main", 1: "Global", 2: "Local"}
    MAIN = {0x8: "Input", 0x9: "Output", 0xA: "Collection",
            0xB: "Feature", 0xC: "End Collection"}
    GLOBAL = {0x0: "Usage Page", 0x1: "Logical Min", 0x2: "Logical Max",
              0x3: "Physical Min", 0x4: "Physical Max", 0x5: "Unit Exponent",
              0x6: "Unit", 0x7: "Report Size", 0x8: "Report ID",
              0x9: "Report Count", 0xA: "Push", 0xB: "Pop"}
    LOCAL = {0x0: "Usage", 0x1: "Usage Min", 0x2: "Usage Max"}
    # Logical/physical extents are signed in the HID spec, so 0x81 means -127,
    # not 129. Everything else is unsigned.
    SIGNED_GLOBAL = {0x1, 0x2, 0x3, 0x4, 0x5}

    lines, i = [], 0
    while i < len(rd):
        b = rd[i]
        size = b & 0x03
        size = 4 if size == 3 else size
        typ = (b >> 2) & 0x03
        tag = (b >> 4) & 0x0F
        data = rd[i + 1: i + 1 + size]
        signed = typ == 1 and tag in SIGNED_GLOBAL
        val = int.from_bytes(data, "little", signed=signed) if data else 0

        if typ == 0:
            name = MAIN.get(tag, f"Main tag {tag:#x}")
        elif typ == 1:
            name = GLOBAL.get(tag, f"Global tag {tag:#x}")
        else:
            name = LOCAL.get(tag, f"Local tag {tag:#x}")

        shown = f"{val}" if signed else f"{val} (0x{val:x})"
        lines.append(f"      {rd[i:i+1+size].hex():<12} {TYPES[typ]:<6} "
                     f"{name:<16} = {shown}")
        i += 1 + size
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--no-open", action="store_true",
                    help="pure enumeration; do not open devices at all")
    args = ap.parse_args()

    devices = hid.enumerate()
    candidates, others = [], []
    for d in devices:
        hit, why = looks_like_emotiv(d)
        (candidates if hit else others).append((d, why))

    if args.json:
        out = []
        for d, why in candidates:
            e = dict(d)
            e["path"] = e["path"].decode(errors="replace")
            e["match_reason"] = why
            if not args.no_open:
                rd = report_descriptor(d["path"])
                e["report_descriptor"] = rd.hex() if isinstance(rd, bytes) else rd
            out.append(e)
        print(json.dumps({"platform": platform.platform(),
                          "hid_device_count": len(devices),
                          "emotiv_candidates": out}, indent=2))
        return 0 if candidates else 1

    print("=" * 78)
    print("Gate 1 - EMOTIV receiver detection (passive, no EMOTIV software)")
    print("=" * 78)
    print(f"Host        : {platform.platform()}")
    print(f"Python      : {platform.python_version()}")
    print(f"hidapi      : {getattr(hid, '__version__', 'unknown')}")
    print(f"HID devices : {len(devices)} enumerated")
    print(f"Candidates  : {len(candidates)}")
    print()

    if not candidates:
        print("NO EMOTIV CANDIDATE FOUND.")
        print("Devices seen:")
        for d, _ in others:
            print(f"  {d['vendor_id']:#06x}:{d['product_id']:#06x} "
                  f"{d.get('manufacturer_string')!r} {d.get('product_string')!r}")
        return 1

    for n, (d, why) in enumerate(candidates, 1):
        print("-" * 78)
        print(f"CANDIDATE {n}: matched because {why}")
        print("-" * 78)
        print(f"  vendor_id        : {d['vendor_id']:#06x}  ({d['vendor_id']})")
        print(f"  product_id       : {d['product_id']:#06x}  ({d['product_id']})")
        print(f"  manufacturer     : {d.get('manufacturer_string')!r}")
        print(f"  product          : {d.get('product_string')!r}")
        print(f"  serial_number    : {d.get('serial_number')!r}")
        print(f"  release_number   : {d.get('release_number')} "
              f"(bcdDevice {d.get('release_number', 0):#06x})")
        print(f"  interface_number : {d.get('interface_number')}")
        print(f"  usage_page       : {d.get('usage_page'):#06x}")
        print(f"  usage            : {d.get('usage'):#06x}")
        print(f"  bus_type         : {d.get('bus_type')}")
        print(f"  path             : {d['path'].decode(errors='replace')}")

        if not args.no_open:
            rd = report_descriptor(d["path"])
            if isinstance(rd, bytes):
                print(f"  report descriptor: {len(rd)} bytes")
                print(f"    raw: {rd.hex()}")
                print("    decoded:")
                for line in decode_report_descriptor(rd):
                    print(line)
            else:
                print(f"  report descriptor: {rd}")
        print()

    print("=" * 78)
    print("RESULT: EMOTIV receiver identified without EMOTIV software. Gate 1 PASS.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
