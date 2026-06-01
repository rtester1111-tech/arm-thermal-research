# gem5 Bug: ThermalModel Intermediate Node Initialized to 0 K

## One-Line Summary

`ThermalModel::startup()` never initializes intermediate RC-network nodes, leaving
them at 0 K (−273.15 °C). This creates a spurious absolute-zero heat sink in the
first Backward Euler step, driving die temperature far below ambient despite
positive CPU power input.

## Quick Repro

```bash
bash reproduce.sh
# Expected anomalous output: Junction temp drops 25°C → ~12°C
```

See [`expected_vs_observed.md`](expected_vs_observed.md) for a 4-way numerical comparison.
Apply [`gem5_thermal_fix.patch`](../../gem5_thermal_fix.patch) to fix.

---

## Affected Versions

All gem5 versions supporting multi-node thermal networks.
The `temp(0.0f)` constructor default has been unchanged since thermal model introduction (2017).
**Confirmed on gem5 25.1.0.1 stable.**

---

## Symptom

Configure a 2-node Cauer RC thermal network in gem5 FS mode with ~3 W CPU power:

```
Expected: Junction temp rises from 25°C toward steady-state (~28°C)
Observed: Junction temp drops 25°C → 12.34°C (physically impossible cooling)
```

The temperature drop is sustained for several thermal time-constant periods (τ_die = C·R ≈ 5 s),
then slowly recovers — but by then the simulation window may have ended.

---

## Root Cause

### 1. `ThermalNode` constructor defaults to 0 K

```cpp
// src/sim/power/thermal_node.cc
ThermalNode::ThermalNode(const ThermalNodeParams &p)
    : SimObject(p), id(-1), isref(false), temp(0.0f)  // ← 0 K = −273.15 °C
{}
```

`Temperature(0.0f)` stores 0 Kelvin, not 0 Celsius.

### 2. `ThermalModel::startup()` only initializes two categories of nodes

```cpp
// src/sim/power/thermal_model.cc — startup()
for (auto ref : references)
    ref->node->temp = ref->_temperature;        // ThermalReference nodes ✓

for (auto dom : domains)
    dom->getNode()->temp = dom->initialTemperature();  // ThermalDomain nodes ✓

// Intermediate nodes are added to eq_nodes here but NEVER initialized → remain at 0 K ✗
for (auto n : nodes) { ... eq_nodes.push_back(n); }
```

Any node that is neither a `ThermalReference` nor directly owned by a `ThermalDomain`
(e.g., the structural Package node in a Cauer 2-node RC network) is silently skipped.

### 3. First `doStep()` injects a massive spurious heat sink

```cpp
// ThermalCapacitor::getEquation() — Backward Euler discretization
eq[eq.cnt()] += _capacitance / step *
    (node1->temp - node2->temp).toKelvin();   // node_pkg->temp = 0 K here
```

With `node_pkg->temp = 0 K`, the capacitor's constant term acts as if a −273.15 °C
reservoir is connected to the intermediate node. The resulting spurious current pulls
die temperature below ambient on the very first solver step. The error decays at rate
`exp(-t/τ_pkg)` — for τ_pkg = C_pkg·(R1+R2) = 5·15 = 75 s, it persists for minutes.

---

## Network Topology

```
P_heat → [node_die] ──R1=5──  [node_pkg] ──R2=10── [node_amb=25°C, fixed]
               |                    |
             C1=1               C2=5 ← NOT initialized by startup()
               |                    |
           [node_amb]           [node_amb]
```

Parameters used in this research:
- R1 (die→pkg): 5.0 K/W
- R2 (pkg→amb): 10.0 K/W
- C1 (die capacitance): 1.0 J/K  → τ_die = C1·R1 = 5 s
- C2 (pkg capacitance): 5.0 J/K  → τ_pkg = C2·(R1+R2) = 75 s
- T_amb: 298.15 K (25°C)

---

## Fix

```diff
--- a/src/sim/power/thermal_model.cc
+++ b/src/sim/power/thermal_model.cc
@@ -205,6 +205,22 @@ ThermalModel::startup()
     for (unsigned i = 0; i < eq_nodes.size(); i++)
         eq_nodes[i]->id = i;

+    // Initialize intermediate nodes to ambient. Without this they retain
+    // 0 K from ThermalNode's constructor, acting as an absolute-zero heat
+    // sink in the first Backward Euler step.
+    if (!references.empty()) {
+        const Temperature ambient = references[0]->_temperature;
+        for (auto n : eq_nodes) {
+            if (n->temp.toKelvin() < 1.0)
+                n->temp = ambient;
+        }
+    }
+
     // Schedule first thermal update
     schedule(stepEvent, curTick() + sim_clock::as_int::s * _step);
 }
```

Full patch: [`../../gem5_thermal_fix.patch`](../../gem5_thermal_fix.patch)

---

## Verification

Independent Python Backward Euler solver with identical RC parameters:

| Scenario | Initial `node_pkg` | Final die temp | Match? |
|---|---|---|---|
| **Case A (Bug)** | 0 K (−273.15°C) | **12.29°C** | gem5 observed: 12.34°C — deviation **0.05°C** ✓ |
| **Case B (Fixed)** | 298.15 K (25°C) | **25.03°C** | Physically correct warming ✓ |
| **gem5 patched run** | 298.15 K (25°C) | **28.71°C** | Steady-state after 52 s sim ✓ |

Three independent proofs:
1. Source code white-box analysis
2. gem5 simulation observation (12.34°C)
3. Independent Python solver reproduction (12.29°C, Δ = 0.05°C)

Solver: [`../../validation/implicit_solver/implicit_solver.py`](../../validation/implicit_solver/implicit_solver.py)
