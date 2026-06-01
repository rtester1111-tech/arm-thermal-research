#!/usr/bin/env python3
"""
analytical_solution.py — Closed-Form Analytical Solution for Cauer 2-Node RC Network

Provides:
  1. Single-node (1st-order) closed-form solution as a clean reference
  2. Two-node (2nd-order) closed-form solution via eigenvalue decomposition
  3. Comparison plot: analytical vs Python Backward Euler vs gem5 results

Used as the ground-truth baseline for:
  - Timestep sweep convergence analysis (validation/timestep_sweep/)
  - Error metric computation (validation/error_metrics/)
  - Three-way comparison figure (validation/crosscheck/)
"""

import numpy as np
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ── Physical parameters (match gem5 config exactly) ───────────────────────────
R1 = 5.0    # K/W  die → pkg
R2 = 10.0   # K/W  pkg → amb
C1 = 1.0    # J/K  die capacitance
C2 = 5.0    # J/K  pkg capacitance
T_AMB = 25.0  # °C
P = 3.0     # W  (representative peak dynamic power)

T_END = 0.250   # s  (covers Phase 5 window of 222.6 ms)
DT_PLOT = 1e-5  # s  (fine grid for smooth analytical curves)

OUT_DIR = os.path.join(os.path.dirname(__file__), "../../results/validation")
os.makedirs(OUT_DIR, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Single-node closed-form (1st-order RC)
# ══════════════════════════════════════════════════════════════════════════════

def single_node_analytical(t_arr, T0=T_AMB, P=P, R=R1+R2, C=C1):
    """
    T(t) = T_amb + P*R*(1 - exp(-t/τ)) + (T0 - T_amb)*exp(-t/τ)
    τ = R*C
    """
    tau = R * C
    T_ss = T_AMB + P * R
    return T_ss - (T_ss - T0) * np.exp(-t_arr / tau)


# ══════════════════════════════════════════════════════════════════════════════
# 2. Two-node closed-form (2nd-order Cauer RC)
# ══════════════════════════════════════════════════════════════════════════════

def two_node_analytical(t_arr, T0_die=T_AMB, T0_pkg=T_AMB, P=P):
    """
    Closed-form solution via eigenvalue decomposition of the 2-node system:

    C1*dT1/dt = P - (T1-T2)/R1
    C2*dT2/dt = (T1-T2)/R1 - (T2-T_amb)/R2

    Rewrite as: d/dt [T1-T_amb, T2-T_amb]^T = A*[...] + b
    where A is the thermal conductance matrix (divided by capacitances).

    The steady-state solution satisfies A*T_ss = -b:
      T1_ss = T_amb + P*(R1+R2)
      T2_ss = T_amb + P*R2

    Transient = sum of two exponential modes with eigenvalues of A.
    """
    T_AMB_K = T_AMB + 273.15

    # State matrix (temperatures in °C above ambient)
    # dθ1/dt = P/C1 - θ1/(C1*R1) + θ2/(C1*R1)
    # dθ2/dt = θ1/(C2*R1) - θ2*(1/R1 + 1/R2)/C2
    A = np.array([
        [-1/(C1*R1),          1/(C1*R1)            ],
        [ 1/(C2*R1),         -(1/R1 + 1/R2)/C2     ]
    ])

    # Steady-state (dθ/dt = 0):
    # -θ1_ss/R1 + θ2_ss/R1 = -P/1  ... wait, let me redo
    # Steady state: A*θ_ss = -[P/C1, 0]^T
    b = np.array([-P/C1, 0.0])
    theta_ss = np.linalg.solve(A, -b)  # θ_ss = -A^{-1} * b... careful with sign

    # Actually: A*θ_ss + [P/C1, 0] = 0  →  θ_ss = -A^{-1}*[P/C1, 0]
    # Let's just use physical result:
    T1_ss = T_AMB + P * (R1 + R2)   # °C
    T2_ss = T_AMB + P * R2           # °C

    # Initial conditions (deviations from steady-state)
    theta0 = np.array([T0_die - T1_ss, T0_pkg - T2_ss])

    # Eigendecomposition
    eigenvalues, eigenvectors = np.linalg.eig(A)
    # eigenvalues are negative (stable system)

    # Coefficients: eigenvectors @ diag(c) = theta0
    # c = eigenvectors^{-1} @ theta0
    c = np.linalg.solve(eigenvectors, theta0)

    T1 = np.zeros_like(t_arr)
    T2 = np.zeros_like(t_arr)
    for i in range(2):
        mode = c[i] * np.exp(eigenvalues[i] * t_arr)
        T1 += eigenvectors[0, i] * mode
        T2 += eigenvectors[1, i] * mode

    T1 += T1_ss
    T2 += T2_ss

    return T1, T2


# ══════════════════════════════════════════════════════════════════════════════
# 3. Backward Euler numerical solver (for comparison)
# ══════════════════════════════════════════════════════════════════════════════

def backward_euler(t_end, dt, T1_init=T_AMB, T2_init=T_AMB, P=P):
    """Implicit (Backward Euler) numerical solver — matches gem5's doStep()."""
    T1 = T1_init + 273.15  # K
    T2 = T2_init + 273.15  # K
    T_amb_K = T_AMB + 273.15

    times, T1_hist, T2_hist = [], [], []
    t = 0.0
    while t <= t_end + 1e-12:
        times.append(t)
        T1_hist.append(T1 - 273.15)
        T2_hist.append(T2 - 273.15)

        A = np.array([
            [1/R1 + C1/dt,   -1/R1            ],
            [-1/R1,           1/R1 + 1/R2 + C2/dt]
        ])
        b = np.array([
            P + C1/dt * T1,
            T_amb_K/R2 + C2/dt * T2
        ])
        T_new = np.linalg.solve(A, b)
        T1, T2 = T_new
        t += dt

    return np.array(times), np.array(T1_hist), np.array(T2_hist)


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    t_fine = np.linspace(0, T_END, int(T_END / DT_PLOT) + 1)

    # Analytical (both initial temps at ambient — the correct initial condition)
    T1_anal, T2_anal = two_node_analytical(t_fine)

    # Analytical (bug case: T2_init = -273.15°C = 0 K)
    T1_bug, T2_bug = two_node_analytical(t_fine, T0_pkg=-273.15)

    # Backward Euler (correct init, dt=0.01s matching gem5)
    t_num, T1_num, _ = backward_euler(T_END, dt=0.01)

    # Print steady-state values
    print(f"Steady-state (analytical):")
    print(f"  T_die_ss  = {T_AMB + P*(R1+R2):.2f}°C")
    print(f"  T_pkg_ss  = {T_AMB + P*R2:.2f}°C")
    print(f"  τ_die     = {C1*R1:.1f} s")
    print(f"  τ_pkg     = {C2*(R1+R2):.1f} s")
    print(f"\nAt t = {T_END*1000:.0f} ms (Phase 5 window):")
    print(f"  T_die (correct init): {T1_anal[-1]:.4f}°C")
    print(f"  T_die (bug, 0K init): {T1_bug[-1]:.4f}°C")
    print(f"  T_die (Backward Euler, dt=0.01s): {T1_num[-1]:.4f}°C")
    print(f"  gem5 observed (unpatched): 12.34°C")
    print(f"  Deviation (analytical bug case vs gem5): {abs(T1_bug[-1] - 12.34):.4f}°C")

    # ── Plot ──────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(12, 6))

    ax.plot(t_fine * 1000, T1_anal, color='black', lw=2.5,
            label='Analytical (correct init, 25°C)', zorder=5)
    ax.plot(t_fine * 1000, T1_bug, color='crimson', lw=2.0, linestyle='--',
            label='Analytical (bug: node_pkg = 0 K)', zorder=4)
    ax.plot(t_num * 1000, T1_num, color='dodgerblue', lw=1.5, linestyle=':',
            label=f'Backward Euler (dt=0.01s, correct init)', zorder=3)

    ax.axhline(25.0, color='gray', linestyle='--', alpha=0.5, label='Ambient (25°C)')
    ax.axhline(12.34, color='orange', linestyle=':', alpha=0.8,
               label='gem5 observed (unpatched): 12.34°C')

    ax.set_xlabel('Simulation Time (ms)')
    ax.set_ylabel('Junction Temperature (°C)')
    ax.set_title(
        'Cauer 2-Node RC Thermal Network — Analytical Solution\n'
        f'R1={R1} K/W, R2={R2} K/W, C1={C1} J/K, C2={C2} J/K, '
        f'P={P} W, T_amb={T_AMB}°C',
        fontweight='bold'
    )
    ax.legend(fontsize=10)
    ax.grid(True, linestyle='--', alpha=0.4)
    fig.tight_layout()

    out_path = os.path.join(OUT_DIR, 'analytical_solution.png')
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print(f"\nPlot saved: {out_path}")


if __name__ == '__main__':
    main()
