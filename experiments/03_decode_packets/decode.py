#!/usr/bin/env python3
"""
Gate 4: find the AES key for THIS receiver and decode packets.

We do not trust any single community implementation. RESEARCH.md section 4.1
documents that Emokit, python-emotiv and CyKit contradict each other on the key
byte layout, and that they use the words "consumer" and "research" to mean
different things. So we generate every documented candidate, decrypt with each,
and let the data pick the winner.

The discriminator is the packet counter. In a correctly decrypted classic EPOC
stream, byte 0 carries a counter whose low 7 bits advance by one, modulo 128,
every packet, with occasional packets where the high bit is set (battery). Random
bytes will not do that. It is a very sharp test: a wrong key scores near 0.8%,
a right key scores near 100%.

Usage:
    python decode.py ../../captures/run007-linked.bin
"""

import argparse
import collections
import os
import sys

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "02_raw_packets"))
from capture import read_capture  # noqa: E402


def candidate_keys(sn):
    """Every documented key layout, built from the last four serial characters."""
    s1, s2, s3, s4 = (ord(sn[-1]), ord(sn[-2]), ord(sn[-3]), ord(sn[-4]))
    H, T, B, P = 0x48, 0x54, 0x42, 0x50
    D, X = 0x44, 0x58
    return {
        "emokit_consumer (is_research=False)":
            [s1, 0x00, s2, T, s3, 0x10, s4, B, s1, 0x00, s2, H, s3, 0x00, s4, P],
        "emokit_research (is_research=True)":
            [s1, 0x00, s2, H, s1, 0x00, s2, T, s3, 0x10, s4, B, s3, 0x00, s4, P],
        "pyemotiv_consumer":
            [s1, 0x00, s2, H, s3, 0x00, s4, T, s1, 0x10, s2, B, s3, 0x00, s4, P],
        "emokit_new_crypto_key":
            [s1, s2, s2, s3, s3, s3, s2, s4, s1, s4, s2, s2, s4, s4, s2, s1],
        "emokit_epoc_plus":
            [s1, 0x00, s2, 0x15, s3, 0x00, s4, 0x0C, s3, 0x00, s2, D, s1, 0x00, s2, X],
    }


def decrypt(payload, key):
    """Classic EPOC: two independent AES-128-ECB blocks, no IV, no chaining."""
    dec = Cipher(algorithms.AES(bytes(key)), __import__(
        "cryptography.hazmat.primitives.ciphers.modes",
        fromlist=["ECB"]).ECB()).decryptor()
    return dec.update(payload[:16]) + dec.update(payload[16:]) + dec.finalize()


def counter_score(decoded):
    """
    Fraction of consecutive packets whose byte 0 low-7-bits advance by exactly
    one modulo 128. Packets with the high bit set are the battery packet and are
    allowed to break the run.

    Only pairs where BOTH bytes are below 128 are scored. Battery packets are
    skipped rather than counted as successes: counting them as good would credit
    random data for every byte that happens to have its high bit set, which
    inflates the baseline to about 50% and hides how sharp this test really is.
    """
    good = total = 0
    for a, b in zip(decoded, decoded[1:]):
        c0, c1 = a[0], b[0]
        if c0 >= 128 or c1 >= 128:
            continue
        total += 1
        if (c0 + 1) % 128 == c1:
            good += 1
    return good / total if total else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("capture")
    ap.add_argument("--limit", type=int, default=1000)
    args = ap.parse_args()

    meta, recs = read_capture(args.capture)
    sn = meta["device"]["serial_number"]
    payloads = [p for _, _, p in recs[: args.limit] if len(p) == 32]

    print("=" * 78)
    print("Gate 4 - AES key search against real packets")
    print("=" * 78)
    print(f"capture      : {args.capture}")
    print(f"packets used : {len(payloads)} (32-byte)")
    print(f"serial       : {sn!r}")
    print(f"key chars    : sn[-1]={sn[-1]!r} sn[-2]={sn[-2]!r} "
          f"sn[-3]={sn[-3]!r} sn[-4]={sn[-4]!r}")
    print()

    baseline = counter_score(payloads)
    print(f"baseline (undecrypted, expect near zero) : {baseline*100:6.2f}%")
    print()
    print(f"  {'candidate key layout':<38} {'key (hex)':<34} {'counter':>8}")
    print("  " + "-" * 82)

    results = []
    for name, key in candidate_keys(sn).items():
        decoded = [decrypt(p, key) for p in payloads]
        sc = counter_score(decoded)
        results.append((sc, name, key, decoded))
        print(f"  {name:<38} {bytes(key).hex():<34} {sc*100:7.2f}%")

    results.sort(reverse=True, key=lambda r: r[0])
    best_score, best_name, best_key, best_decoded = results[0]

    print()
    if best_score < 0.9:
        print("NO CANDIDATE KEY WORKS.")
        print(f"Best was {best_name} at {best_score*100:.2f}%, which is not a")
        print("counter. This dongle revision may differ from everything documented.")
        return 1

    print("=" * 78)
    print(f"WINNER: {best_name}")
    print(f"        key = {bytes(best_key).hex()}")
    print(f"        counter consistency = {best_score*100:.2f}%")
    print("=" * 78)
    print()

    counters = [d[0] for d in best_decoded]
    battery = [c for c in counters if c >= 128]
    print(f"counter values seen : min={min(counters)} max={max(counters)}")
    print(f"battery packets     : {len(battery)} of {len(counters)}"
          f"  ({len(battery)/len(counters)*100:.2f}%)")
    if battery:
        print(f"battery raw bytes   : {sorted(collections.Counter(battery).items())}")

    print("\nfirst 16 decrypted packets (hex), counter is byte 0:")
    for i, d in enumerate(best_decoded[:16]):
        print(f"  [{i:3d}] c={d[0]:3d}  {d.hex(' ')}")

    print("\nfirst 40 counter values:")
    print("  " + " ".join(f"{c:3d}" for c in counters[:40]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
