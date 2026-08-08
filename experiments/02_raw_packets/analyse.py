#!/usr/bin/env python3
"""
Analyse a BDCAP001 capture without interpreting it as EEG.

Answers only structural questions:
  - report length(s)
  - packets per second, inter-packet timing distribution
  - which byte positions change and how much
  - whether any byte behaves like a counter

Usage:
    python analyse.py ../../captures/run001-ffff.bin
"""

import argparse
import collections
import statistics
import sys

from capture import read_capture


def counter_score(col):
    """
    How well does this byte column behave like a free-running counter?
    Returns (score 0..1, description). Checks step-by-1 with wraparound.
    """
    if len(col) < 3:
        return 0.0, "too few samples"
    steps = collections.Counter()
    for a, b in zip(col, col[1:]):
        steps[(b - a) % 256] += 1
    total = sum(steps.values())
    plus_one = steps.get(1, 0) / total
    most, most_n = steps.most_common(1)[0]
    return plus_one, (f"+1 in {plus_one*100:.1f}% of steps; "
                      f"most common step {most} ({most_n/total*100:.1f}%); "
                      f"distinct values {len(set(col))}, "
                      f"range {min(col)}..{max(col)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("capture")
    ap.add_argument("--max-show", type=int, default=8, help="rows of raw hex to show")
    args = ap.parse_args()

    meta, recs = read_capture(args.capture)
    print("=" * 78)
    print(f"Capture: {args.capture}")
    print("=" * 78)
    for k, v in meta.items():
        if k == "device":
            print("  device:")
            for dk, dv in v.items():
                print(f"    {dk:16s}: {dv!r}")
        else:
            print(f"  {k:16s}: {v!r}")
    print()

    if not recs:
        print("NO REPORTS IN THIS CAPTURE.")
        print("This file records the fact that the receiver produced no input reports")
        print("during the capture window. That is itself a result, not a failure of")
        print("the tooling: see docs/LAB_NOTES.md.")
        return 1

    n = len(recs)
    lengths = collections.Counter(len(p) for _, _, p in recs)
    span_s = (recs[-1][0] - recs[0][0]) / 1e9

    print(f"reports          : {n}")
    print(f"report lengths   : {dict(lengths)}")
    print(f"span             : {span_s:.6f} s")
    if span_s > 0:
        print(f"rate             : {(n - 1) / span_s:.3f} reports/sec")

    dts = [(b[0] - a[0]) / 1e6 for a, b in zip(recs, recs[1:])]
    if dts:
        print("\ninter-packet interval (ms)")
        print(f"  mean   : {statistics.fmean(dts):.4f}")
        print(f"  median : {statistics.median(dts):.4f}")
        print(f"  stdev  : {statistics.pstdev(dts):.4f}")
        print(f"  min    : {min(dts):.4f}")
        print(f"  max    : {max(dts):.4f}")
        print(f"  implied sample rate if 1 sample/report : {1000/statistics.fmean(dts):.2f} Hz")
        print(f"  implied sample rate if 2 samples/report: {2000/statistics.fmean(dts):.2f} Hz")

    width = max(lengths)
    print(f"\nper-byte behaviour over {n} reports (width {width})")
    print(f"  {'idx':>3} {'uniq':>5} {'min':>4} {'max':>4} {'mean':>7} "
          f"{'+1 step%':>9}  note")
    cols = []
    for i in range(width):
        col = [p[i] for _, _, p in recs if len(p) > i]
        cols.append(col)
        uniq = len(set(col))
        sc, desc = counter_score(col)
        note = ""
        if uniq == 1:
            note = f"CONSTANT = 0x{col[0]:02x}"
        elif sc > 0.9:
            note = "COUNTER-LIKE (near-monotonic +1)"
        elif sc > 0.5:
            note = "possibly counter-like"
        print(f"  {i:3d} {uniq:5d} {min(col):4d} {max(col):4d} "
              f"{statistics.fmean(col):7.2f} {sc*100:8.1f}%  {note}")

    print("\nfirst reports (hex):")
    for i, (tm, _, p) in enumerate(recs[: args.max_show]):
        print(f"  [{i:3d}] t={tm/1e6:9.3f}ms  {p.hex(' ')}")

    const = [i for i, c in enumerate(cols) if len(set(c)) == 1]
    counters = [i for i, c in enumerate(cols) if counter_score(c)[0] > 0.9]
    print("\nSUMMARY")
    print(f"  constant byte positions : {const}")
    print(f"  counter-like positions  : {counters}")
    print("  (Structural observations only. No field meanings are claimed here.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
