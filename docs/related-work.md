# Related Work

## Thermal Modeling Tools

### HotSpot
- **What it is:** Compact thermal model for processor floorplan-level analysis.
  Uses a grid of RC elements mapped to physical die regions (functional units,
  heat spreader, heat sink layers).
- **Difference from this work:** HotSpot operates at floorplan granularity and
  models spatial temperature distribution. Our Cauer 2-node model is spatially
  lumped (one temperature per layer) — equivalent to HotSpot collapsed to a
  single tile. HotSpot would show hot spots within the die; our model shows
  only the average junction temperature.
- **Relevance:** The RC parameters we use (R₁=5 K/W, R₂=10 K/W) are consistent
  with HotSpot's default values for a medium-sized ARM SoC die without a heat
  sink. A HotSpot run could serve as an external calibration target for Phase 7.
- **gem5 integration:** gem5's thermal model uses the same Cauer RC concept as
  HotSpot's package-level model. The bug we found would affect any multi-node
  Cauer network in gem5, equivalent to HotSpot's multi-layer thermal stack.

### McPAT (Multi-core Power, Area, and Timing)
- **What it is:** Analytical power model for processor microarchitectures, driven
  by gem5 activity counters (instruction mix, cache hit rates, branch outcomes).
- **Difference from this work:** McPAT produces power estimates per functional unit.
  Our power model (`P = V² × 3.0 × IPC`) is a single-equation approximation that
  uses IPC as a proxy for activity, losing per-unit breakdown.
- **Relevance:** A full McPAT integration would replace our IPC-based power model
  with per-unit power, improving accuracy during OPP transitions and providing
  separate static/dynamic breakdowns per pipeline stage.
- **Limitation acknowledged:** The current model underestimates power during
  frequency transitions because IPC doesn't capture the voltage-squared factor
  changing across OPP points. This is documented in `docs/limitations.md`.

### DVFS Governor Literature
- **schedutil (Linux mainline):** Reactive governor that scales frequency based on
  CPU utilization at scheduler tick rate (~4 ms). Our "reactive" baseline governor
  corresponds to this behavior.
- **EAS (Energy-Aware Scheduler):** Linux scheduler extension that uses an Energy
  Model (capacity-dmips-mhz + power coefficients) to make scheduling decisions
  that minimize energy while meeting performance targets. Phase 6 studies this.
- **dT/dt predictive governor (this work):** Novel governor that observes the
  thermal derivative to proactively reduce OPP before reaching the throttle
  threshold. Not a standard Linux governor — implemented in Python simulation.

---

## Simulation Infrastructure

### gem5
- **Version used:** 25.1.0.1 stable, ARM FS mode
- **Thermal model origin:** Introduced circa 2017 as `src/sim/power/thermal_model.cc`.
  Based on Cauer RC networks driven by `MathExprPowerModel`.
- **Bug context:** The `ThermalNode` constructor default of `temp(0.0f)` was always
  present. The bug only manifests with ≥2 node networks where an intermediate node
  exists (neither ThermalDomain nor ThermalReference). Single-node configurations
  are unaffected.
- **Related gem5 issue:** The `ThermalCapacitor::getEquation()` function correctly
  implements Backward Euler — the bug is entirely in initialization, not numerics.

### SPICE Equivalent Circuit
The Cauer 2-node RC thermal network has a direct SPICE analog:
- Thermal resistance (K/W) → electrical resistance (Ω)
- Thermal capacitance (J/K) → electrical capacitance (F)
- Power (W) → current source (A)
- Temperature (K) → voltage (V)
- T_ambient (fixed) → ground reference or voltage source

A SPICE netlist reproducing the bug:
```spice
* gem5 Absolute-Zero Bug SPICE equivalent
* Node 1 = die (junction), Node 2 = pkg (intermediate), GND = ambient (25V offset)
I1 GND 1 3.0        ; 3W CPU power = 3A current source
R1 1   2  5         ; R_die_pkg = 5 K/W = 5 Ω
R2 2   GND 10       ; R_pkg_amb = 10 K/W = 10 Ω
C1 1   GND 1        ; C_die = 1 J/K = 1 F, IC=298.15V (25°C + 273.15)
C2 2   GND 5        ; C_pkg = 5 J/K = 5 F, IC=0V ← THE BUG (0K = 0V)
.IC V(1)=298.15 V(2)=0   ; bug: V(2)=0 instead of 298.15
.TRAN 1m 250m             ; 1ms steps, 250ms total
.PROBE V(1) V(2)
.END
```

With `IC V(2)=0`, SPICE would reproduce the 12.34°C anomaly.
With `IC V(2)=298.15`, SPICE would show correct warm-up.
See `validation/crosscheck/spice_crosscheck.md` for full methodology.

---

## ARM Thermal Management Standards

### ACPI Thermal Zones
Linux kernel thermal framework (`CONFIG_THERMAL=y`) implements ACPI-style thermal
zones with trip points (passive, hot, critical). Our work uses gem5's native
`ThermalDomain`/`ThermalModel` which is a lower-level mechanism that feeds into
the same Linux thermal zone infrastructure via MMIO-mapped temperature sensors.

### ARM DynamIQ / big.LITTLE
The Phase 6 EAS study uses a standard ARM big.LITTLE configuration:
- big cluster: 1× Cortex-X4-class (ArmO3CPU, 3.3 GHz)
- little cluster: 1× Cortex-A520-class (MinorCPU, 2.0 GHz)
- Capacity ratio: big=1024, little=540 (matching Linux EAS energy model convention)

EAS uses `capacity-dmips-mhz` from the Device Tree to make scheduling decisions.
Our `scripts/patch_eas_dtb.py` injects these values into gem5's auto-generated DTB.
