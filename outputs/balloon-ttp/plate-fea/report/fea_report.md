# Payload support plate - shell FEA

`tools/check_strength.py` in the payload project checks the ear as a
hand-calculated cantilever. This study is the finite-element cross-check
of the whole part: the real cut profile, a 2.0 mm aluminium shell, the
thermocol lid as a support and the rope load applied where the washer
actually presses.

| | |
|---|---|
| solver | CalculiX ccx 2.21 (WSL) |
| elements | S6 shells (6-node quadratic triangles), t = 2.0 mm (expanded to C3D15 by ccx) |
| material | Al 6061-T6: E = 69000 MPa, nu = 0.33, Fty = 240, Ftu = 290 MPa |
| support | rigid frictionless bed over the shroud footprint + 3-2-1 in-plane point constraints |
| load | 20 mm washer patch per ear + plate self weight |
| mesh | 12776 S6 elements, 28472 nodes (scale 1.0) |
| geometry | design/plate.dxf, cut area 32675 mm2, plate 176 g |
| all-up weight | 47.98 N (4.89 kg) |

## Validation of the model

A 100 x 20 x 2 mm cantilever strip of the same material was meshed
and loaded the same way (1701 nodes, 802 S6).

| quantity | FEA | theory | ratio |
|---|---|---|---|
| tip deflection | 0.3531 mm | 0.3623 mm (beam) / 0.3229 mm (plate) | 0.97 |
| root stress | 8.10 MPa | 7.50 MPa | 1.08 |

The strip sits between beam theory (narrow strip) and plate theory
(lateral curvature suppressed), i.e. the shell behaves as it should.

## Load cases

Each ear carries the clamp-loop tension T = n g W / 4 + T0, where T0 is
the per-loop pretension. The loops - not the foam - carry the payload,
so a heavily pretensioned loop loads the ear more than the g-level does.

| case | T / ear | von Mises | SF yield | SF ult | w max | bearing | SF bear |
|---|---|---|---|---|---|---|---|
| 1 g, loops just taut | 12 N | 18.6 MPa | 12.94 | 15.63 | 0.044 mm | 41 kPa | 2.4 |
| 2 g balloon launch jerk | 24 N | 37.2 MPa | 6.46 | 7.80 | 0.088 mm | 83 kPa | 1.2 |
| 5 g parachute opening | 60 N | 93.0 MPa | 2.58 | 3.12 | 0.220 mm | 207 kPa | 0.5 |
| 12 g design envelope | 144 N | 223.3 MPa | 1.07 | 1.30 | 0.528 mm | 497 kPa | 0.2 |
| 16.2 g qualification limit | 194 N | 301.4 MPa | 0.80 | 0.96 | 0.713 mm | 671 kPa | 0.1 |
| 1 g + 50 N pretension | 62 N | 96.1 MPa | 2.50 | 3.02 | 0.228 mm | 214 kPa | 0.5 |
| 1 g + 100 N pretension | 112 N | 173.7 MPa | 1.38 | 1.67 | 0.411 mm | 386 kPa | 0.3 |
| 5 g, one loop lost (2 ears) | 120 N | 175.2 MPa | 1.37 | 1.66 | 0.401 mm | 414 kPa | 0.2 |

Yield of the peak location corresponds to **T = 155 N per ear** (ultimate 187 N), i.e. about **12.9 g** with just-taut loops.

## Where the stress is

At the 12 g envelope the peak is 223.3 MPa at X = 123.0, Z = 130.1 - on the
ear circumference, where the R15 ear lobe runs into the straight plate
edge. That transition is a **sharp re-entrant corner** in the cut
profile. The hand calc assumes the ear root is the full 24.7 mm chord
with Kt = 1.15; the FE load path actually crosses the ear/plate blend at
~12 mm width, with the notch concentration on top of that.

Outside the four lobes the whole plate peaks at **5 MPa** at the same 12 g load, so the camera
aperture ring, the lightening openings and the ligaments are not at
risk, and neither is the part in global bending. Note that the rigid
bed holds the field flat, so this is an underestimate: a compliant
foundation lets the plate sink and bend a little more, but not to
anything like the ear value.

