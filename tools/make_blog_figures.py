#!/usr/bin/env python3
"""
Render figures for the blog from real capture data. No synthetic numbers.

Every value plotted here is read out of a BDCAP001 capture recorded from the
physical receiver. Colours match the blog theme so the figures sit on the dark
page without a white slab around them.

Text must never overlap other text, and a legend must never sit on top of a data
point. That is enforced by assert_layout_is_clean(), which measures the rendered
bounding boxes and raises if anything collides. Eyeballing a figure does not
scale and does not survive a data change; a failing assertion does.

Usage:
    python tools/make_blog_figures.py <capture.bin> <output_dir>
"""

import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.legend import Legend  # noqa: E402
from matplotlib.text import Text  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "experiments", "02_raw_packets"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "experiments", "03_decode_packets"))
from capture import read_capture      # noqa: E402
from decode import candidate_keys, decrypt, counter_score  # noqa: E402

BG = "#15171c"
FG = "#f2f3f5"
MUTED = "#888f9c"
GRID = "#2e333d"
ACCENT = "#e8a13c"
ACCENT2 = "#5ec8c8"
ACCENT3 = "#d4754a"

# Minimum clear space between any two pieces of text, in points.
TEXT_PAD_PT = 2.0


def _boxes(fig):
    """Rendered bounding boxes of every visible text artist and legend."""
    r = fig.canvas.get_renderer()
    out = []
    for ax in fig.axes:
        artists = [ax.title, ax.xaxis.label, ax.yaxis.label]
        artists += ax.get_xticklabels() + ax.get_yticklabels()
        artists += [c for c in ax.get_children()
                    if isinstance(c, Text) and c not in artists]
        for a in artists:
            if not a.get_visible() or not a.get_text().strip():
                continue
            try:
                out.append((f"{type(a).__name__}:{a.get_text()[:30]!r}",
                            a.get_window_extent(renderer=r)))
            except Exception:  # noqa: BLE001
                pass
        leg = ax.get_legend()
        if leg is not None and leg.get_visible():
            out.append(("legend", leg.get_window_extent(renderer=r)))
    return out


def assert_layout_is_clean(fig, name):
    """
    Fail loudly if any two text boxes overlap, or if a legend covers a data
    point. Non-negotiable: a figure that ships must be readable.
    """
    fig.canvas.draw()
    boxes = _boxes(fig)

    problems = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            (n1, b1), (n2, b2) = boxes[i], boxes[j]
            pad = TEXT_PAD_PT
            if (b1.x0 - pad < b2.x1 and b2.x0 - pad < b1.x1
                    and b1.y0 - pad < b2.y1 and b2.y0 - pad < b1.y1):
                problems.append(f"text overlaps text: {n1} vs {n2}")

    r = fig.canvas.get_renderer()
    for ax in fig.axes:
        leg = ax.get_legend()
        if leg is None or not leg.get_visible():
            continue
        lb = leg.get_window_extent(renderer=r)
        for line in ax.get_lines():
            xd, yd = line.get_data()
            for x, y in zip(xd, yd):
                px, py = ax.transData.transform((x, y))
                if lb.x0 <= px <= lb.x1 and lb.y0 <= py <= lb.y1:
                    problems.append(
                        f"legend covers a data point at ({x:.6g}, {y:.6g})")
                    break
            else:
                continue
            break

    if problems:
        raise SystemExit(f"FIGURE LAYOUT FAILED for {name}:\n  "
                         + "\n  ".join(problems))
    print(f"  layout clean: {len(boxes)} text boxes, no overlaps")


def style(ax):
    ax.set_facecolor(BG)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.xaxis.label.set_color(MUTED)
    ax.yaxis.label.set_color(MUTED)
    ax.title.set_color(FG)
    ax.grid(True, color=GRID, linewidth=0.6, alpha=0.6)
    ax.set_axisbelow(True)


