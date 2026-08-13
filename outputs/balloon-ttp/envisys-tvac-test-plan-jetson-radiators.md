# Envisys Tech TVAC Test Plan - Jetson with Copper Straps and Radiator Variants

**Project:** balloon-ttp  
**Purpose:** provide a short, technician-ready TVAC plan for four quick thermal checks of the Jetson payload with the latest radiator/strap setup.  
**Test window:** 8 hours total  
**Setup location:** Envisys Tech TVAC chamber

## 1. Objective

We need to screen four payload configurations within one 8-hour chamber window:

1. Jetson at 30 W with both radiators
2. Jetson at 10 W with both radiators
3. Jetson at 10 W with a single radiator
4. Jetson at 30 W with a single radiator

The payload flies from ground level to 40 km on the balloon. What we are asking the chamber to simulate is the **cold, low-pressure environment the payload sees on the way up to 40 km** — not the exact timeline of the flight, which is far longer than 8 hours. Section 2 below shows that environment (temperature and pressure vs altitude, 0 to 40 km) and exactly which part of it the chamber profile is standing in for, so the technician isn't just chasing a setpoint in isolation.

## 2. Flight Environment Being Simulated (0 to 40 km)

This is the actual altitude environment the payload experiences, built from the same atmosphere model used in the project's CFD studies (US Standard Atmosphere 1976, blended below 30 km with a digitized real radiosonde profile for the flight location — see `outputs/balloon-ttp/PROJECT.md` and `.tmp/scripts/atmosphere.py`). It is not a new assumption invented for this test plan; it is the same environment the thermal simulations use as their boundary condition.

![Temperature and pressure vs altitude, 0-40 km](diagrams/atmosphere_0_40km.png)

Key reference points:

| Altitude | Ambient temperature | Ambient pressure | Note |
| --- | ---: | ---: | --- |
| 0 km (ground) | ~28 C | 1013 mbar | Test start / chamber at ambient |
| ~11 km | ~-36 C | 227 mbar | Coldest point in the lower atmosphere on the way up |
| ~20 km | ~-57 to -67 C | 55 mbar | Tropopause cold plateau (coldest true air temperature the payload sees) |
| ~31 km | ~-45 C | **10 mbar** | Where the chamber's pressure target and the real atmosphere's temperature line up together |
| 40 km (mission ceiling) | ~-23 C | **2.9 mbar** | Actual end-of-flight condition — warmer but much lower pressure than the chamber test reaches |

**Why the chamber profile is not a literal 40 km replica:** the chamber technician has reported it can reliably reach about 10 mbar within the 8-hour window. In the real atmosphere, 10 mbar corresponds to roughly 31 km, where the true air temperature is about -45 C — which is essentially the chamber's "-40 C or lower" cold target in Section 5. So the requested chamber profile (10 mbar, -40 to -47 C) is a good simultaneous match to ~31 km conditions, reached and held for real comparison time.

Actual 40 km air is colder in pressure (2.9 mbar, about a third of the chamber's target vacuum) but *warmer* in temperature (-23 C, milder than the chamber's cold soak) than the tropopause region the chamber profile is really probing. In other words: **the requested chamber profile is thermally conservative (colder than true 40 km) but not vacuum-representative of 40 km** (it doesn't reach 40 km's much lower pressure in the 8-hour window). If the chamber can be pushed lower than 10 mbar without threatening the 8-hour schedule, pulling toward 3-5 mbar during the final soak of Test 4 would be a closer match to the true 40 km vacuum level — but this is a stretch goal, not a requirement; do not sacrifice the comparability of the four tests to chase it.

## 3. Simulation Reference — What We Expect to See (Case 1 benchmark)

