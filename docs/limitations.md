# Model Limitations and Future Work

This document honestly describes the boundaries of the current models and what
would need to change to make each claim stronger.

---

## 1. Thermal RC Parameter Source

**Current state:** R and C values were derived by curve-fitting to published
thermal characterization data for Cortex-A55/A76-class SoCs. They represent
the correct order of magnitude but are not calibrated to a specific physical die.

**What this means for results:**
- The *steady-state temperature* (28.7°C at 3W) is model-specific, not a
  measurement of real hardware
- The *bug discovery* (0 K intermediate node) is valid independent of parameter
  values — any non-zero C_pkg would produce unphysical cooling from a 0 K initial
  condition

**What would strengthen it:**
- Calibrate against a real device's thermal measurements (e.g., die temperature
  sensor readings under controlled load)
- Compare against HotSpot or a SPICE equivalent circuit with the same topology

---

## 2. One-Dimensional Thermal Model

**Current state:** The Cauer 2-node RC network is a spatially lumped (0D/1D)
model. It captures the junction-to-ambient thermal impedance path but not:
- Lateral heat spreading within the die
- Hot-spot formation in specific functional units
- Package-level thermal gradients

**What this means for results:**
- The model is appropriate for chip-level average junction temperature
- It cannot predict hot spots or spatial temperature distribution
- It is the same level of abstraction used by gem5's thermal model itself,
  so comparisons between Python solver and gem5 are internally consistent

**What would strengthen it:**
- Finite-element method (FEM) simulation as an external ground truth
- Multi-node RC (3+ nodes) to capture package/heatsink layers

---

## 3. Power Model Simplification

**Current state:**
```python
P_dynamic = V^2 * 3.0 * IPC   # uses IPC as activity factor
P_leak = 0.1 * (T_temp / 300)^2
```

This approximates αCV²f by substituting IPC for the activity factor, which:
- Underestimates power during OPP transitions (when V changes but IPC lags)
- Does not model memory-access-driven power variation (DRAM refresh, IO)
- Uses a simplified quadratic leakage model instead of Arrhenius exponential
  (the Python `thermal_governor.py` uses a more accurate Arrhenius model)

**What would strengthen it:**
- McPAT-calibrated power model using gem5 activity counters
- Separate models for integer, FP, and memory subsystem power

---

## 4. Workload Representativeness

**Current state:** Brightness (memory-bound) and IDCT (compute-bound) are
synthetic microbenchmarks, not real application workloads.

**What this means for results:**
- IPC and power measurements are clean and reproducible
- Real workloads (video decode, gaming) have more variable IPC profiles
- The 25% energy reduction claim is specific to these workloads and this governor;
  it would need re-evaluation for real applications

**What would strengthen it:**
- Use SPEC CPU 2017 or MiBench workloads in gem5
- Measure thermal signatures across a wider workload set

---

## 5. gem5 Simulation Fidelity

**Current state:** gem5 ARM Timing O3CPU models microarchitecture-level
pipeline behavior but with caveats:
- Cache hierarchy is modeled but memory controller timing is simplified
- DVFS transitions are instantaneous in the model (no PLL lock delay)
- The thermal model runs as a separate fixed-step ODE solver, not cycle-coupled

**What this means for results:**
- IPC numbers are cycle-accurate within gem5's microarchitecture model
- They may differ from real hardware by 10–30% due to prefetcher differences,
  branch predictor accuracy, and memory timing
- The thermal-frequency feedback loop does not model PLL transition latency

---

## 6. The "25% Energy Reduction" Claim

**Precise conditions:**
- Workload: 2D IDCT (compute-bound), 1M 8×8 blocks
- Governor: Predictive (dT/dt-based), max thermal setpoint 85°C
- Thermal params: R_total=15 K/W, C_die=1 J/K, ambient=25°C
- Comparison baseline: reactive (on-throttle) governor
- Metric: total energy-delay product (EDP = Energy / mean FPS)

This number should not be extrapolated to:
- Different workloads, ambient temperatures, or SoC thermal profiles
- Real hardware (this is a simulation result)

---

## 7. gem5 Bug Report Status

The Absolute-Zero Heat Sink Bug patch has been:
- Applied locally to this gem5 build ✓
- Submitted to gem5 Gerrit for upstream review

Status as of 2026-05-24: pending upstream review.
The patch is a conservative fix (only initializes nodes with temp < 1 K to ambient)
that should be safe for all existing thermal configurations.
