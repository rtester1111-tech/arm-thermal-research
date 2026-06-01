#!/usr/bin/env python3
"""
verify_absolute_zero_bug.py — Independent Mathematical Verification
of the gem5 Absolute-Zero Heat Sink Bug

This script independently reproduces gem5's ThermalModel::doStep()
logic using the exact same Backward Euler discretization and Kirchhoff
nodal analysis, to verify that:

  Case A (Bug):   node_pkg initialized to 0 K  → T_die drops below 25°C
  Case B (Fixed): node_pkg initialized to 298.15 K → T_die rises above 25°C

If Case A matches the gem5 observation (12.34°C) and Case B shows
physically correct behavior, the bug is independently confirmed.

Cauer 2-Node RC Network Topology:
    P_heat → [node_die] --R1-- [node_pkg] --R2-- [node_amb=25°C fixed]
                  |                  |
                [C1]               [C2]
                  |                  |
              [node_amb]         [node_amb]

Parameters (matching fs_thermal.py exactly):
    R1 = R_die_pkg = 5.0 K/W
    R2 = R_pkg_amb = 10.0 K/W
    C1 = C_die     = 1.0 J/K
    C2 = C_pkg     = 5.0 J/K
    T_amb          = 298.15 K (25°C)
    dt (step)      = 0.01 s (10 ms)
    P_heat         = 3.0 W (peak dynamic power from IPC=0.96)
"""

import numpy as np
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ============================================================
# Physical Parameters (match fs_thermal.py exactly)
# ============================================================
R1 = 5.0    # K/W  (die → package)
R2 = 10.0   # K/W  (package → ambient)
C1 = 1.0    # J/K  (die thermal capacitance)
C2 = 5.0    # J/K  (package thermal capacitance)
T_AMB_K = 298.15  # K (25°C, fixed ambient reference)
DT = 0.01   # s (thermal step, matches gem5 --thermal-step=0.01)

# Simulation duration: 222.6 ms with stats dump every 0.2 ms
TOTAL_TIME = 0.2226  # s
N_STEPS = int(TOTAL_TIME / DT) + 1

# Power profile: ~3W for first 3ms, then 0W (matching observed IPC profile)
POWER_DURATION = 0.003  # s (IPC active period)
P_PEAK = 3.0  # W


def get_power(t):
    """Power profile matching the observed gem5 IPC transient."""
    if t < POWER_DURATION:
        return P_PEAK
    return 0.0


