#!/usr/bin/env python3
"""Render the README charts from data/. usage: plots.py  (writes images/*.png)
Needs matplotlib: nix-shell -p 'python3.withPackages(p:[p.matplotlib])'
Colours: the site's osu! blue/pink stepped into the dark-mode lightness band (validated)."""
import pathlib, statistics
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = pathlib.Path(__file__).resolve().parent.parent
LT, RT = "#389cd4", "#e5508f"
SURF, INK, INK2, GRID = "#0e1422", "#f1f5f9", "#94a3b8", "#1f2a40"
plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 11,
})


def raw_lattice():
    rows = [l.split() for l in open(root / "data/telem_raw_div4_60s.log")]
    t0 = float(rows[0][0])
    t = [float(r[0]) - t0 for r in rows]
    fig, axes = plt.subplots(2, 1, figsize=(10, 5.6), sharex=True)
    for ax, col, name, colour in ((axes[0], 1, "LT", LT), (axes[1], 2, "RT", RT)):
        v = [int(r[col]) for r in rows]
        base = statistics.mode(v)
        ax.scatter(t, v, s=9, color=colour, linewidths=0)
        ax.set_title(f"{name} raw value, controller untouched", loc="left", color=INK, fontsize=11)
        for k in range(0, 13):
            ax.axhline(base + 100 * k, color=GRID, lw=0.6, zorder=0)
        ax.set_ylabel("raw (sum of 80 / 10)")
    axes[1].set_xlabel("seconds (stock ADC clock, 48 MHz / 4)")
    axes[0].annotate("each step up = one bad sample in the 80-sample average (+~100)",
                     xy=(0.99, 0.92), xycoords="axes fraction", ha="right", color=INK2, fontsize=10)
    fig.tight_layout()
    fig.savefig(root / "images/raw_lattice_div4.png", dpi=110)


def snapshot():
    def pick(path, want_bad):
        for line in open(path):
            a = list(map(int, line.split()[1:85]))[4:]  # LT buffer, the firmware's averaging window
            med = statistics.median(a)
            bad = [i for i, x in enumerate(a) if abs(x - med) > 12]
            if bool(bad) == want_bad and (not want_bad or len(bad) >= 3):
                return a
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, path, title, bad in ((axes[0], "data/snap_div4_90s.log", "stock: 12 MHz ADC clock", True),
                                 (axes[1], "data/snap_div8_90s.log", "fixed: 6 MHz ADC clock", False)):
        a = pick(root / path, bad)
        ax.plot(range(4, 84), a, color=LT, lw=2)
        ax.scatter(range(4, 84), a, s=14, color=LT, edgecolors=SURF, linewidths=1.2, zorder=3)
        ax.set_title(f"one LT DMA buffer, {title}", loc="left", color=INK, fontsize=11)
        ax.set_xlabel("sample index (4 to 83 are averaged)")
        if bad:
            spikes = [(i + 4, x) for i, x in enumerate(a) if x in (2048, 1023)]
            for i, x in spikes[:1]:
                ax.annotate("exactly 2048 (0x800)", xy=(i, x), xytext=(i + 6, x - 180),
                            color=INK2, fontsize=10, arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    axes[0].set_ylabel("ADC value (12-bit)")
    axes[0].set_ylim(900, 2200)
    fig.tight_layout()
    fig.savefig(root / "images/dma_buffer_div4_vs_div8.png", dpi=110)


raw_lattice()
snapshot()
print("images/raw_lattice_div4.png, images/dma_buffer_div4_vs_div8.png")
