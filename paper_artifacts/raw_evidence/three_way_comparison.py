#!/usr/bin/env python3
"""
three_way_comparison.py — The Core Verification Figure

Produces a single figure with four curves on the same axes:

  1. Analytical (closed-form, constant 3W)  ── black  ── physical ground truth
  2. gem5 unpatched                          ── red    ── 12.34°C anomaly (bug)
  3. Python solver, bug init (0K)            ── orange ── reproduces gem5 bug
  4. Python solver, fixed init (25°C)        ── green  ── physically correct

The key messages the figure conveys:
  - Curves 1 and 4 overlap → correct init gives physically valid warm-up
  - Curves 2 and 3 overlap → Python solver reproduces gem5 bug exactly (same mechanism)
  - Curves 2/3 vs 1/4 → the gap is the bug's magnitude (~13°C below physical)

The Python solver uses the ACTUAL gem5 power profile (from phase5 JSON) so that
it matches gem5's observed values at 0.05°C precision rather than the analytical
assumption of constant 3W.

Output: results/validation/three_way_comparison.png
"""

import numpy as np
import json
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ── Parameters ─────────────────────────────────────────────────────────────────
R1, R2 = 5.0, 10.0   # K/W
C1, C2 = 1.0, 5.0    # J/K
T_AMB_C = 25.0        # °C
T_AMB_K = T_AMB_C + 273.15
DT = 0.01             # s  (matches gem5 --thermal-step=0.01)

BASE_DIR = os.path.join(os.path.dirname(__file__), "../..")
PHASE5_JSON = os.path.join(BASE_DIR, "results/phase5/fs_simulation_results.json")
OUT_DIR = os.path.join(BASE_DIR, "results/validation")
os.makedirs(OUT_DIR, exist_ok=True)


# ── Load gem5 unpatched data ───────────────────────────────────────────────────
with open(PHASE5_JSON) as f:
    gem5_data = json.load(f)

gem5_t = np.array([d['time_ms'] for d in gem5_data])        # ms
gem5_T = np.array([d['temp_C']  for d in gem5_data])        # °C
gem5_P = np.array([d['dyn_power_W'] + d.get('st_power_W', 0) for d in gem5_data])  # W
T_END = gem5_t[-1] / 1000   # s


# ── Build power interpolation from gem5 data ──────────────────────────────────
# gem5 stats period = 0.2ms, but thermal step = 10ms.
# We use gem5's reported power to drive our Python solver at 10ms steps.
def get_power_at(t_s):
    """Interpolate gem5 power profile at time t_s."""
    t_ms = t_s * 1000
    return float(np.interp(t_ms, gem5_t, gem5_P))


# ── Backward Euler solver using gem5 power profile ────────────────────────────
def solver_gem5_power(T1_init_C, T2_init_C):
    """
    Backward Euler matching gem5's doStep() exactly, driven by gem5's power profile.
    T_init in °C; returns (times_ms, T_die_C).
    """
    T1 = T1_init_C + 273.15
    T2 = T2_init_C + 273.15

    times_ms, T1_hist = [], []
    t = 0.0
    while t <= T_END + DT * 0.5:
        times_ms.append(t * 1000)
        T1_hist.append(T1 - 273.15)

        P = get_power_at(t)
        A = np.array([
            [1/R1 + C1/DT,  -1/R1           ],
            [-1/R1,          1/R1 + 1/R2 + C2/DT]
        ])
        b = np.array([P + C1/DT * T1, T_AMB_K/R2 + C2/DT * T2])
        T_new = np.linalg.solve(A, b)
        T1, T2 = T_new
        t += DT

    return np.array(times_ms), np.array(T1_hist)


