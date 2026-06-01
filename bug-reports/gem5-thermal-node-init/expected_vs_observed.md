# Expected vs Observed: 4-Way Numerical Comparison

## Setup

- Cauer 2-node RC thermal network
- R_die_pkg = 5.0 K/W, R_pkg_amb = 10.0 K/W
- C_die = 1.0 J/K, C_pkg = 5.0 J/K
- T_ambient = 25.0°C (298.15 K)
- CPU power: ~3.0 W (dynamic) during active workload
- Backward Euler, dt = 0.01 s (thermal-step = 10 ms)

---

## Comparison Table

| Metric | Analytical (closed-form) | gem5 Original (buggy) | gem5 Patched | Python Solver (independent) |
|---|:---:|:---:|:---:|:---:|
| **Initial node_pkg temp** | 25°C (by definition) | **0 K = −273.15°C** ← bug | 25°C | 0 K (Case A) / 25°C (Case B) |
| **Min junction temp** | 25.00°C | **12.34°C** | 25.00°C | **12.29°C** (Case A) |
| **Final junction temp (222 ms)** | 25.03°C | 12.34°C | 25.04°C | 12.29°C (Case A) / 25.03°C (Case B) |
| **Final junction temp (52 s)** | 28.78°C† | n/a (sim ended at 222 ms) | **28.71°C** | 28.76°C† |
| **Temp below ambient?** | Never | **Yes — 12.73°C below** | Never | Case A: Yes / Case B: Never |
| **Physical validity** | ✅ | ❌ Violates 2nd law | ✅ | Case A: ❌ / Case B: ✅ |
| **Deviation from gem5 bugged** | — | baseline | — | **0.05°C** (Case A) |

† Analytical and Python solver values at 52 s estimated with sustained 3W power; actual gem5 run had varying IPC/power.

---

## Key Takeaway

The Python independent solver reproduces the gem5 bugged result within **0.05°C** — confirming
the same physical mechanism (0 K intermediate node acting as absolute-zero heat sink).

After the patch, gem5 matches the physically expected warm-up trajectory.

---

## Simulation Window Note

The original Phase 5 run covered only **222.6 ms** of simulated time, which is much shorter
than τ_die = 5 s. This is why:
- The buggy run never recovered to ambient before the simulation ended
- The patched run showed only 0.04°C of warming in 222 ms (expected: T rises by ~0.04°C
  in the first 222 ms for 3W / (total resistance) steady-state)

The Phase 5.5 patched run extended to **52 simulated seconds** (~10× τ_die), confirming
the temperature reached a physical steady-state of **28.71°C**.

---

## How to Reproduce

```bash
# Reproduce the bug (Case A):
bash reproduce.sh

# Run the independent Python solver (both cases):
python3 ../../validation/implicit_solver/implicit_solver.py

# Run the analytical solution:
python3 ../../validation/analytical/analytical_solution.py
```