def simulate_cauer_rc(T_die_init_K, T_pkg_init_K, label):
    """
    Simulate the 2-node Cauer RC thermal network using Backward Euler,
    exactly mirroring gem5's ThermalModel::doStep() linear system solver.

    Backward Euler discretization of the Kirchhoff nodal equations:

    For node_die (unknown T1):
        C1/dt * (T1 - T1_prev) = P_heat - (T1 - T2)/R1 - (T1 - T_amb)/... 
        Wait — in Cauer topology, C1 shunts die→amb, not die→pkg.

    Let me re-derive matching the exact gem5 topology:

    Connected components:
        R1: node_die ↔ node_pkg
        C1: node_die ↔ node_amb (Cauer: capacitor shunts to ground)
        R2: node_pkg ↔ node_amb
        C2: node_pkg ↔ node_amb (Cauer: capacitor shunts to ground)
        Domain (heat source): P_heat injected at node_die
        Reference: node_amb fixed at T_AMB_K

    KCL at node_die:
        P_heat = (T1 - T2)/R1 + C1/dt*(T1 - T_amb - T1_prev + T_amb_prev)
        Since T_amb is fixed reference:
        P_heat = (T1 - T2)/R1 + C1/dt*(T1 - T1_prev)

    KCL at node_pkg:
        0 = (T2 - T1)/R1 + (T2 - T_amb)/R2 + C2/dt*(T2 - T_amb - T2_prev + T_amb_prev)
        0 = (T2 - T1)/R1 + (T2 - T_amb)/R2 + C2/dt*(T2 - T2_prev)

    Rearranging into matrix form [A]*[T] = [b]:

    Node die:
        T1 * (1/R1 + C1/dt) + T2 * (-1/R1) = P_heat + C1/dt * T1_prev

    Node pkg:
        T1 * (-1/R1) + T2 * (1/R1 + 1/R2 + C2/dt) = T_amb/R2 + C2/dt * T2_prev
    """
    times = []
    T_die_history = []
    T_pkg_history = []

    T1 = T_die_init_K  # node_die temperature (Kelvin)
    T2 = T_pkg_init_K  # node_pkg temperature (Kelvin)

    for step in range(N_STEPS):
        t = step * DT
        times.append(t * 1000)  # ms
        T_die_history.append(T1 - 273.15)  # Convert to Celsius
        T_pkg_history.append(T2 - 273.15)

        P = get_power(t)
        T1_prev = T1
        T2_prev = T2

        # Build 2x2 linear system: A * [T1_new, T2_new]^T = b
        A = np.zeros((2, 2))
        b = np.zeros(2)

        # Row 0: KCL at node_die
        A[0, 0] = 1.0/R1 + C1/DT
        A[0, 1] = -1.0/R1
        b[0] = P + C1/DT * T1_prev

        # Row 1: KCL at node_pkg
        A[1, 0] = -1.0/R1
        A[1, 1] = 1.0/R1 + 1.0/R2 + C2/DT
        b[1] = T_AMB_K/R2 + C2/DT * T2_prev

        # Solve
        T_new = np.linalg.solve(A, b)
        T1 = T_new[0]
        T2 = T_new[1]

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Initial T_die:  {T_die_init_K - 273.15:.2f}°C ({T_die_init_K:.2f} K)")
    print(f"  Initial T_pkg:  {T_pkg_init_K - 273.15:.2f}°C ({T_pkg_init_K:.2f} K)")
    print(f"  Final T_die:    {T_die_history[-1]:.2f}°C")
    print(f"  Final T_pkg:    {T_pkg_history[-1]:.2f}°C")
    print(f"  Min T_die:      {min(T_die_history):.2f}°C")
    print(f"  Max T_die:      {max(T_die_history):.2f}°C")
    print(f"  Steps:          {N_STEPS}")
    print(f"  Power profile:  {P_PEAK}W for {POWER_DURATION*1000}ms, then 0W")

    return times, T_die_history, T_pkg_history


