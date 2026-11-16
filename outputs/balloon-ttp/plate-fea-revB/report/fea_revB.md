# Revision B plates - quick native plate FEA

Same idealisation as `design/fea.md`, solved natively with scikit-fem
(Morley plate elements) because CalculiX only runs in the agent's WSL
environment. Thin-plate bending, 2.0 mm Al 6061-T6, rigid frictionless
bed over the shroud footprint, D20 washer patch with 144 N per ear
(the 12 g design envelope).

| | |
|---|---|
| mesh | 74297 Morley triangles, 151011 dofs |
| validation | 100x20x2 clamped strip: w_tip 0.3462 mm vs 0.3623 beam (ratio 0.96), root stress 7.93 vs 7.50 MPa (ratio 1.06) |
| cross-check vs CalculiX | sharp (revision A) profile peaks at 207 MPa at the notch; the agent's ccx study gives 223 MPa at the same point |
| revision B ear peak | **121 MPa** at (-125.8, -129.1) = first yield at 23.8 g |
| plate body (outside the ears) | 0.3 MPa |
| deflection | 0.37 mm |

## Mesh convergence (revision B ear peak)

| min element size | elements | ear peak MPa | body MPa | w max mm |
|---|---|---|---|---|
| 1.6 mm | 64705 | 122.3 | 0.4 | 0.378 |
| 1.1 mm | 74297 | 120.9 | 0.3 | 0.375 |
| 0.8 mm | 131038 | 118.1 | 0.2 | 0.367 |

## Variant study - where the geometry can be changed

| variant | ear peak MPa | first yield g | pair mass g | comment |
|---|---|---|---|---|
| revB 2.0 mm, R4, R15 ear | 121 | 23.8 | 373 | as built |
| blend R0 | 207 | 13.9 | 373 | revision A, sharp corner |
| blend R2 | 152 | 19.0 | 373 | half the blend |
| blend R4 | 121 | 23.8 | 373 | as built (= revB row) |
| blend R6 | 104 | 27.7 | 374 | sweet spot, no interface change |
| blend R8 | 106 | 27.1 | 374 | no further gain |
| blend R10 | 101 | 28.6 | 375 | no further gain |
| ear R18, blend R4 | 90 | 32.0 | 385 | bigger lobe, same hole and rope clearance |
| ear R21, blend R4 | 80 | 36.0 | 398 | biggest lobe that still fits |
| ear inboard 2 mm | 72 | 39.9 | 372 | rope clearance 6.5 mm - marginal |
| ear inboard 4 mm | 51 | 56.6 | 369 | rope clearance 4.5 mm - not acceptable |
| 2.5 mm sheet | 77 | 37.2 | 467 | fallback, +93 g/pair |
| washer D30 | 124 | 23.3 | 373 | bigger washer, no new part |
| top plate (no aperture) | 121 | 23.8 | 373 | not critical |

Differences below about 5 MPa are mesh noise (see the convergence
table). The *global* peak of this model (500+ MPa) sits on the
support-edge corner at |X| = 120, |Z| = 135.5 and is an artifact of
the rigid bed: the real EPS is compliant and spreads that reaction
over its 30 mm characteristic length. Only the ear peak is quoted as
a design number.

## Reading of the results

* The **ear/outline blend is what governs**. The sharp revision A
  profile peaks at 207 MPa in the ear
  (matches the CalculiX 223 MPa); the R4 blend drops it to
  121 MPa, i.e. first yield moves from
  13.9 g to 23.8 g. The blend is doing the work
  the study predicted.
* **The blend has a sweet spot near R6.** R6 is about 15 % better than
  the R4 that is on the drawing; R8 and R10 buy nothing more. Since the
  profile is being re-cut anyway, changing `EAR_BLEND` to 6.0 is free.
* **After the blend the plate is no longer the governing item.** First
  yield moves to 24 g, well above the 16.1 g
  thermocol-bearing envelope, so `strength.md` becomes thermocol-
  governed again (subject to the CalculiX re-run).
* **The body is not a design driver.** Away from the ears the plate
  peaks at 0.3 MPa - two orders below yield. The
  aperture ring, both lightening openings, the ligaments and the
  aperture/opening split between the two plates can all be changed
  freely; that is where mass can be taken out or vents added without
  touching the strength case.
* **Ear radius is the strongest lever after the blend**: R18 and R21
  widen the load path across the corner. It costs a little mass and
  no interface change (same hole position, same rope clearance), but
  it grows the lobe that bears on the lid.
* **Moving the ears inboard is not worth it**: it helps the moment arm
  but eats the rope clearance to the shroud faces, which is the whole
  reason the ears sit outboard.
* **The top plate is not critical** (no aperture, same ears), so the
  two-part split costs nothing structurally.
* Still open: this model is linear and one-sided contact is idealised
  as a rigid bed, so the ear stress is an upper bound. Re-run the
  CalculiX study on `plate_bottom.dxf` in WSL before quoting a new
  envelope.

## Figures

![fields](fea_revB_fields.png)

![variants](fea_revB_variants.png)

