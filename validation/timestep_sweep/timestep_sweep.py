#!/usr/bin/env python3
"""
timestep_sweep.py — Timestep Convergence Analysis for Backward Euler Solver

Sweeps dt across [1e-6, 1e-5, 1e-4, 1e-3, 0.01] seconds and computes RMSE
against the closed-form analytical solution for each timestep.

Purpose:
  - Proves the Backward Euler solver converges to the analytical solution
  - Demonstrates the bug is NOT caused by numerical instability
  - Shows that dt = 0.01 s (gem5 default --thermal-step=0.01) is sufficiently
    accurate for the thermal dynamics of interest

Output:
  results/validation/timestep_sweep_convergence.png
  results/validation/timestep_sweep_results.json
"""

import numpy as np
import json
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ── Parameters ─────────────────────────────────────────────────────────────────
R1, R2 = 5.0, 10.0   # K/W
C1, C2 = 1.0, 5.0    # J/K
T_AMB = 25.0          # °C
P = 3.0               # W

T_END = 0.250         # s  (Phase 5 window)

DT_SWEEP = [1e-6, 1e-5, 1e-4, 1e-3, 0.01]
DT_REFERENCE = 1e-7   # s  (reference for "true" numerical solution)

OUT_DIR = os.path.join(os.path.dirname(__file__), "../../results/validation")
os.makedirs(OUT_DIR, exist_ok=True)


def backward_euler(t_end, dt, T1_init=T_AMB, T2_init=T_AMB, P=P):
    """Backward Euler solver matching gem5's ThermalCapacitor::getEquation()."""
    T1 = T1_init + 273.15
    T2 = T2_init + 273.15
    T_amb_K = T_AMB + 273.15

    times, T1_hist = [], []
    t = 0.0
    while t <= t_end + dt * 0.5:
        times.append(t)
        T1_hist.append(T1 - 273.15)
        A = np.array([
            [1/R1 + C1/dt,  -1/R1           ],
            [-1/R1,          1/R1 + 1/R2 + C2/dt]
        ])
        b = np.array([P + C1/dt * T1, T_amb_K/R2 + C2/dt * T2])
        T_new = np.linalg.solve(A, b)
        T1, T2 = T_new
        t += dt

    return np.array(times), np.array(T1_hist)


def two_node_analytical(t_arr, T0_die=T_AMB, T0_pkg=T_AMB, P=P):
    """Closed-form 2-node solution via eigenvalue decomposition."""
    T1_ss = T_AMB + P * (R1 + R2)
    T2_ss = T_AMB + P * R2

    A = np.array([
        [-1/(C1*R1),          1/(C1*R1)           ],
        [ 1/(C2*R1),         -(1/R1 + 1/R2)/C2    ]
    ])
    theta0 = np.array([T0_die - T1_ss, T0_pkg - T2_ss])
    eigenvalues, eigenvectors = np.linalg.eig(A)
    c = np.linalg.solve(eigenvectors, theta0)

    T1 = np.zeros_like(t_arr)
    for i in range(2):
        T1 += eigenvectors[0, i] * c[i] * np.exp(eigenvalues[i] * t_arr)
    return T1 + T1_ss


def compute_rmse(t_ref, T_ref, t_test, T_test):
    """Interpolate T_test onto t_ref grid and compute RMSE."""
    T_interp = np.interp(t_ref, t_test, T_test)
    return np.sqrt(np.mean((T_ref - T_interp) ** 2))


