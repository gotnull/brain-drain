#!/usr/bin/env python3
"""
Gate 4b: extract EEG channels from decrypted packets and test whether they
actually behave like EEG.

The bit table below comes from Emokit (see RESEARCH.md section 3.3). It is a
hypothesis, not an assumption. The test that matters is lag-1 autocorrelation.

Why that test. The EPOC's analogue path is band-limited to roughly 0.16-43 Hz and
sampled at 128 Hz, so consecutive samples of a real channel MUST be highly
correlated: the signal cannot jump arbitrarily between samples. If the bit
mapping is wrong, we are gathering bits from unrelated fields and the result is
effectively noise, giving an autocorrelation near zero. Real channels score above
about 0.9; a wrong mapping scores near 0.

One adaptation for our hardware: Emokit indexes with `bits[i] // 8 + 1` because
it prepends a report-ID byte to make 33 bytes. Our HID interface declares no
report ID and hidapi hands us exactly 32 bytes, so we index with `bits[i] // 8`
and no offset.

Usage:
    python channels.py ../../captures/run007-linked.bin
"""

import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(__file__))
from decode import candidate_keys, decrypt  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "02_raw_packets"))
from capture import read_capture  # noqa: E402

SENSORS_14 = {
    "F3":  [10, 11, 12, 13, 14, 15, 0, 1, 2, 3, 4, 5, 6, 7],
    "FC5": [28, 29, 30, 31, 16, 17, 18, 19, 20, 21, 22, 23, 8, 9],
    "AF3": [46, 47, 32, 33, 34, 35, 36, 37, 38, 39, 24, 25, 26, 27],
    "F7":  [48, 49, 50, 51, 52, 53, 54, 55, 40, 41, 42, 43, 44, 45],
    "T7":  [66, 67, 68, 69, 70, 71, 56, 57, 58, 59, 60, 61, 62, 63],
    "P7":  [84, 85, 86, 87, 72, 73, 74, 75, 76, 77, 78, 79, 64, 65],
    "O1":  [102, 103, 88, 89, 90, 91, 92, 93, 94, 95, 80, 81, 82, 83],
    "O2":  [140, 141, 142, 143, 128, 129, 130, 131, 132, 133, 134, 135, 120, 121],
    "P8":  [158, 159, 144, 145, 146, 147, 148, 149, 150, 151, 136, 137, 138, 139],
    "T8":  [160, 161, 162, 163, 164, 165, 166, 167, 152, 153, 154, 155, 156, 157],
    "F8":  [178, 179, 180, 181, 182, 183, 168, 169, 170, 171, 172, 173, 174, 175],
    "AF4": [196, 197, 198, 199, 184, 185, 186, 187, 188, 189, 190, 191, 176, 177],
    "FC6": [214, 215, 200, 201, 202, 203, 204, 205, 206, 207, 192, 193, 194, 195],
    "F4":  [216, 217, 218, 219, 220, 221, 222, 223, 208, 209, 210, 211, 212, 213],
}
QUALITY_BITS = list(range(99, 113))
UV_PER_LSB = 0.5151515151


def get_level(data, bits):
    """MSB-first gather of 14 bits from scattered positions. No report-id offset."""
    level = 0
    for i in range(len(bits) - 1, -1, -1):
        level <<= 1
        b = bits[i] // 8
        o = bits[i] % 8
        level |= (data[b] >> o) & 1
    return level


