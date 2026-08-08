#!/usr/bin/env python3
"""
Find the real sample packing on THIS hardware, empirically.

The Emokit bit table produced 0/14 EEG-like channels here, so this dongle
revision packs its samples differently. Rather than guess another table, scan
every plausible field position and let the autocorrelation say where the real
channels are.

Method. A genuine EEG channel is band-limited to about 43 Hz and sampled at
128 Hz, so consecutive samples must be strongly correlated. A field that is not
a channel (crypto residue, misaligned bits, a flag byte) will not be. So: slide
a candidate field across every bit offset in the packet, extract the series,
and score its lag-1 autocorrelation. Real channels appear as sharp peaks.

This makes no assumption about field order, channel names, or where the payload
starts. It only assumes samples are contiguous fixed-width integers somewhere.

Usage:
    python scan_layout.py ../../captures/run007-linked.bin
"""

import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(__file__))
from decode import candidate_keys, decrypt  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "02_raw_packets"))
from capture import read_capture  # noqa: E402


def bits_of(packet):
    """Packet as a list of 256 bits, MSB-first within each byte."""
    out = []
    for byte in packet:
        for k in range(7, -1, -1):
            out.append((byte >> k) & 1)
    return out


def field(bitrows, start, width, msb_first=True):
    """Extract a contiguous field at a bit offset from every packet."""
    vals = []
    rng = range(start, start + width) if msb_first else \
        range(start + width - 1, start - 1, -1)
    for row in bitrows:
        v = 0
        for i in rng:
            v = (v << 1) | row[i]
        vals.append(v)
    return vals


def autocorr1(xs):
    n = len(xs)
    m = statistics.fmean(xs)
    den = sum((x - m) ** 2 for x in xs)
    if den == 0:
        return 0.0
    num = sum((xs[i] - m) * (xs[i + 1] - m) for i in range(n - 1))
    return num / den


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("capture")
    ap.add_argument("--limit", type=int, default=1500)
    ap.add_argument("--width", type=int, default=None,
                    help="only scan this field width")
    ap.add_argument("--threshold", type=float, default=0.90)
    args = ap.parse_args()

    meta, recs = read_capture(args.capture)
    sn = meta["device"]["serial_number"]
    key = candidate_keys(sn)["emokit_consumer (is_research=False)"]
    packets = [decrypt(p, key) for _, _, p in recs[: args.limit] if len(p) == 32]
    # Drop battery packets: their byte 0 differs in kind and would add a
    # spurious discontinuity to every field that overlaps it.
    packets = [p for p in packets if p[0] < 128]
    bitrows = [bits_of(p) for p in packets]

    print("=" * 78)
    print("Empirical field scan")
    print("=" * 78)
    print(f"capture : {args.capture}")
    print(f"packets : {len(packets)} (battery packets excluded)")
    print(f"looking for contiguous fields whose lag-1 autocorrelation "
          f"exceeds {args.threshold}\n")

    widths = [args.width] if args.width else [16, 14, 12]
    for width in widths:
        print(f"--- field width {width} bits ---")
        hits = []
        for msb in (True, False):
            for start in range(0, 256 - width + 1):
                vals = field(bitrows, start, width, msb)
                if len(set(vals)) < 8:
                    continue          # constant or near-constant, not a channel
                ac = autocorr1(vals)
                if ac > args.threshold:
                    hits.append((start, msb, ac, vals))
        if not hits:
            print("  no fields above threshold\n")
            continue

        # Keep the best-scoring representative of each overlapping cluster, so a
        # real channel is reported once rather than as a smear of near-hits.
        hits.sort(key=lambda h: -h[2])
        chosen = []
        for h in hits:
            if all(abs(h[0] - c[0]) >= width or h[1] != c[1] for c in chosen):
                chosen.append(h)
        chosen.sort(key=lambda h: h[0])

        print(f"  {len(chosen)} distinct field(s):")
        print(f"    {'bit':>4} {'byte.bit':>9} {'order':>5} {'ac':>7} "
              f"{'mean':>9} {'sd':>8} {'min':>6} {'max':>6}")
        for start, msb, ac, vals in chosen:
            print(f"    {start:4d} {start//8:5d}.{start%8:<3d} "
                  f"{'MSB' if msb else 'LSB':>5} {ac:7.4f} "
                  f"{statistics.fmean(vals):9.1f} {statistics.pstdev(vals):8.2f} "
                  f"{min(vals):6d} {max(vals):6d}")
        if len(chosen) > 1:
            deltas = [chosen[i+1][0] - chosen[i][0] for i in range(len(chosen)-1)]
            print(f"    spacing between consecutive fields: {deltas}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
