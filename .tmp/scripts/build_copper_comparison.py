"""
One-off comparison-figure builder: Cu-ETP vs OFHC copper thermal straps,
balloon-ttp transient-0-40km ascent + 60-min dwell studies.

Not a general skill script -- reads the four already-completed studies'
transient_T_history.csv files directly and produces the figures referenced by
outputs/balloon-ttp/etp-vs-ohfc-copper-comparison/report.md.

Color assignment is fixed and entity-tied (never cycled/re-ranked): OFHC copper is
always the Okabe-Ito orange, Cu-ETP is always the Okabe-Ito blue, in every figure.
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "balloon-ttp" / "etp-vs-ohfc-copper-comparison" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

# Okabe-Ito colorblind-safe qualitative pair -- fixed per material, every figure.
C_OFHC = "#E69F00"  # orange
C_ETP = "#0072B2"   # blue
GRID_ALPHA = 0.3

STUDIES = {
    "ofhc_ascent": ROOT / "outputs/balloon-ttp/transient-0-40km/figures/transient_T_history.csv",
    "etp_ascent": ROOT / "outputs/balloon-ttp/transient-0-40km-etp-copper/figures/transient_T_history.csv",
    "ofhc_dwell": ROOT / "outputs/balloon-ttp/transient-0-40km-dwell-60min/figures/transient_T_history.csv",
    "etp_dwell": ROOT / "outputs/balloon-ttp/transient-0-40km-dwell-60min-etp-copper/figures/transient_T_history.csv",
}


def load(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    return {float(r["time_s"]): r for r in rows}


data = {k: load(v) for k, v in STUDIES.items()}

# Stitch ascent + dwell into one continuous 20..13200 s timeline per material.
ofhc = {**data["ofhc_ascent"], **data["ofhc_dwell"]}
etp = {**data["etp_ascent"], **data["etp_dwell"]}
times = sorted(set(ofhc) & set(etp))


def series(d, times, comp):
    return [float(d[t][f"{comp}_Tmax_C"]) for t in times]


# ---------------------------------------------------------------------------
# Figure 1: overlaid absolute temperature, OFHC vs ETP, full 0->13200s timeline
# ---------------------------------------------------------------------------
fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), sharey=False)
for ax, comp, title in zip(
    axes, ("jetson_module", "interface_plate"), ("jetson_module (die)", "interface_plate (cold plate)")
):
    ax.plot(times, series(ofhc, times, comp), color=C_OFHC, lw=2.0, label="OFHC copper (κ 390 W/m·K)")
    ax.plot(times, series(etp, times, comp), color=C_ETP, lw=2.0, ls="--", label="Cu-ETP copper (κ 386 W/m·K)")
    ax.axvline(9600, color="0.5", lw=1.0, ls=":")
    ax.set_xlabel("time [s]")
    ax.set_ylabel("temperature [°C]")
    ax.set_title(title)
    ax.grid(alpha=GRID_ALPHA)
# annotate the ascent->dwell boundary just inside the axes, below the title
for ax in axes:
    ymin, ymax = ax.get_ylim()
    ax.annotate("ascent ends /\ndwell begins", xy=(9600, ymin + 0.90 * (ymax - ymin)),
                fontsize=7.5, color="0.4", ha="left", va="top")
axes[0].legend(fontsize=8, loc="lower right")
fig.suptitle("Peak component temperature: OFHC vs Cu-ETP copper straps (0→40 km ascent + 60 min dwell)", fontsize=11)
fig.tight_layout(rect=(0, 0, 1, 0.94))
fig.savefig(OUT / "temperature_overlay.png", dpi=150)
plt.close(fig)

# ---------------------------------------------------------------------------
# Figure 2: the actual point of this report -- delta (ETP - OFHC) vs time
# ---------------------------------------------------------------------------
components_delta = [
    ("jetson_module", "jetson_module (die)"),
    ("interface_plate", "interface_plate (cold plate)"),
    ("copper_strap_left", "copper_strap_left"),
    ("radiator_plate", "radiator_plate"),
]
fig, ax = plt.subplots(figsize=(10, 5.5))
delta_colors = ["#0072B2", "#E69F00", "#009E73", "#CC79A7"]  # Okabe-Ito, fixed order per component
for (comp, label), col in zip(components_delta, delta_colors):
    d = [e - o for e, o in zip(series(etp, times, comp), series(ofhc, times, comp))]
    ax.plot(times, d, color=col, lw=1.6, label=label)
ax.axhline(0, color="0.3", lw=1.0)
ax.axvline(9600, color="0.5", lw=1.0, ls=":")
ymin, ymax = ax.get_ylim()
ax.annotate("ascent ends / dwell begins", xy=(9600, ymin + 0.08 * (ymax - ymin)), fontsize=7.5, color="0.4",
            ha="left", va="bottom")
ax.set_xlabel("time [s]")
ax.set_ylabel("ΔT = T(Cu-ETP) − T(OFHC)  [K]")
ax.set_title("Temperature delta, Cu-ETP minus OFHC copper straps — same 30 W load, same BCs")
ax.grid(alpha=GRID_ALPHA)
ax.legend(fontsize=8, loc="upper left", ncol=2)
fig.tight_layout()
fig.savefig(OUT / "delta_vs_time.png", dpi=150)
plt.close(fig)

# ---------------------------------------------------------------------------
# Figure 3: final-time delta by component, ascent end (9600s) vs dwell end (13200s)
# ---------------------------------------------------------------------------
components_bar = [
    "jetson_module", "interface_plate", "connector_block_left", "connector_block_right",
    "copper_strap_left", "copper_strap_right", "radiator_bracket_left", "radiator_bracket_right",
    "radiator_plate", "radiator_plate_2",
]
t_ascent_end = 9600.0
t_dwell_end = 13200.0


def delta_at(t, comp):
    return float(etp[t][f"{comp}_Tmax_C"]) - float(ofhc[t][f"{comp}_Tmax_C"])


d_ascent = [delta_at(t_ascent_end, c) for c in components_bar]
d_dwell = [delta_at(t_dwell_end, c) for c in components_bar]

x = range(len(components_bar))
w = 0.36
fig, ax = plt.subplots(figsize=(11, 5.2))
b1 = ax.bar([i - w / 2 for i in x], d_ascent, width=w, color="#56B4E9", label="t = 9600 s (ascent end)")
b2 = ax.bar([i + w / 2 for i in x], d_dwell, width=w, color="#0072B2", label="t = 13200 s (dwell end)")
ax.axhline(0, color="0.3", lw=1.0)
ax.set_xticks(list(x))
ax.set_xticklabels(components_bar, rotation=35, ha="right", fontsize=8)
ax.set_ylabel("ΔT = T(Cu-ETP) − T(OFHC)  [K]")
ax.set_title("Per-component temperature delta at the two checkpoints (positive = Cu-ETP runs hotter)")
ax.grid(alpha=GRID_ALPHA, axis="y")
ax.legend(fontsize=8.5)
fig.tight_layout()
fig.savefig(OUT / "delta_by_component_bar.png", dpi=150)
plt.close(fig)

print("wrote:")
for p in sorted(OUT.glob("*.png")):
    print(" ", p)

# Print the exact numbers used, for the report table.
print("\n--- headline numbers ---")
for t in (t_ascent_end, t_dwell_end):
    print(f"t={t}")
    for c in ("jetson_module", "interface_plate", "copper_strap_left", "copper_strap_right",
              "radiator_plate", "radiator_plate_2"):
        o = float(ofhc[t][f"{c}_Tmax_C"])
        e = float(etp[t][f"{c}_Tmax_C"])
        print(f"  {c:22s} OFHC={o:7.3f}  ETP={e:7.3f}  dT={e-o:+.4f}")
