"""Draws the AirLLM layer streaming diagram used in the blog post.

Usage: python src/make_diagram.py   (writes docs/images/airllm_layer_streaming.png)
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images" / "airllm_layer_streaming.png"

BLUE = "#2a78d6"
ORANGE = "#eb6834"
INK = "#1f2933"
MUTE = "#5b6670"
BG = "#ffffff"
LIGHT = "#e8eef7"
GRID = "#cfd8e3"

fig, ax = plt.subplots(figsize=(11, 5.6), dpi=200)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 110)
ax.set_ylim(-9, 56)
ax.axis("off")


def box(x, y, w, h, fc, ec, txt="", tc=INK, fs=10, weight="normal", lw=1.4):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.0,rounding_size=1.2", fc=fc, ec=ec, lw=lw))
    if txt:
        ax.text(x + w / 2, y + h / 2, txt, ha="center", va="center", color=tc, fontsize=fs, fontweight=weight)


ax.text(1, 53, "How AirLLM runs a model that does not fit into memory", fontsize=15, fontweight="bold", color=INK, va="center")

# Row 1: normal loading
ax.text(1, 45.5, "Normal: all 80 layers must sit in memory at once", fontsize=11.5, fontweight="bold", color=INK, va="center")
ax.text(1, 42.3, "70B model in bf16 = about 140 GB, a 64 GB laptop cannot hold it", fontsize=10, color=MUTE, va="center")
for i in range(16):
    box(1 + i * 4.3, 33, 3.7, 6, LIGHT, GRID, "", lw=1)
ax.text(71, 36, "... x 80 layers", fontsize=10, color=MUTE, va="center")
box(88, 32, 21, 8, "#ffffff", ORANGE, "64 GB RAM\n(too small)", tc=ORANGE, fs=10, weight="bold", lw=2)

ax.plot([1, 109], [28, 28], color=GRID, lw=1)

# Row 2: AirLLM streaming
ax.text(1, 24.5, "AirLLM: one layer at a time, streamed from the SSD", fontsize=11.5, fontweight="bold", color=INK, va="center")
ax.text(1, 21.3, "Repeated for every single token, so the disk speed sets the pace", fontsize=10, color=MUTE, va="center")

box(1, 6, 26, 10, LIGHT, BLUE, "SSD\n80 layer files\n140 GB", fs=10, weight="bold", lw=1.6)
box(42, 6, 26, 10, "#ffffff", BLUE, "RAM\nonly 1 layer\n(about 1.75 GB)", fs=10, weight="bold", lw=2)
box(83, 6, 26, 10, LIGHT, BLUE, "Compute\nthen discard\nthe layer", fs=10, weight="bold", lw=1.6)
for x0, x1 in [(27.5, 41.5), (68.5, 82.5)]:
    ax.add_patch(FancyArrowPatch((x0, 11), (x1, 11), arrowstyle="-|>", mutation_scale=16, color=BLUE, lw=2))
ax.text(34.5, 13.3, "read", ha="center", fontsize=9.5, color=MUTE)
ax.text(75.5, 13.3, "next", ha="center", fontsize=9.5, color=MUTE)
ax.add_patch(FancyArrowPatch((96, 5.0), (14, 5.0), connectionstyle="arc3,rad=-0.15", arrowstyle="-|>", mutation_scale=16, color=ORANGE, lw=2))
ax.text(55, -7.2, "80 layers = one token (about 20 s in my test), then everything starts again for the next token",
        ha="center", fontsize=10, color=ORANGE, fontweight="bold")

OUT.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(OUT, bbox_inches="tight", facecolor=BG)
print(f"saved {OUT}")