The project has already run a transient CFD simulation of the exact Case 1 configuration (30 W, both radiators, full ascent to 40 km, `outputs/balloon-ttp/transient-0-40km` and its 60-minute-dwell continuation `transient-0-40km-dwell-60min`). This is not a prediction for the chamber test itself — the chamber's cold-soak profile is much faster and colder than a real ascent — but it tells the technician what a healthy Jetson/radiator response looks like on this hardware, and gives concrete numbers to sanity-check the logged data against.

![Simulated transient response, 30 W dual-radiator ascent to 40 km](diagrams/sim_reference_30W_dual_radiator_ascent.png)

Simulated result at the end of the ascent (t = 9600 s, 40 km) and after a further 60-minute hold at 40 km:

| Quantity | End of ascent (40 km) | After 60 min dwell at 40 km |
| --- | ---: | ---: |
| `jetson_module` | 71.3 C | 78.2 C |
| `interface_plate` (cold plate) | 72.1 C | 78.9 C |
| Radiator plates (max) | ~19.4 / 19.9 C | ~25.0 / 25.5 C |
| Heat rejected by radiators | ~24.2 W | ~26.3 W |
| Heat injected at the die | 30.1 W | 30.1 W |

The gap between injected and rejected heat (still ~4 W after the dwell) means the assembly was still slowly warming at the end of both simulations — it had not reached steady state even after 60 minutes at altitude. **This means the chamber's cold-soak hold should also be read as "still trending," not "must go flat."** A Jetson temperature that is still slowly climbing at the end of a 2-hour test window is consistent with the simulation, not necessarily a fault.

**No simulation exists yet for the 10 W cases or for either single-radiator case (Tests 2, 3, 4)** — the single-radiator hardware configuration in particular has not been modelled in CFD at all. Those three tests are filling a real gap in the analysis, not just re-confirming it; treat their results as new information for the team, not a check against a known answer.

## 4. Test Philosophy

Use one common chamber profile for all four tests. Only the hardware configuration and Jetson power level change between runs.

The technician noted the chamber typically needs about 30 to 40 minutes to reach 10 mbar and -30 C, then roughly another hour to pull down further. That fits a practical quick-screening profile for these four cases, and — per Section 2 — lands the chamber at a condition close to the real ~31 km environment for the bulk of each test's hold.

## 5. Proposed Chamber Profile

Use the same profile for each test unless the chamber has a better verified equivalent.

### 5.0 Client-Supplied Reference Profile

This figure was supplied in the inputs folder and shows the temperature profile we want the technician to use as the reference when setting up the chamber sequence. It is a real measured sounding (0-31 km), which is also the low-altitude data source used to build the 0-40 km reference in Section 2.

![Client-supplied temperature profile](diagrams/temp_profile_0_30km.jpeg)

The chamber test does not need to reproduce the full profile exactly. It needs to capture the same thermal intent within the available 8-hour window: a strong pull-down, a low-pressure hold, and enough dwell to compare the four payload configurations.

### 5.1 Profile Figures

The same chamber profile is shown in both figures below. Figure 1 is the pressure timeline; Figure 2 is the temperature timeline.

![Chamber pressure profile](envisys-tvac-test-plan-jetson-radiators/diagrams/chamber_pressure_profile.svg)

![Chamber temperature profile](envisys-tvac-test-plan-jetson-radiators/diagrams/chamber_temperature_profile.svg)

| Stage | Time from start | Chamber pressure | Chamber temperature | Purpose | Approx. real-altitude equivalent |
| --- | ---: | ---: | ---: | --- | --- |
| 1. Pull-down | 0 to 40 min | Ramp to 10 mbar | Ramp to -30 C | Get the chamber into the cold/vacuum region quickly | Passing through ~7-11 km on temperature, ~31 km on pressure |
| 2. Deep-cold approach | 40 to 100 min | Hold near 10 mbar | Continue lowering to the coldest stable setpoint the chamber can reach, target -40 C or lower if available | Drive the payload toward the limiting cold condition | ~31 km (pressure and temperature together) |
| 3. Final soak | 100 to 120 min | Hold near 10 mbar | Hold at the deepest stable cold setpoint | Capture the comparison data before the next hardware change | ~31 km hold |