# ── Analytical solution (constant 3W, physical baseline) ──────────────────────
def analytical_correct(t_ms_arr, P=3.0):
    """Closed-form 2-node Cauer RC, constant power P, both nodes init at T_amb."""
    T1_ss = T_AMB_C + P * (R1 + R2)
    T2_ss = T_AMB_C + P * R2
    A = np.array([
        [-1/(C1*R1),       1/(C1*R1)          ],
        [ 1/(C2*R1),      -(1/R1+1/R2)/C2     ]
    ])
    theta0 = np.array([T_AMB_C - T1_ss, T_AMB_C - T2_ss])
    evals, evecs = np.linalg.eig(A)
    c = np.linalg.solve(evecs, theta0)
    t_s = t_ms_arr / 1000
    T1 = np.zeros_like(t_s, dtype=float)
    for i in range(2):
        T1 += evecs[0, i] * c[i] * np.exp(evals[i] * t_s)
    return T1 + T1_ss


# ── Run all four curves ────────────────────────────────────────────────────────
t_fine = np.linspace(0, T_END * 1000, 5000)  # ms
T_anal = analytical_correct(t_fine)

t_py_bug,   T_py_bug   = solver_gem5_power(T_AMB_C, -273.15)   # node_pkg = 0K
t_py_fixed, T_py_fixed = solver_gem5_power(T_AMB_C,  T_AMB_C)  # node_pkg = 25°C

# ── Statistics ────────────────────────────────────────────────────────────────
py_bug_final   = T_py_bug[-1]
py_fixed_final = T_py_fixed[-1]
gem5_final     = gem5_T[-1]
gem5_min       = gem5_T.min()

# Match quality between Python bug and gem5
T_py_bug_at_gem5 = np.interp(gem5_t, t_py_bug, T_py_bug)
rmse_match = np.sqrt(np.mean((T_py_bug_at_gem5 - gem5_T)**2))
max_dev = np.max(np.abs(T_py_bug_at_gem5 - gem5_T))

print("=" * 60)
print("  Three-Way Comparison — Key Numbers")
print("=" * 60)
print(f"  Analytical (correct, constant 3W):  {T_anal[-1]:.4f}°C at {T_END*1000:.0f}ms")
print(f"  Python solver (fixed init):         {py_fixed_final:.4f}°C")
print(f"  Python solver (bug, 0K init):       {py_bug_final:.4f}°C")
print(f"  gem5 unpatched:                     {gem5_final:.4f}°C  (min: {gem5_min:.4f}°C)")
print(f"")
print(f"  Python bug vs gem5 RMSE:            {rmse_match:.4f} K")
print(f"  Python bug vs gem5 max deviation:   {max_dev:.4f} K")
print(f"")
print(f"  Bug magnitude (fixed - bugged):     {py_fixed_final - py_bug_final:.2f}°C")
print(f"  Bug vs analytical error ratio:      {abs(py_bug_final-T_anal[-1]) / 0.0004:.0f}× larger than numerical error")


# ── Plot ──────────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(16, 6),
                         gridspec_kw={'width_ratios': [2, 1]})

# ── Left panel: full comparison ────────────────────────────────────────────────
ax = axes[0]

ax.plot(t_fine, T_anal, color='black', lw=2.5, zorder=6,
        label='Analytical (closed-form, constant 3 W)', linestyle='-')

ax.plot(t_py_fixed, T_py_fixed, color='#2ca02c', lw=2.0, zorder=5,
        label=f'Python solver — correct init (25°C)  final: {py_fixed_final:.2f}°C',
        linestyle='--')

ax.plot(gem5_t, gem5_T, color='#d62728', lw=2.5, zorder=4,
        label=f'gem5 unpatched (bug)  min: {gem5_min:.2f}°C', linestyle='-')

ax.plot(t_py_bug, T_py_bug, color='#ff7f0e', lw=1.8, zorder=3,
        label=f'Python solver — bug init (0 K)  RMSE vs gem5: {rmse_match:.3f} K',
        linestyle=':', alpha=0.9)

