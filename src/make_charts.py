"""Build static charts + a one-page dashboard preview from results/*.csv."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parent.parent
R, IMG = ROOT / "results", ROOT / "images"
IMG.mkdir(exist_ok=True)

ACCENT, MUTED, ACCENT2 = "#1F6FEB", "#B8BEC7", "#E8590C"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "axes.spines.top": False, "axes.spines.right": False,
    "axes.titleweight": "bold", "axes.titlesize": 11, "axes.labelsize": 9,
    "xtick.labelsize": 8, "ytick.labelsize": 8,
})

share = pd.read_csv(R / "sector_share.csv")
trend = pd.read_csv(R / "sector_trend.csv")
region = pd.read_csv(R / "region_sector.csv")
pareto = pd.read_csv(R / "facility_pareto.csv")
inten = pd.read_csv(R / "intensity.csv")
road = pd.read_csv(R / "roadmap_summary.csv")
kpi = pd.read_csv(R / "kpis.csv").iloc[0]


def c_share(ax):
    d = share.sort_values("share_pct_all_years")
    cols = [ACCENT if s == "Manufacturing" else MUTED for s in d.sector]
    ax.barh(d.sector, d.share_pct_all_years, color=cols)
    for y, v in enumerate(d.share_pct_all_years):
        ax.text(v + 0.4, y, f"{v:.1f}%", va="center", fontsize=8)
    ax.set_title("Share of total emissions by sector (2015-2023)")
    ax.set_xlabel("% of total CO2e"); ax.set_xlim(0, d.share_pct_all_years.max() * 1.18)


def c_trend(ax):
    hi = {"Manufacturing": ACCENT, "Power & Utilities": ACCENT2}
    ends = []
    for s, g in trend.groupby("sector"):
        ax.plot(g.year, g.pct_vs_2015, color=hi.get(s, MUTED), lw=2.2 if s in hi else 1.2)
        ends.append([s, g.iloc[-1].pct_vs_2015])
    # de-overlap end labels: keep at least `gap` between neighbours
    ends.sort(key=lambda e: e[1])
    gap = 1.1
    pos = [e[1] for e in ends]
    for i in range(1, len(pos)):
        pos[i] = max(pos[i], pos[i - 1] + gap)
    for (s, _), y in zip(ends, pos):
        ax.text(2023.15, y, s, fontsize=7, color=hi.get(s, "#6B7280"), va="center")
    ax.axhline(0, color="#999", lw=0.6)
    ax.set_title("Emissions change vs 2015, by sector")
    ax.set_ylabel("% change vs 2015"); ax.set_xlim(2015, 2027.2)


def c_pareto(ax):
    n = len(pareto)
    x = pareto.facility_rank / n * 100
    ax.plot(x, pareto.cumulative_share_pct, color=ACCENT, lw=2)
    ax.plot([0, 100], [0, 100], color=MUTED, ls="--", lw=1)
    top10 = pareto.loc[pareto.facility_rank == round(n * 0.10), "cumulative_share_pct"].iloc[0]
    ax.scatter([10], [top10], color=ACCENT2, zorder=3)
    ax.annotate(f"Top 10% of facilities\n= {top10:.0f}% of emissions", (10, top10),
                (24, top10 - 22), fontsize=8, arrowprops=dict(arrowstyle="-", color="#666"))
    ax.set_title("Emissions are concentrated in a few facilities (2023)")
    ax.set_xlabel("% of facilities (largest first)"); ax.set_ylabel("cumulative % of emissions")
    return top10


def c_heat(ax):
    p = region.pivot(index="region", columns="sector", values="co2e_2023_tonnes") / 1e6
    sns.heatmap(p, ax=ax, cmap="Blues", annot=True, fmt=".1f", linewidths=.5,
                cbar=False, annot_kws={"fontsize": 7})
    ax.set_title("2023 emissions by region and sector (Mt CO2e)")
    ax.set_xlabel(""); ax.set_ylabel("")
    ax.tick_params(axis="x", rotation=40)
    for t in ax.get_xticklabels():
        t.set_ha("right")


def c_inten(ax):
    d = inten[inten.year == 2023].sort_values("tco2e_per_musd")
    cols = [ACCENT if s == "Manufacturing" else MUTED for s in d.sector]
    ax.barh(d.sector, d.tco2e_per_musd, color=cols)
    ax.set_title("Carbon intensity, 2023")
    ax.set_xlabel("tCO2e per $M revenue")


def c_road(ax):
    d = road[road.sector != "ALL SECTORS"].sort_values("total_reduction_tonnes")
    ax.barh(d.sector, d.lever_a_efficiency_tonnes / 1e6, color=ACCENT, label="A: efficiency to sector median")
    ax.barh(d.sector, d.lever_b_renewables_tonnes / 1e6, left=d.lever_a_efficiency_tonnes / 1e6,
            color=ACCENT2, label="B: renewable floor")
    tot = road[road.sector == "ALL SECTORS"].iloc[0]
    ax.set_title(f"Reduction roadmap: {tot.reduction_pct_of_sector:.1f}% of 2023 baseline")
    ax.set_xlabel("Mt CO2e avoided"); ax.legend(frameon=False, fontsize=7, loc="lower right")


def save(fn, name, size=(7.5, 4.6)):
    fig, ax = plt.subplots(figsize=size)
    fn(ax)
    fig.tight_layout(); fig.savefig(IMG / name, dpi=160); plt.close(fig)


for fn, name in [(c_share, "01_sector_share.png"), (c_trend, "02_trend_vs_2015.png"),
                 (c_pareto, "03_facility_pareto.png"), (c_heat, "04_region_sector_heatmap.png"),
                 (c_inten, "05_carbon_intensity.png"), (c_road, "06_reduction_roadmap.png")]:
    save(fn, name, (8.5, 5) if fn is c_heat else (7.5, 4.6))

# ---- one-page dashboard preview ------------------------------------------------
fig = plt.figure(figsize=(16, 10.5))
gs = fig.add_gridspec(3, 3, height_ratios=[0.35, 2, 2.2], hspace=0.75, wspace=0.42)
fig.suptitle("Industry Carbon Emissions - Dashboard Preview (synthetic data)",
             fontsize=16, fontweight="bold", x=0.06, ha="left", y=0.985)
tiles = [("Facility-year records", f"{int(kpi.clean_records):,}"),
         ("Facilities", f"{int(kpi.facilities):,}"),
         ("2023 emissions", f"{kpi.co2e_2023 / 1e6:.1f} Mt CO2e"),
         ("Change vs 2015", f"{kpi.change_pct_2015_2023:+.1f}%")]
tax = fig.add_subplot(gs[0, :]); tax.axis("off")
for i, (lab, val) in enumerate(tiles):
    tax.text(0.02 + i * 0.25, 0.62, val, fontsize=20, fontweight="bold", color=ACCENT, transform=tax.transAxes)
    tax.text(0.02 + i * 0.25, 0.15, lab, fontsize=10, color="#555", transform=tax.transAxes)
for fn, pos in [(c_share, (1, 0)), (c_trend, (1, 1)), (c_pareto, (1, 2)),
                (c_heat, (2, 0)), (c_inten, (2, 1)), (c_road, (2, 2))]:
    fn(fig.add_subplot(gs[pos]))
fig.savefig(IMG / "dashboard_preview.png", dpi=130, bbox_inches="tight", facecolor="white")
print("charts saved to", IMG)