def main():
    # Reference: fine-grid analytical solution
    t_ref = np.linspace(0, T_END, int(T_END / 1e-5) + 1)
    T_anal = two_node_analytical(t_ref)

    print(f"{'dt (s)':<12} {'RMSE (K)':<14} {'Peak error (K)':<18} {'Order'}")
    print("-" * 58)

    results = []
    rmse_prev = None
    dt_prev = None

    for dt in DT_SWEEP:
        t_num, T_num = backward_euler(T_END, dt)
        rmse = compute_rmse(t_ref, T_anal, t_num, T_num)
        T_interp = np.interp(t_ref, t_num, T_num)
        peak_err = np.max(np.abs(T_anal - T_interp))

        order = None
        if rmse_prev is not None and rmse > 0 and rmse_prev > 0:
            order = np.log10(rmse / rmse_prev) / np.log10(dt / dt_prev)

        order_str = f"{order:.2f}" if order is not None else "—"
        print(f"{dt:<12.1e} {rmse:<14.6f} {peak_err:<18.6f} {order_str}")

        results.append({
            "dt": dt,
            "rmse_K": round(rmse, 8),
            "peak_error_K": round(peak_err, 8),
            "convergence_order": round(order, 3) if order else None
        })
        rmse_prev = rmse
        dt_prev = dt

    # Also compute RMSE for the BUG case at gem5 default dt
    _, T_bug = backward_euler(T_END, 0.01, T2_init=-273.15)
    rmse_bug = compute_rmse(t_ref, T_anal, np.linspace(0, T_END, len(T_bug)), T_bug)
    print(f"\nBug case (dt=0.01, node_pkg=0K): RMSE = {rmse_bug:.4f} K")
    print(f"  This shows the bug dominates over numerical error by ~{rmse_bug/results[-1]['rmse_K']:.0f}×")

    # Save JSON
    with open(os.path.join(OUT_DIR, 'timestep_sweep_results.json'), 'w') as f:
        json.dump({"sweep": results, "bug_rmse_K": round(rmse_bug, 4)}, f, indent=2)
    print(f"\nJSON: {OUT_DIR}/timestep_sweep_results.json")

    # ── Convergence plot ───────────────────────────────────────────────────────
    dts = [r['dt'] for r in results]
    rmses = [r['rmse_K'] for r in results]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Left: convergence curve
    ax = axes[0]
    ax.loglog(dts, rmses, 'o-', color='steelblue', lw=2, markersize=8,
              label='Backward Euler RMSE vs analytical')
    # First-order reference line
    ref_line = [rmses[-1] * (dt / dts[-1]) for dt in dts]
    ax.loglog(dts, ref_line, 'k--', alpha=0.5, label='1st-order reference (slope=1)')
    ax.axhline(rmse_bug, color='crimson', linestyle=':', lw=2,
               label=f'Bug RMSE at dt=0.01 ({rmse_bug:.3f} K)')
    ax.set_xlabel('Timestep dt (s)')
    ax.set_ylabel('RMSE vs Analytical (K)')
    ax.set_title('Timestep Convergence: Backward Euler\nProves solver converges; bug is NOT numerical instability')
    ax.legend(fontsize=9)
    ax.grid(True, which='both', linestyle='--', alpha=0.4)

    # Right: temperature traces comparison
    ax2 = axes[1]
    ax2.plot(t_ref * 1000, T_anal, 'k-', lw=2.5, label='Analytical (reference)', zorder=5)
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    for i, (dt, col) in enumerate(zip([1e-5, 1e-4, 0.01], colors)):
        t_n, T_n = backward_euler(T_END, dt)
        ax2.plot(t_n * 1000, T_n, '--', color=col, lw=1.5, alpha=0.8,
                 label=f'BE dt={dt:.0e} s')
    _, T_bug_trace = backward_euler(T_END, 0.01, T2_init=-273.15)
    t_bug_trace = np.linspace(0, T_END, len(T_bug_trace))
    ax2.plot(t_bug_trace * 1000, T_bug_trace, color='crimson', lw=2,
             label='BE dt=0.01 s, bug (node_pkg=0K)')
    ax2.axhline(25.0, color='gray', linestyle='--', alpha=0.5)
    ax2.set_xlabel('Time (ms)')
    ax2.set_ylabel('Junction Temperature (°C)')
    ax2.set_title('Temperature Traces: Various dt Values\n(correct init vs bug init)')
    ax2.legend(fontsize=8)
    ax2.grid(True, linestyle='--', alpha=0.4)

    fig.tight_layout()
    out_path = os.path.join(OUT_DIR, 'timestep_sweep_convergence.png')
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print(f"Plot: {out_path}")


if __name__ == '__main__':
    main()