If the chamber cannot reliably reach -40 C, use the lowest stable temperature it can maintain and record the actual profile in the log. This will still be at or below the ~31 km-equivalent temperature identified in Section 2, so it remains a valid (if slightly less severe) cold case.

## 6. Test Matrix

| Test | Hardware configuration | Jetson load | Chamber profile | Notes |
| --- | --- | ---: | --- | --- |
| 1 | Both radiators installed | 30 W | Shared profile above | Highest-load check on the full-radiator build. Compare against Section 3's simulated benchmark. |
| 2 | Both radiators installed | 10 W | Shared profile above | Lower-load check on the full-radiator build. No CFD reference exists — new data. |
| 3 | Single radiator installed | 10 W | Shared profile above | Lower-stress case for the single-radiator build. No CFD reference exists — new data. |
| 4 | Single radiator installed | 30 W | Shared profile above | Highest-stress case and the key risk case. No CFD reference exists — new data. |

Recommended order is 1 -> 2 -> 3 -> 4 so the full-radiator 30 W and 10 W cases are verified first (and checked against the Section 3 benchmark while the setup is fresh), then the more severe single-radiator configuration.

## 7. 8-Hour Execution Plan

This schedule assumes each test uses about 2 hours including pull-down, soak, and a short configuration changeover.

| Window | Activity |
| --- | --- |
| 0:00 to 2:00 | Test 1: 30 W, both radiators |
| 2:00 to 2:10 | Changeover and logging review |
| 2:10 to 4:10 | Test 2: 10 W, both radiators |
| 4:10 to 4:20 | Changeover and logging review |
| 4:20 to 6:20 | Test 3: 10 W, single radiator |
| 6:20 to 6:30 | Changeover and logging review |
| 6:30 to 8:00 | Test 4: 30 W, single radiator |

If the chamber pull-down runs slower than expected, shorten the final soak on the earlier cases and preserve the last case, since the 30 W single-radiator test is the most demanding one.

## 8. What To Record For Each Test

Please capture the following for every run:

- Chamber pressure versus time
- Chamber temperature versus time
- Jetson temperature versus time
- Radiator temperature versus time
- Start and end timestamps for the test
- Any control notes during changeover or hold

Recommended logging interval: 30 to 60 seconds.

For Test 1, also flag if the Jetson or interface-plate temperature crosses roughly 70-80 C during the hold — that is the simulated range from Section 3, so anything well outside it (either direction) is worth a note even if the test otherwise runs clean.

## 9. Technician Notes

- Keep the same chamber profile for all four tests so the only variables are load and radiator count.
- Confirm whether the chamber temperature should be held at the lowest stable setpoint or stepped in stages below -30 C; either is acceptable as long as the actual profile is logged.
- If a configuration change requires extra time, preserve the 30 W single-radiator case as the final priority case.
- If the chamber can only hold one low setpoint, do not overcomplicate the profile - the useful part of the test is the cold-vacuum exposure, not an exact flight-time match.
- The chamber's achievable vacuum (~10 mbar) represents roughly 31 km, not the full 40 km flight ceiling (~2.9 mbar) — see Section 2. If time allows on Test 4's final soak only, pulling toward 3-5 mbar gets closer to the true 40 km pressure, but do not do this on Tests 1-3 since it would break the common-profile comparison.

## 10. Suggested Outcome

At the end of the 8-hour window, we should have a direct comparison of the four combinations under a consistent cold-vacuum profile, enough to identify whether the second radiator materially reduces Jetson temperature and whether the single-radiator setup is acceptable at 10 W and 30 W. Test 1's result also gives a first real-hardware check against the Section 3 simulation, which should inform how much confidence to place in the CFD model for the three untested (10 W and single-radiator) configurations going forward.
