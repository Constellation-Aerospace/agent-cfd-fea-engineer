# Validation References — Submerged Buoyant Jets & Marine Exhaust

Anchors for the validation methodology section of study reports. Use `web_search` /
`fetch_page` to pull specific data when building a validation case.

## Classical correlations (first-order sanity checks)

- **Turbulent round jet centreline decay:** excess velocity and temperature decay
  ~ 1/x in the self-similar far field (x/D > ~10); centreline dilution
  S ≈ 0.25·(x/D) for momentum jets.
- **Buoyant jet transition:** momentum-to-buoyancy length scale
  l_M = M^(3/4)/B^(1/2) (M momentum flux, B buoyancy flux) — beyond l_M plume behaviour
  dominates; check the simulated plume bends upward at a consistent distance.
- **Back-pressure decomposition:** p_inlet ≈ p_atm + rho_w·g·H + Δp_dynamic + Δp_losses.
  The CFD gauge back-pressure should exceed rho_w·g·H; large excess implies choking or
  interface pumping effects worth inspecting.

## Experimental datasets (literature)

- Papanicolaou & List (1988), JFM 195 — round vertical buoyant jets: velocity/scalar decay.
- Wang & Law (2002), JFM 459 — second-order integral model for jets/plumes.
- Gas jets discharged into water (air-water VOF validation): Loth & Faeth (1989),
  Int. J. Multiphase Flow — submerged air jet structure.
- Marine exhaust specific: class society guidance on submerged exhaust back-pressure
  limits (typical MDO engine limit ~30-50 mbar above atmospheric at the turbocharger).

## Recommended validation ladder

1. Solver-level: laminar/RANS single-phase round jet vs. classical decay correlation.
2. Two-phase: submerged air jet in water tank vs. Loth & Faeth penetration/void data.
3. Application: mesh-independent full case + parametric envelope + engine back-pressure
   limit compliance check.
