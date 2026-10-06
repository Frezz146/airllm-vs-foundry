"""Aggregate raw results into a summary CSV and a chart.

  report.py                          all results      -> results/summary.csv, docs/images/benchmark.png
  report.py --filter 70B --name 70b  only series whose label contains 70B -> results/summary_70b.csv, docs/images/benchmark_70b.png

Compared metrics are tokens per second and time to first token. Total time is not charted because
the backends may generate a different number of new tokens (AirLLM is very slow per token).
"""
import argparse
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from dotenv import load_dotenv
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

from common import ROOT

load_dotenv()

# Reference palette, categorical slots 1 to 4 in fixed order (adjacent pairs validated: CVD and normal vision pass)
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
LENGTHS = ["short", "medium", "long"]


def label(row) -> str:
    name = str(row["model"]).split("/")[-1]
    return f"{'AirLLM' if row['backend'] == 'airllm' else 'Foundry'}: {name}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--filter", help="keep only series whose label contains this text (case insensitive)")
    ap.add_argument("--name", help="suffix for the output files")
    args = ap.parse_args()

    frames = [pd.DataFrame(json.loads(p.read_text(encoding="utf-8"))) for p in sorted((ROOT / "results" / "raw").glob("*.json"))]
    if not frames:
        raise SystemExit("No raw results found. Run the benchmarks first.")
    df = pd.concat(frames, ignore_index=True)
    df["series"] = df.apply(label, axis=1)
    if args.filter:
        df = df[df["series"].str.contains(args.filter, case=False, regex=False)]
        if df.empty:
            raise SystemExit(f"No series matches filter {args.filter!r}")
    suffix = f"_{args.name}" if args.name else ""

    summary = (df.groupby(["series", "length"])
                 .agg(ttft_median_s=("ttft_s", "median"), total_median_s=("total_s", "median"),
                      total_std_s=("total_s", "std"), tokens_per_s_median=("tokens_per_s", "median"),
                      output_tokens=("output_tokens", "median"), runs=("run", "count"))
                 .reset_index())
    summary["length"] = pd.Categorical(summary["length"], LENGTHS, ordered=True)
    summary = summary.sort_values(["series", "length"])
    out = ROOT / "results" / f"summary{suffix}.csv"
    summary.to_csv(out, index=False)
    print(summary.to_string(index=False))

    f = df[df.backend == "foundry"]
    if not f.empty and "throttled" in f:
        print(f"\nFoundry throttled attempts (excluded from timings): {int(f['throttled'].sum())}")
    price_model = os.getenv("FOUNDRY_PRICE_MODEL", "gpt-5-mini")
    fp = f[f["model"].str.contains(price_model, case=False, regex=False)]
    p_in = float(os.getenv("FOUNDRY_PRICE_INPUT_PER_1M", 0))
    p_out = float(os.getenv("FOUNDRY_PRICE_OUTPUT_PER_1M", 0))
    p_cached = float(os.getenv("FOUNDRY_PRICE_CACHED_INPUT_PER_1M", p_in))
    if not fp.empty and (p_in or p_out):
        cached = fp["cached_tokens"].fillna(0) if "cached_tokens" in fp else 0
        fresh = fp["input_tokens"].fillna(0) - cached
        cost = (fresh * p_in + cached * p_cached + fp["output_tokens"] * p_out) / 1_000_000
        cur = os.getenv("FOUNDRY_PRICE_CURRENCY", "EUR")
        print(f"Foundry cost for {len(fp)} runs of {price_model} (prices from .env): {cost.sum():.4f} {cur}, per run: {cost.mean():.6f} {cur}")

    series = list(dict.fromkeys(summary["series"]))
    if len(series) > len(COLORS):
        raise SystemExit(f"{len(series)} series, at most {len(COLORS)} are supported. Use --filter.")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), facecolor=SURFACE)
    panels = [("tokens_per_s_median", "Throughput (tokens per second, median)", "{:.2f}"),
              ("ttft_median_s", "Time to first token (seconds, median)", "{:.1f}")]
    offsets = {s: (i - (len(series) - 1) / 2) * 0.2 for i, s in enumerate(series)}
    for ax, (col, title, fmt) in zip(axes, panels):
        ax.set_facecolor(SURFACE)
        for i, s in enumerate(series):
            sub = summary[summary.series == s].set_index("length")
            xs = [LENGTHS.index(l) + offsets[s] for l in sub.index]
            ys = sub[col].tolist()
            ax.scatter(xs, ys, s=110, color=COLORS[i], edgecolor=SURFACE, linewidth=2, label=s, zorder=3)
            for x, y in zip(xs, ys):
                ax.annotate(fmt.format(y), (x, y), textcoords="offset points", xytext=(0, 11),
                            ha="center", fontsize=9, color=INK)
        ax.set_yscale("log")
        ax.yaxis.set_major_locator(LogLocator(base=10, subs=(1, 2, 5)))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        ax.yaxis.set_minor_formatter(NullFormatter())
        ax.set_xticks(range(len(LENGTHS)))
        ax.set_xticklabels([f"{l} prompts" for l in LENGTHS], color=INK_2)
        ax.set_xlim(-0.5, len(LENGTHS) - 0.5)
        ax.set_title(title, loc="left", fontsize=11, color=INK)
        ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
        ax.tick_params(colors=INK_2, length=0)
        for spine in ax.spines.values():
            spine.set_visible(False)
        lo, hi = ax.get_ylim()
        ax.set_ylim(lo / 1.6, hi * 2.2)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=min(len(labels), 2), frameon=False,
               labelcolor=INK, fontsize=10, bbox_to_anchor=(0.5, -0.01))
    fig.suptitle("AirLLM layer streaming vs. Microsoft Foundry (log scale)", x=0.012, ha="left", fontsize=13, color=INK)
    tokens = sorted({int(t) for t in df["max_new_tokens"].dropna()}) if "max_new_tokens" in df else []
    note = "Medians per prompt length."
    note += (f" New tokens per request: {', '.join(map(str, tokens))}." if tokens else " AirLLM and Foundry may generate a different number of new tokens.")
    note += " Tokens per second is the fair comparison."
    fig.text(0.012, 0.905, note, fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0.07 if len(labels) > 2 else 0.06, 1, 0.9))
    png = ROOT / "docs" / "images" / f"benchmark{suffix}.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    png.parent.mkdir(exist_ok=True)
    fig.savefig(png, dpi=160, facecolor=SURFACE)
    print("\nsaved", out, "and", png)


if __name__ == "__main__":
    main()