def fig_counter(payloads, decoded, out):
    """Byte 0 before and after decryption. The whole story in one picture."""
    n = 300
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 5.8), sharex=True)
    fig.patch.set_facecolor(BG)

    a1.plot(range(n), [p[0] for p in payloads[:n]], ".", color=ACCENT3,
            markersize=3.4)
    a1.set_title("Byte 0 of each packet, as it arrives over USB", fontsize=11,
                 loc="left", pad=9)
    a1.set_ylabel("value")
    a1.set_ylim(-12, 268)
    style(a1)

    c = [d[0] for d in decoded[:n]]
    a2.plot(range(n), c, ".", color=ACCENT2, markersize=3.4)
    batt = [(i, v) for i, v in enumerate(c) if v >= 128]
    if batt:
        a2.plot([i for i, _ in batt], [v for _, v in batt], "o",
                color=ACCENT, markersize=6, markerfacecolor="none",
                markeredgewidth=1.4)
        # Annotate in known-empty space above the ramp and left of the first
        # battery marker, rather than a legend that could land on the data.
        bx, by = batt[0]
        a2.annotate(f"battery packet, raw {by}",
                    xy=(bx, by), xytext=(bx + 26, by - 74),
                    color=ACCENT, fontsize=9,
                    arrowprops=dict(arrowstyle="-", color=ACCENT, lw=1.0))
    a2.set_title("The same byte after AES-128-ECB decryption", fontsize=11,
                 loc="left", pad=9)
    a2.set_ylabel("value")
    a2.set_xlabel("packet number")
    a2.set_ylim(-12, 300)
    style(a2)

    fig.tight_layout(pad=1.4, h_pad=2.2)
    assert_layout_is_clean(fig, os.path.basename(out))
    fig.savefig(out, dpi=170, facecolor=BG)
    print("wrote", out)


def fig_keys(payloads, sn, out):
    """Every documented key layout, scored against the same real packets."""
    scores, labels = [], []
    for name, key in candidate_keys(sn).items():
        scores.append(counter_score([decrypt(p, key) for p in payloads]) * 100)
        labels.append(name.split(" (")[0].replace("_", " "))
    scores.append(counter_score(payloads) * 100)
    labels.append("no decryption")

    order = sorted(range(len(scores)), key=lambda i: scores[i])
    scores = [scores[i] for i in order]
    labels = [labels[i] for i in order]

    fig, ax = plt.subplots(figsize=(9, 3.8))
    fig.patch.set_facecolor(BG)
    colours = [ACCENT if s > 90 else MUTED for s in scores]
    bars = ax.barh(labels, scores, color=colours, height=0.6)
    # Headroom so the widest value label cannot reach the right spine.
    ax.set_xlim(0, 124)
    for b, s in zip(bars, scores):
        ax.text(s + 2.5, b.get_y() + b.get_height() / 2, f"{s:.2f}%",
                va="center", ha="left", fontsize=9,
                color=FG if s > 90 else MUTED)
    ax.set_xlabel("packets whose counter advances by exactly one (percent)")
    ax.set_title("Five documented key layouts, scored on 1000 real packets",
                 fontsize=11, loc="left", pad=9)
    style(ax)
    ax.grid(axis="y", visible=False)
    fig.tight_layout(pad=1.4)
    assert_layout_is_clean(fig, os.path.basename(out))
    fig.savefig(out, dpi=170, facecolor=BG)
    print("wrote", out)


def main():
    cap, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    meta, recs = read_capture(cap)
    sn = meta["device"]["serial_number"]
    payloads = [p for _, _, p in recs if len(p) == 32][:1000]
    key = candidate_keys(sn)["emokit_consumer (is_research=False)"]
    decoded = [decrypt(p, key) for p in payloads]

    fig_counter(payloads, decoded, os.path.join(outdir, "epoc-counter-emerges.png"))
    fig_keys(payloads, sn, os.path.join(outdir, "epoc-key-scores.png"))


if __name__ == "__main__":
    main()