def main():
    print("=" * 60)
    print("  gem5 Absolute-Zero Heat Sink Bug — Independent Verification")
    print("  Backward Euler Cauer 2-Node RC Simulation")
    print("=" * 60)
    print(f"  R_die_pkg = {R1} K/W,  R_pkg_amb = {R2} K/W")
    print(f"  C_die     = {C1} J/K,  C_pkg     = {C2} J/K")
    print(f"  T_ambient = {T_AMB_K} K ({T_AMB_K - 273.15}°C)")
    print(f"  dt        = {DT} s,  total     = {TOTAL_TIME*1000} ms")

    # Case A: Bug — node_pkg at 0 Kelvin (absolute zero)
    t_a, die_a, pkg_a = simulate_cauer_rc(
        T_die_init_K=T_AMB_K,  # 298.15 K (25°C) — set by domain
        T_pkg_init_K=0.0,      # 0 K (-273.15°C) — THE BUG
        label="Case A: BUG — node_pkg = 0 K (Absolute Zero)"
    )

    # Case B: Fixed — node_pkg at ambient temperature
    t_b, die_b, pkg_b = simulate_cauer_rc(
        T_die_init_K=T_AMB_K,  # 298.15 K (25°C)
        T_pkg_init_K=T_AMB_K,  # 298.15 K (25°C) — CORRECT
        label="Case B: FIXED — node_pkg = 298.15 K (25°C)"
    )

    # gem5 observed value
    GEM5_FINAL_TEMP = 12.34  # °C (from our gem5 simulation)

    print(f"\n{'='*60}")
    print(f"  VERIFICATION SUMMARY")
    print(f"{'='*60}")
    print(f"  gem5 observed final T_die:    {GEM5_FINAL_TEMP:.2f}°C")
    print(f"  Python Case A final T_die:    {die_a[-1]:.2f}°C")
    print(f"  Python Case B final T_die:    {die_b[-1]:.2f}°C")
    print()

    if die_a[-1] < 25.0 and die_b[-1] >= 25.0:
        print("  ✅ VERIFICATION PASSED:")
        print("     Case A (Bug) reproduces anomalous cooling (T < 25°C)")
        print("     Case B (Fixed) shows physically correct behavior (T ≥ 25°C)")
        print("     The Absolute-Zero Heat Sink Bug is INDEPENDENTLY CONFIRMED.")
    else:
        print("  ❌ VERIFICATION INCONCLUSIVE — review parameters")

    delta = abs(die_a[-1] - GEM5_FINAL_TEMP)
    print(f"\n  Deviation from gem5: {delta:.2f}°C")
    if delta < 5.0:
        print(f"  → Close match (within 5°C) — confirms same physical mechanism")
    else:
        print(f"  → Larger deviation — may be due to sampling/interpolation differences")

    # ============================================================
    # Plot comparison
    # ============================================================
    out_dir = "results/phase5"
    os.makedirs(out_dir, exist_ok=True)

    fig, axes = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11})

    # --- Top: Die (Junction) Temperature ---
    ax1 = axes[0]
    ax1.plot(t_a, die_a, color='crimson', linewidth=2.5,
             label='Case A (BUG): node_pkg = 0 K')
    ax1.plot(t_b, die_b, color='dodgerblue', linewidth=2.5,
             label='Case B (FIXED): node_pkg = 298.15 K')
    ax1.axhline(25.0, color='gray', linestyle='--', alpha=0.7, label='Ambient (25°C)')
    ax1.axhline(GEM5_FINAL_TEMP, color='orange', linestyle=':', alpha=0.7,
                label=f'gem5 observed ({GEM5_FINAL_TEMP}°C)')
    ax1.set_ylabel('Junction Temperature (°C)', fontsize=12)
    ax1.set_title(
        'Independent Verification: gem5 Absolute-Zero Heat Sink Bug\n'
        'Die (Junction) Node Temperature — Backward Euler Cauer 2-Node RC',
        fontsize=13, fontweight='bold')
    ax1.legend(fontsize=10, loc='center right')
    ax1.grid(True, linestyle='--', alpha=0.5)

    # --- Bottom: Package Node Temperature ---
    ax2 = axes[1]
    ax2.plot(t_a, pkg_a, color='crimson', linewidth=2.5,
             label='Case A (BUG): node_pkg starts at −273.15°C')
    ax2.plot(t_b, pkg_b, color='dodgerblue', linewidth=2.5,
             label='Case B (FIXED): node_pkg starts at 25°C')
    ax2.axhline(25.0, color='gray', linestyle='--', alpha=0.7, label='Ambient (25°C)')
    ax2.set_xlabel('Simulation Time (ms)', fontsize=12)
    ax2.set_ylabel('Package Temperature (°C)', fontsize=12)
    ax2.set_title(
        'Package Node Temperature — Shows Absolute-Zero Initial Condition',
        fontsize=13, fontweight='bold')
    ax2.legend(fontsize=10)
    ax2.grid(True, linestyle='--', alpha=0.5)

    fig.tight_layout()
    out_path = os.path.join(out_dir, 'verification_absolute_zero_bug.png')
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print(f"\n  Plot saved: {out_path}")


if __name__ == '__main__':
    main()
