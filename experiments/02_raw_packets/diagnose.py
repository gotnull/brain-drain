#!/usr/bin/env python3
"""
Diagnose why the EMOTIV receiver opens successfully but delivers no reports.

Three questions, in order:

  Q1. Does our HID read path work at all on this machine?
      Control: try to read from other USB HID devices. If some device yields
      reports and the EMOTIV does not, the read path is fine and the problem
      is upstream of USB (the radio link or the headset).

  Q2. Does the EMOTIV device respond on its control path?
      Probe: GET_FEATURE on interface 1's declared 6-byte feature report.
      This is a READ (control IN). It sends no data to configure anything and
      cannot change device state. It is the only non-passive-looking thing here
      and it is deliberately limited to a read.

  Q3. Does either interface produce anything over a longer window, when polled
      simultaneously rather than one at a time?

Still sends: no output reports, no SET_REPORT/SET_FEATURE, no configuration
changes, no firmware interaction.
"""

import sys
import threading
import time

try:
    import hid
except ImportError:
    sys.exit("hidapi not installed")

EMOTIV_VID = 0x21A1


def q1_control(seconds=6.0):
    print("=" * 78)
    print("Q1  Control experiment: does our HID read path work on ANY device?")
    print("=" * 78)
    print(f"    Polling every non-EMOTIV USB HID device for {seconds:.0f}s total.")
    print("    (Move the mouse / type if you want a guaranteed positive control.)\n")

    targets = [d for d in hid.enumerate()
               if d["vendor_id"] != EMOTIV_VID and d.get("bus_type") == 1]
    results = {}
    handles = []
    for d in targets:
        label = (f"{d['vendor_id']:#06x}:{d['product_id']:#06x} "
                 f"if{d.get('interface_number')} "
                 f"up={d.get('usage_page'):#06x} "
                 f"{(d.get('product_string') or '?')[:34]}")
        dev = hid.device()
        try:
            dev.open_path(d["path"])
            dev.set_nonblocking(1)
            handles.append((label, dev))
            results[label] = 0
        except Exception as e:  # noqa: BLE001
            results[label] = f"OPEN FAILED: {type(e).__name__}: {e}"

    t_end = time.perf_counter() + seconds
    while time.perf_counter() < t_end:
        for label, dev in handles:
            try:
                data = dev.read(64)
            except Exception:  # noqa: BLE001
                continue
            if data:
                results[label] += 1
        time.sleep(0.002)
    for _, dev in handles:
        dev.close()

    any_data = False
    for label, r in sorted(results.items()):
        if isinstance(r, int):
            mark = "DATA" if r else "silent"
            if r:
                any_data = True
            print(f"    [{mark:>6}] {label}  reports={r}")
        else:
            print(f"    [ERROR ] {label}  {r}")
    print()
    if any_data:
        print("    VERDICT: read path WORKS. At least one HID device delivered")
        print("             reports through the same code path. If EMOTIV stays")
        print("             silent, the fault is the radio link or the headset,")
        print("             NOT our software.")
    else:
        print("    VERDICT: INCONCLUSIVE. No control device produced reports")
        print("             either. That may just mean nothing was moving.")
        print("             Re-run while typing or moving the mouse.")
    print()
    return any_data


def q2_feature():
    print("=" * 78)
    print("Q2  Control-path probe: GET_FEATURE (read-only) on the EMOTIV")
    print("=" * 78)
    devs = [d for d in hid.enumerate() if d["vendor_id"] == EMOTIV_VID]
    for d in devs:
        up = d.get("usage_page")
        dev = hid.device()
        try:
            dev.open_path(d["path"])
        except Exception as e:  # noqa: BLE001
            print(f"    if{d.get('interface_number')} up={up:#06x}: open failed: {e}")
            continue
        for rid in (0, 1):
            try:
                got = dev.get_feature_report(rid, 8)
                print(f"    if{d.get('interface_number')} up={up:#06x} "
                      f"GET_FEATURE(id={rid}) -> {bytes(got).hex(' ') if got else '<empty>'}")
            except Exception as e:  # noqa: BLE001
                print(f"    if{d.get('interface_number')} up={up:#06x} "
                      f"GET_FEATURE(id={rid}) -> error: {e}")
        dev.close()
    print()


def q3_both(seconds=20.0):
    print("=" * 78)
    print(f"Q3  Poll BOTH EMOTIV interfaces simultaneously for {seconds:.0f}s")
    print("=" * 78)
    devs = [d for d in hid.enumerate() if d["vendor_id"] == EMOTIV_VID]
    counts = {}
    firsts = {}
    stop = threading.Event()

    def worker(d):
        key = f"if{d.get('interface_number')} up={d.get('usage_page'):#06x}"
        counts[key] = 0
        dev = hid.device()
        try:
            dev.open_path(d["path"])
        except Exception as e:  # noqa: BLE001
            counts[key] = f"open failed: {e}"
            return
        dev.set_nonblocking(1)
        while not stop.is_set():
            try:
                data = dev.read(64)
            except Exception:  # noqa: BLE001
                break
            if data:
                counts[key] += 1
                firsts.setdefault(key, bytes(data).hex(" "))
            else:
                time.sleep(0.001)
        dev.close()

    threads = [threading.Thread(target=worker, args=(d,), daemon=True) for d in devs]
    for t in threads:
        t.start()
    time.sleep(seconds)
    stop.set()
    for t in threads:
        t.join(timeout=2)

    for k, v in sorted(counts.items()):
        print(f"    {k}: {v} reports"
              + (f"   first={firsts[k]}" if k in firsts else ""))
    print()
    return any(isinstance(v, int) and v > 0 for v in counts.values())


if __name__ == "__main__":
    print()
    ctrl = q1_control()
    q2_feature()
    got = q3_both()
    print("=" * 78)
    print("OVERALL")
    print("=" * 78)
    print(f"  control device produced data : {ctrl}")
    print(f"  EMOTIV produced data         : {got}")
    if ctrl and not got:
        print("\n  The software path is proven good and the EMOTIV receiver is")
        print("  silent. The gap is between the headset and the receiver:")
        print("    - headset battery flat (most likely for 2013-era hardware)")
        print("    - headset not paired to THIS receiver")
        print("    - receiver needs an initialisation command we have not sent")
    elif not ctrl and not got:
        print("\n  Inconclusive: no device produced data. Re-run while using the")
        print("  keyboard or mouse to get a real positive control.")