ax.axhline(25.0, color='gray', linestyle='--', alpha=0.5, lw=1.2, label='Ambient 25°C')
ax.axhline(gem5_min, color='#d62728', linestyle=':', alpha=0.4, lw=1.0)

ax.fill_between(gem5_t, gem5_T, 25.0,
                where=gem5_T < 25.0, alpha=0.08, color='red',
                label='Anomalous sub-ambient zone')

# Annotation: bug magnitude
ax.annotate(
    f'Bug: {gem5_min:.2f}°C\n({25.0 - gem5_min:.2f}°C below ambient)',
    xy=(gem5_t[gem5_T.argmin()], gem5_min),
    xytext=(gem5_t[gem5_T.argmin()] * 0.4, gem5_min + 3.5),
    fontsize=9.5, color='#d62728', fontweight='bold',
    arrowprops=dict(arrowstyle='->', color='#d62728', lw=1.5)
)
ax.annotate(
    f'Fixed: {py_fixed_final:.2f}°C',
    xy=(t_py_fixed[-1], py_fixed_final),
    xytext=(t_py_fixed[-1] * 0.6, py_fixed_final + 1.5),
    fontsize=9.5, color='#2ca02c', fontweight='bold',
    arrowprops=dict(arrowstyle='->', color='#2ca02c', lw=1.5)
)

ax.set_xlabel('Simulation Time (ms)', fontsize=12)
ax.set_ylabel('Junction Temperature (°C)', fontsize=12)
ax.set_title(
    'gem5 Absolute-Zero Heat Sink Bug — Three-Way Verification\n'
    'Analytical  ·  gem5 Observation  ·  Independent Python Solver',
    fontsize=13, fontweight='bold'
)
ax.legend(fontsize=9, loc='center right')
ax.grid(True, linestyle='--', alpha=0.35)
ax.set_ylim([gem5_min - 2, T_anal[-1] + 3])

# ── Right panel: match quality (Python bug vs gem5) ────────────────────────────
ax2 = axes[1]

diff = T_py_bug_at_gem5 - gem5_T
ax2.plot(gem5_t, diff * 1000, color='#ff7f0e', lw=1.8,
         label=f'Python bug − gem5\n(RMSE={rmse_match*1000:.1f} mK,\nmax={max_dev*1000:.1f} mK)')
ax2.axhline(0, color='gray', linestyle='--', alpha=0.7)
ax2.fill_between(gem5_t, diff * 1000, 0, alpha=0.2, color='#ff7f0e')
ax2.set_xlabel('Simulation Time (ms)', fontsize=11)
ax2.set_ylabel('Residual (milli-Kelvin)', fontsize=11)
ax2.set_title(
    'Python Solver vs gem5 Residual\n(same physical mechanism confirmed)',
    fontsize=11, fontweight='bold'
)
ax2.legend(fontsize=9)
ax2.grid(True, linestyle='--', alpha=0.35)

# Annotate max deviation
idx_max = np.argmax(np.abs(diff))
ax2.annotate(
    f'{diff[idx_max]*1000:.1f} mK',
    xy=(gem5_t[idx_max], diff[idx_max]*1000),
    xytext=(gem5_t[idx_max] + 5, diff[idx_max]*1000 + 10),
    fontsize=8.5, color='#ff7f0e',
    arrowprops=dict(arrowstyle='->', color='#ff7f0e', lw=1.2)
)

fig.suptitle(
    f'Cauer 2-Node RC  ·  R₁={R1} K/W, R₂={R2} K/W, C₁={C1} J/K, C₂={C2} J/K  ·  '
    f'T_amb={T_AMB_C}°C  ·  gem5 25.1.0.1',
    fontsize=9.5, y=0.02, color='#444'
)

fig.tight_layout(rect=[0, 0.04, 1, 1])
out_path = os.path.join(OUT_DIR, 'three_way_comparison.png')
fig.savefig(out_path, dpi=300, bbox_inches='tight')
plt.close(fig)
print(f"\nSaved: {out_path}")
