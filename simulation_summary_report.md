# Balloon Payload CHT Setup Report

## Case Summary

- Study name: Balloon Payload Thermal Model
- Objective: Evaluate steady-state heat rejection from the payload to the environment and confirm that the thermal path remains within acceptable limits.
- Solver: chtMultiRegionSimpleFoam
- Time regime: Steady-state
- Units: SI units, temperatures in K, heat flux in W, distances in m

## Geometry and Regions

- Geometry source: Multi-region assembly with payload, copper strap, radiator plate, foam insulation, and mounting interfaces.
- Regions:
  - jetson_ttp_plate
  - copper_strap
  - radiator_plate
  - radiator_plate_2
  - foam_insulation
  - mounting_brackets
- Mesh requirements:
  - Conformal mesh across all solid regions
  - Fine refinement near heat source and contact interfaces
  - Surface mesh suitable for radiation and thermal contact treatment

## Material Definitions

- Aluminum 6061
  - Density: 2700 kg/m^3
  - Specific heat: 896 J/kg/K
  - Thermal conductivity: 167 W/m/K
- Copper
  - Density: 8960 kg/m^3
  - Specific heat: 385 J/kg/K
  - Thermal conductivity: 390 W/m/K
- EPS Foam
  - Density: 1021 kg/m^3
  - Specific heat: 1300 J/kg/K
  - Thermal conductivity: 0.033 W/m/K

## Boundary Conditions

The following boundary conditions are required to run the model.

### Thermal Load

- Patch: Jetson Heat Source
- Type: Heat flux
- Value: 37.5 W total heat input
- Application: Applied over the jetson thermal interface region

### Environment / Radiation

- Patch: Radiator Outer Faces
- Type: Altitude environment / radiation-to-ambient
- Value: emissivity = 0.85, ambient temperature = 193.15 K
- Notes: Use the high-altitude environment model for the external radiator surfaces.

- Patch: Foam Outer Faces
- Type: Altitude environment / radiation-to-ambient
- Value: emissivity = 0.90, ambient temperature = 193.15 K
- Notes: Used to represent the external insulation surfaces exposed to the environment.

### Thermal Contacts

- Interface: jetson_plate ↔ copper_strap
- Type: Thermal contact resistance
- Value: PTM / indium foil contact resistance

- Interface: copper_strap ↔ radiator_bracket
- Type: Thermal contact resistance
- Value: bolted joint contact resistance

## Initial Conditions

- Initial solid temperature: 293.15 K
- Initial fluid temperature (if a fluid region is included): 193.15 K
- Initial pressure: 1.0e5 Pa or case-specific atmospheric pressure
- Initial velocity: 0 m/s for the solid-only baseline case

## Solver Configuration

- Solver name: chtMultiRegionSimpleFoam
- Physics: Conduction + convection + radiation
- State: Steady-state
- Number of iterations: 500
- Number of processors: 4
- Relaxation settings: Use solver defaults unless a stability issue requires adjustment
- Residual targets: Apply convergence criteria appropriate to the selected solver and case tolerance

## Execution Checklist

1. Import the multi-part geometry and assign all regions.
2. Assign the material properties listed above.
3. Apply all boundary conditions listed in this report.
4. Set initial conditions and solver controls.
5. Run the case and review temperature, heat-flux, and energy-balance results.

## Notes and Assumptions

- Radiation is the dominant heat rejection path at high altitude.
- Convection is weak at 30 km and should be treated consistently with the selected environment model.
- The foam region primarily acts as insulation and should not be treated as the main heat path.
