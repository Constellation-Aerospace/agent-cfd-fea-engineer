import sys
sys.path.insert(0, "D:/Github/agent-cfd-fea-engineer/.tmp/scripts")
from atmosphere import atmosphere, ambient_T_blended
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

INK = "#16232d"
MUTED = "#7b8790"
MARINE = "#0f4c68"
THERMAL = "#b5501f"
SOFT = "#eef6fb"
LINE = "#c7d0d8"

alts_m = np.linspace(0, 40000, 401)
alts_km = alts_m / 1000.0
T_us76 = np.array([atmosphere(a)["T_C"] for a in alts_m])
T_blend = np.array([ambient_T_blended(a) - 273.15 for a in alts_m])
p_pa = np.array([atmosphere(a)["p_Pa"] for a in alts_m])
p_mbar = p_pa / 100.0

fig, (ax_t, ax_p) = plt.subplots(1, 2, figsize=(11.5, 7.2), sharey=True)
fig.patch.set_facecolor("white")

# --- Temperature panel ---
ax_t.plot(T_blend, alts_km, color=THERMAL, lw=2.4, label="Measured sounding blend\n(Kolkata 12z 19-May, <30 km) + US76")
ax_t.plot(T_us76, alts_km, color=THERMAL, lw=1.4, ls="--", alpha=0.55, label="US Standard Atmosphere 1976\n(reference model, all altitudes)")

# Achievable chamber cold-soak band
ax_t.axvspan(-47, -30, color=MARINE, alpha=0.08, zorder=0)
ax_t.axvline(-30, color=MARINE, lw=1.1, ls=":", alpha=0.8)
ax_t.axvline(-47, color=MARINE, lw=1.1, ls=":", alpha=0.8)
ax_t.text(-38.5, 21.5, "Chamber cold-soak\ntarget band\n(-30 to -47 C)", color=MARINE, fontsize=9,
           ha="center", va="bottom", fontweight="bold")

ax_t.axhline(40, color=INK, lw=1, ls="-", alpha=0.35, label="40 km mission ceiling\n(-22.8 C, 2.9 mbar)")
ax_t.axhline(31.2, color=MARINE, lw=1, ls="--", alpha=0.5, label="10 mbar chamber target\n= ~31 km equivalent (-45 C)")

ax_t.set_xlabel("Temperature (C)", fontsize=11, color=INK)
ax_t.set_ylabel("Altitude (km)", fontsize=11, color=INK)
ax_t.set_title("Temperature vs Altitude", fontsize=13, color=INK, fontweight="bold")
ax_t.set_ylim(0, 42)
ax_t.set_xlim(-85, 35)
ax_t.grid(True, color=LINE, lw=0.6, alpha=0.8)
ax_t.legend(loc="lower left", fontsize=7.8, frameon=True, facecolor="white", edgecolor=LINE)
for spine in ax_t.spines.values():
    spine.set_color(LINE)

# --- Pressure panel ---
ax_p.plot(p_mbar, alts_km, color=MARINE, lw=2.4)
ax_p.plot([2.9], [40], marker="o", color=INK, ms=5, zorder=5)
ax_p.set_xscale("log")
ax_p.axvline(10, color=MARINE, lw=1.1, ls=":", alpha=0.8)
ax_p.axhline(31.2, color=MARINE, lw=1, ls="--", alpha=0.5)
ax_p.axhline(40, color=INK, lw=1, ls="-", alpha=0.35)
ax_p.text(11, 33.4, "10 mbar chamber\ntarget = ~31 km", color=MARINE, fontsize=9, ha="left", va="bottom", fontweight="bold")
ax_p.text(3.4, 40.3, "40 km: 2.9 mbar", color=INK, fontsize=8.5, ha="left", va="bottom")

ax_p.set_xlabel("Pressure (mbar, log scale)", fontsize=11, color=INK)
ax_p.set_title("Pressure vs Altitude", fontsize=13, color=INK, fontweight="bold")
ax_p.set_xlim(1, 1100)
ax_p.set_ylim(0, 42)
ax_p.grid(True, which="both", color=LINE, lw=0.6, alpha=0.8)
for spine in ax_p.spines.values():
    spine.set_color(LINE)

fig.suptitle("Balloon-TTP Flight Environment Being Simulated: 0-40 km (US76 + measured sounding)",
             fontsize=14, color=INK, fontweight="bold", y=1.0)
fig.text(0.5, -0.02,
         "Source: .tmp/scripts/atmosphere.py (US Standard Atmosphere 1976) blended below 30 km with the digitized\n"
         "Kolkata 12:00 UTC 19-May-2026 radiosonde used across the balloon-ttp CFD studies. See outputs/balloon-ttp/PROJECT.md.",
         ha="center", fontsize=8.5, color=MUTED)

fig.tight_layout(rect=[0, 0.02, 1, 0.96])
out = "D:/Github/agent-cfd-fea-engineer/outputs/balloon-ttp/envisys-tvac-test-plan-jetson-radiators/diagrams/atmosphere_0_40km.png"
fig.savefig(out, dpi=170, bbox_inches="tight", facecolor="white")
print("saved", out)