def autocorr1(xs):
    """Lag-1 Pearson autocorrelation."""
    n = len(xs)
    if n < 3:
        return 0.0
    m = statistics.fmean(xs)
    num = sum((xs[i] - m) * (xs[i + 1] - m) for i in range(n - 1))
    den = sum((x - m) ** 2 for x in xs)
    return num / den if den else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("capture")
    ap.add_argument("--limit", type=int, default=2000)
    args = ap.parse_args()

    meta, recs = read_capture(args.capture)
    sn = meta["device"]["serial_number"]
    key = candidate_keys(sn)["emokit_consumer (is_research=False)"]
    payloads = [p for _, _, p in recs[: args.limit] if len(p) == 32]
    decoded = [decrypt(p, key) for p in payloads]

    print("=" * 78)
    print("Gate 4b - EEG channel extraction and plausibility")
    print("=" * 78)
    print(f"capture : {args.capture}")
    print(f"packets : {len(decoded)}")
    print(f"key     : {bytes(key).hex()}")
    print()

    series = {name: [get_level(d, bits) for d in decoded]
              for name, bits in SENSORS_14.items()}

    print("Per-channel statistics. Raw is the 14-bit ADC value (0..16383).")
    print("Scaled uses the documented 0.5151 uV/LSB, relative to each channel's")
    print("own mean, so it reads as a signal excursion rather than a DC offset.\n")
    print(f"  {'chan':<5} {'raw mean':>9} {'raw sd':>8} {'min':>6} {'max':>6} "
          f"{'p-p uV':>8} {'lag-1 ac':>9}  verdict")
    print("  " + "-" * 74)

    acs = []
    for name in SENSORS_14:
        xs = series[name]
        ac = autocorr1(xs)
        acs.append(ac)
        sd = statistics.pstdev(xs)
        pp = (max(xs) - min(xs)) * UV_PER_LSB
        verdict = ("EEG-like" if ac > 0.9 else
                   "marginal" if ac > 0.5 else "NOISE-LIKE")
        print(f"  {name:<5} {statistics.fmean(xs):9.1f} {sd:8.2f} "
              f"{min(xs):6d} {max(xs):6d} {pp:8.1f} {ac:9.4f}  {verdict}")

    good = sum(1 for a in acs if a > 0.9)
    print(f"\n  {good}/14 channels have lag-1 autocorrelation above 0.9")

    counters = [d[0] for d in decoded]
    quality = [get_level(d, QUALITY_BITS) for d in decoded]
    print("\ncontact quality (multiplexed by counter, one electrode per packet):")
    print(f"  raw range {min(quality)}..{max(quality)}, "
          f"mean {statistics.fmean(quality):.1f}")

    per_electrode = {}
    order = list(SENSORS_14.keys())
    for c, q in zip(counters, quality):
        if c < 128:
            per_electrode.setdefault(c % 16, []).append(q)
    print("  by counter slot (slot -> mean raw quality, n):")
    for slot in sorted(per_electrode):
        vs = per_electrode[slot]
        print(f"    slot {slot:2d}: {statistics.fmean(vs):8.1f}  (n={len(vs)})")

    print("\nBattery:")
    batt = [d[0] for d in decoded if d[0] >= 128]
    if batt:
        raw = statistics.mode(batt)
        table = {255: 100, 254: 100, 253: 100, 252: 100, 251: 100, 250: 100,
                 249: 100, 248: 100, 247: 99, 246: 97, 245: 93, 244: 89,
                 243: 85, 242: 82, 241: 77, 240: 72, 239: 66, 238: 62,
                 237: 55, 236: 46, 235: 32, 234: 20, 233: 12, 232: 6,
                 231: 4, 230: 3, 229: 2, 228: 2, 227: 2, 226: 1, 225: 0, 224: 0}
        print(f"  raw {raw} -> approximately {table.get(raw, '?')}% "
              f"(Emokit lookup table, empirical)")
    else:
        print("  no battery packet in this window")

    print("\n" + "=" * 78)
    if good >= 12:
        print("VERDICT: channels behave like band-limited physiological signals.")
        print("The bit mapping is consistent with this hardware. Gate 4 PASS.")
    else:
        print("VERDICT: too few channels look EEG-like. The bit mapping is")
        print("probably wrong for this hardware revision. Gate 4 NOT passed.")
    print("=" * 78)
    return 0 if good >= 12 else 1


if __name__ == "__main__":
    sys.exit(main())
