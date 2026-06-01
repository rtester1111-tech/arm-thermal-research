# Methodology

## 1. Thermal Model: Cauer 2-Node RC Network

This research uses a **second-order Cauer RC thermal network** to model the
die-to-ambient thermal path of a fanless ARM SoC:

```
P_heat → [node_die] ──R1── [node_pkg] ──R2── [T_amb, fixed]
               |                  |
             C_die             C_pkg
               |                  |
           [T_amb]            [T_amb]
```

### Parameters

| Parameter | Value | Physical meaning |
|---|---|---|
| R_die_pkg (R1) | 5.0 K/W | Thermal resistance: die → package |
| R_pkg_amb (R2) | 10.0 K/W | Thermal resistance: package → ambient |
| C_die (C1) | 1.0 J/K | Thermal capacitance of die |
| C_pkg (C2) | 5.0 J/K | Thermal capacitance of package |
| T_ambient | 25°C (298.15 K) | Fixed ambient reference |

### Derived quantities

- τ_die = C_die × R_die_pkg = 5.0 s
- τ_pkg = C_pkg × (R_die_pkg + R_pkg_amb) = 75.0 s
- R_total = R1 + R2 = 15.0 K/W
- T_steady (at 3W) = T_amb + P × R_total = 25 + 45 = 70°C

### Why Cauer (not Foster)?

Foster RC networks have no physical thermal node corresponding to a real
material boundary. Cauer networks place capacitors to ground at each node,
making intermediate temperatures physically interpretable. This is why gem5
uses the Cauer topology — and why the uninitialized intermediate node bug
has real physical consequences.

### Parameter source

Parameters were derived by curve-fitting to published thermal characterization
data for Cortex-A55/A76-class SoCs (junction-to-case and case-to-ambient
resistances from datasheets). They are representative of the correct order
of magnitude but not calibrated to a specific die. See [`limitations.md`](limitations.md).

---

## 2. Solver Strategy: Backward Euler (Implicit)

The Kirchhoff nodal equations for the 2-node Cauer network are:

**KCL at node_die:**
$$\frac{C_1}{\Delta t}(T_1^{n+1} - T_1^n) = P_\text{heat} - \frac{T_1^{n+1} - T_2^{n+1}}{R_1}$$

**KCL at node_pkg:**
$$\frac{C_2}{\Delta t}(T_2^{n+1} - T_2^n) = \frac{T_1^{n+1} - T_2^{n+1}}{R_1} - \frac{T_2^{n+1} - T_\text{amb}}{R_2}$$

Rearranged into the 2×2 linear system $A \mathbf{T}^{n+1} = \mathbf{b}$:

$$A = \begin{pmatrix} \frac{1}{R_1} + \frac{C_1}{\Delta t} & -\frac{1}{R_1} \\ -\frac{1}{R_1} & \frac{1}{R_1} + \frac{1}{R_2} + \frac{C_2}{\Delta t} \end{pmatrix}$$

$$\mathbf{b} = \begin{pmatrix} P_\text{heat} + \frac{C_1}{\Delta t} T_1^n \\ \frac{T_\text{amb}}{R_2} + \frac{C_2}{\Delta t} T_2^n \end{pmatrix}$$

This is exactly the discretization used in gem5's `ThermalCapacitor::getEquation()`.
Backward Euler is unconditionally stable for this problem, so numerical instability
cannot explain the observed temperature drop — it must be a physical initialization error.

Timestep used: dt = 0.01 s (matching `--thermal-step=0.01` in gem5).

---

## 3. gem5 Configuration

### Simulation pipeline

```
Atomic boot (fast) → checkpoint → Timing O3CPU restore → workload → stats
```

This avoids simulating the multi-second Linux boot in timing mode (which would
take weeks at ~0.7 MIPS gem5 speed).

### Key gem5 parameters

| Parameter | Value | Rationale |
|---|---|---|
| `--cpu-type` | timing | Cycle-accurate for IPC/power measurement |
| `--big-cpu-clock` | 3.3 GHz | Representative Cortex-X4-class OPP |
| `--thermal-step` | 0.01 s | 10 ms thermal timestep |
| `--stats-period` | 0.0002 s | 0.2 ms stats sampling for fine thermal resolution |
| `--machine-type` | VExpress_GEM5_Foundation | Standard AArch64 FS platform |

### Power model

```python
# Dynamic power (MathExprPowerModel in gem5_fs_thermal.py)
P_dynamic = V^2 * 3.0 * IPC   [W]

# Static (leakage) power
P_leak = 0.1 * (T_temp / 300)^2   [W]
```

This uses instantaneous IPC as the activity factor, approximating αCV²f.
Known limitation: underestimates power during OPP transitions.
See [`limitations.md`](limitations.md).

---

## 4. Workloads

### Brightness (memory-bandwidth-bound)
- Operation: pixel-wise brightness multiplication on a 4096×4096 frame
- Implementations: scalar C, NEON 128-bit SIMD, SVE2 256-bit SIMD
- Dominant bottleneck: L2/DRAM bandwidth (stride access pattern)

### 2D IDCT (compute-bound)
- Operation: 8×8 inverse DCT (JPEG baseline block)
- Implementations: scalar C, NEON, SVE2 ACLE intrinsics
- Dominant bottleneck: FP/integer pipeline throughput

These two workloads span the bandwidth/compute spectrum, providing representative
IPC profiles for the thermal power model.

---

## 5. Simulation Speed

gem5 ARM timing mode: ~0.7 MIPS (Million Instructions Per Simulated Second).
This is 4,000× slower than real hardware at 3.3 GHz.
One simulated second of workload requires ~2.8 hours of real-time computation.

For research requiring multi-second simulated time (to observe thermal transients
spanning τ_die = 5 s), this is the primary practical constraint.