The through-thickness average (mid-surface) stress at the peak is 114 MPa,
about half the surface value: the ear blend is a mixed bending +
in-plane notch. Both come from the same geometry, so fixing the blend
fixes both.

## Mesh independence

| element size scale | elements | peak von Mises | ear-root section | w max |
|---|---|---|---|---|
| 1.45 | 7102 | 249.61 MPa | 188.83 MPa | 0.608 mm |
| 1.00 | 12776 | 223.26 MPa | 218.82 MPa | 0.528 mm |
| 0.72 | 22182 | 225.13 MPa | 225.13 MPa | 0.458 mm |

A sharp corner has no finite radius, so its peak is a local
concentration rather than a field value; the table shows it settling at
about 225 MPa while the ear-root section converges to the same number,
i.e. the concentration is real and mesh-independent, not a numerical
artifact.

## Sheet thickness

Same profile, same 12 g loop load, only `*SHELL SECTION` changes - a
direct cross-check of `strength.md` section 'Thickness sensitivity'.

| t | peak von Mises | first yield | mass / pair |
|---|---|---|---|
| 1.0 mm | 1022.3 MPa | 2.8 g | 176 g |
| 1.5 mm | 422.1 MPa | 6.8 g | 265 g |
| 2.0 mm | 223.3 MPa | 12.9 g | 353 g |
| 2.5 mm | 148.1 MPa | 19.4 g | 441 g |

Peak stress falls with t^2 as expected, so going to 2.5 mm sheet is a
one-line change that buys ~1.5x capacity at the blend - at the cost of
mass against the 5 kg limit.

## Bearing on the thermocol

The bed is modelled as rigid, so its reaction concentrates under the ear
corner and is an *upper bound* on the foam pressure. The real EPS is
compliant (k = E/t = 0.06 N/mm3) and spreads the load over its
characteristic length L = 30.5 mm. The pi L^2 spreading model in
strength.md (about 4 kPa/ear at 1 g) is the realistic number and keeps a
wide margin on the 100 kPa EPS limit at every case in the table.

## Conclusions

* The plate is a bending part and the ears govern, as assumed - but the
  real concentration is at the ear/outline blend, not at the washer seat.
  The FEA peak (223 MPa at 12 g) is about 3.0x the strength.md hand calc
  (6.2 MPa/ear at 1 g scaled to 12 g), because the ear only overlaps the
  plate over a ~12 mm chord and the blend is a sharp re-entrant corner.
* Outside the four lobes the plate peaks at 5 MPa, so the apertures, the openings and the
  ligaments are not at risk, and neither is the part in global bending.
  Deflections are small (0.53 mm at 12 g).
* With every loop taut the ear blend first yields at about 13 g (T = 155 N/ear), against
  strength.md's 33.7 g. That still covers the expected flight loads -
  2 g gives SF 6.5 and 5 g SF 2.6 - but
  it does **not** cover the 12-16 g qualification envelope the same
  document quotes.
* Loop pretension of 50-100 N, easily applied by hand, is a large share
  of the ear load (it doubles or triples it). Specify the pretension.
* Two ways to restore the envelope, in order of preference:
  1. blend the ear/outline transitions (R3-R5) in the cut profile - it
     only adds material in empty space, no interface change, and it
     removes the notch that produces the concentration;
  2. go to 2.5 mm sheet (see the table above) - about 1.5x capacity for
     +88 g per pair.
  Either way, re-run this study afterwards and re-issue strength.md.

## Figures

![fields](figures/fea_fields.png)

![ears](figures/fea_ears.png)

## Artifacts

Reproduce with (agent repo, `.venv`):

```
python run_plate_fea.py --study balloon-ttp/plate-fea --validate
```

`outputs/balloon-ttp/plate-fea/fea/` holds the CalculiX decks and
results per case (`case1.inp`/`.frd` ... `case8`, `conv`, `thk`,
`validate/strip`), `fea_summary.json` with every number in this report,
and `figures/` with the two plots.

