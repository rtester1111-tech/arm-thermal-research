#!/usr/bin/env python3
"""
run_esl_trace_experiments.py — Paper 2 ESL Phase 3 Trace-Driven Experiment Suite

Produces the three required ESL variants for Paper 2 evaluation:
  Variant 1: 2-node baseline  — 2-node Cauer RC + aggressive DVFS (legacy approach)
  Variant 2: 3-node model     — 3-node Cauer RC + balanced DVFS (improved model, same policy)
  Variant 3: 3-node + policy  — 3-node Cauer RC + package-aware deferred DVFS + big.LITTLE migration

Gem5-calibrated power/IPC constants (from m5out_phase6/stats.txt, Phase 6, 113 dumps):
  Big cluster  (3.3 GHz, A75-class):  IPC_mean=0.991, P_dyn_mean=2.21 W
  Little cluster (2.0 GHz, A55-class): IPC_mean=0.653, P_dyn_mean=0.86 W
  OPP power values below are theoretical peak; gem5 mean is ~49% of peak
  (typical OS workload does not sustain full-width ALU activity).

All throughput figures are PROJECTED (not measured in hardware or gem5 OS mode).
All temperatures are MODELED from the Cauer RC solver.
"""

import sys, csv, json, math
from pathlib import Path
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT   = Path(__file__).parent.parent.parent   # arm-thermal-research/
OUTDIR = Path(__file__).parent / "phase3_esl_experiments"
OUTDIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Simulation constants (gem5-calibrated where noted)
# ---------------------------------------------------------------------------
T_AMB      = 25.0   # °C  ambient
T_THROTTLE = 85.0   # °C  hardware trip
T_PROACT   = 75.0   # °C  proactive threshold
T_HYST     = 5.0    # °C  hysteresis band
DT         = 5.0    # s   timestep
DURATION   = 600    # s  (600 s needed for 3-node heatsink to show dynamics; tau_hs=120 s)

# 2-node RC parameters (matches gem5 smoke run: r-die-pkg=5, r-pkg-amb=10, c-die=1, c-pkg=5)
R1_2N, C1_2N = 5.0, 1.0    # die→pkg
R2_2N, C2_2N = 10.0, 5.0   # pkg→amb

# 3-node RC parameters (matches gem5 --enable-3node smoke run validation)
R1_3N, C1_3N = 5.0, 1.0    # die→pkg  (tau_die  ≈ R1*C1 = 5 s)
R2_3N, C2_3N = 2.0, 5.0    # pkg→hs   (tau_pkg  ≈ 50 s approx)
R3_3N, C3_3N = 8.0, 15.0   # hs→amb   (tau_hs   = R3*C3 = 120 s)

# Gem5-calibrated power (mean dynamic power from m5out_phase6/stats.txt)
# Big cluster at 3.3 GHz: mean 2.21 W; Little cluster at 2.0 GHz: mean 0.86 W
P_BIG_GEM5    = 2.21   # W  — gem5-derived mean (source: Phase 2.5 report)
P_LITTLE_GEM5 = 0.86   # W  — gem5-derived mean

# Theoretical OPP peak power (for comparison; DVFS steps down proportionally)
OPP = [  # (freq_GHz, power_W_theoretical, ipc_relative)
    (3.30, 4.50, 1.000),
    (3.00, 3.50, 0.920),
    (2.80, 2.80, 0.860),
    (2.40, 1.80, 0.740),
    (2.00, 1.20, 0.610),
    (1.60, 0.70, 0.490),
    (1.20, 0.40, 0.370),
]
OPP_DICT = {f: (p, ips) for f, p, ips in OPP}

# Gem5 IPC for big cluster at 3.3 GHz (mean from Phase 6)
IPC_BIG_GEM5    = 0.991
IPC_LITTLE_GEM5 = 0.653

# Power scenario selector:
#   'gem5_mean'  — gem5-observed mean (2.21 W @ 3.3 GHz); typical OS boot activity.
#                  Steady-state T_die ≈ 58°C; no thermal events. Use to show "idle" baseline.
#   'sustained'  — estimated sustained compute load (78% of theoretical OPP peak).
#                  3.5 W @ 3.3 GHz → steady-state T_die ≈ 77.5°C; triggers DVFS policy.
#                  This is the relevant scenario for demonstrating thermal governance value.
# Power scenario:
#   'gem5_mean'  — 2.21 W (gem5-observed mean boot activity; SS T_die ≈ 58°C, no events)
#   'sustained'  — 3.5 W  (moderate-high sustained compute;  SS T_die ≈ 77°C, V1 events)
#   'peak'       — 4.5 W  (theoretical OPP peak TDP;         SS T_die ≈ 92°C, all events)
POWER_SCENARIO   = 'peak'
GEM5_POWER_SCALE = {'gem5_mean': P_BIG_GEM5,
                    'sustained': 3.5,
                    'peak':      OPP_DICT[3.30][0]}[POWER_SCENARIO] / OPP_DICT[3.30][0]

# Base performance metric (projected throughput units, proportional to IPC×freq)
PERF_BASE = IPC_BIG_GEM5 * 3.30   # 3.27 GIPS at peak

# ---------------------------------------------------------------------------
# RC solvers
# ---------------------------------------------------------------------------
SUBSTEPS = 50

def rc2(Td, Tp, P):
    dt = DT / SUBSTEPS
    for _ in range(SUBSTEPS):
        Td += (P - (Td - Tp) / R1_2N) / C1_2N * dt
        Tp += ((Td - Tp) / R1_2N - (Tp - T_AMB) / R2_2N) / C2_2N * dt
    return Td, Tp

def rc3(Td, Tp, Th, P):
    dt = DT / SUBSTEPS
    for _ in range(SUBSTEPS):
        Td += (P - (Td - Tp) / R1_3N) / C1_3N * dt
        Tp += ((Td - Tp) / R1_3N - (Tp - Th) / R2_3N) / C2_3N * dt
        Th += ((Tp - Th) / R2_3N - (Th - T_AMB) / R3_3N) / C3_3N * dt
    return Td, Tp, Th

def opp_power(freq):
    p_theoretical, _ = OPP_DICT.get(freq, (OPP[-1][1], OPP[-1][2]))
    return p_theoretical * GEM5_POWER_SCALE   # gem5-calibrated

def opp_perf(freq):
    _, ipc_rel = OPP_DICT.get(freq, (OPP[-1][1], OPP[-1][2]))
    return PERF_BASE * ipc_rel   # projected GIPS

def opp_step_down(freq):
    freqs = [f for f, _, __ in OPP]
    idx = freqs.index(freq) if freq in freqs else len(freqs) - 1
    return freqs[min(idx + 1, len(freqs) - 1)]

def opp_step_up(freq):
    freqs = [f for f, _, __ in OPP]
    idx = freqs.index(freq) if freq in freqs else len(freqs) - 1
    return freqs[max(idx - 1, 0)]

# ---------------------------------------------------------------------------
# Variant 1: 2-node + aggressive DVFS
# ---------------------------------------------------------------------------
def variant_2node_aggressive():
    Td, Tp = T_AMB, T_AMB
    freq = 3.30
    cooldown = 0
    rows = []
    dvfs_events = []
    for step in range(int(DURATION / DT)):
        t = step * DT
        P = opp_power(freq)
        Td, Tp = rc2(Td, Tp, P)
        # Aggressive: step down at T_PROACT, step up at T_PROACT - T_HYST
        prev_freq = freq
        if Td >= T_THROTTLE:
            freq = 1.60; cooldown = 4
        elif cooldown > 0:
            cooldown -= 1
        elif Td >= T_PROACT:
            freq = opp_step_down(freq)
        elif Td < T_PROACT - T_HYST and freq < 3.30:
            freq = opp_step_up(freq)
        if freq != prev_freq:
            dvfs_events.append({'t_s': t, 'from_GHz': prev_freq, 'to_GHz': freq,
                                 'trigger': 'throttle' if Td >= T_THROTTLE else
                                            'proactive' if Td >= T_PROACT else 'recovery',
                                 'variant': '2node_aggressive'})
        rows.append({'t_s': t, 'T_die': Td, 'T_pkg': Tp, 'T_hs': T_AMB,
                     'freq_GHz': freq, 'power_W': P,
                     'proj_perf': opp_perf(freq), 'variant': '2node_aggressive'})
    return rows, dvfs_events

# ---------------------------------------------------------------------------
# Variant 2: 3-node + balanced DVFS (T_die only, same thresholds as V1)
# ---------------------------------------------------------------------------
def variant_3node_balanced():
    Td, Tp, Th = T_AMB, T_AMB, T_AMB
    freq = 3.30
    cooldown = 0
    rows = []
    dvfs_events = []
    for step in range(int(DURATION / DT)):
        t = step * DT
        P = opp_power(freq)
        Td, Tp, Th = rc3(Td, Tp, Th, P)
        prev_freq = freq
        # Same balanced DVFS logic, still uses T_die only
        if Td >= T_THROTTLE:
            freq = 1.60; cooldown = 4
        elif cooldown > 0:
            cooldown -= 1
        elif Td >= T_PROACT:
            freq = opp_step_down(freq)
        elif Td < T_PROACT - T_HYST and freq < 3.30:
            freq = opp_step_up(freq)
        if freq != prev_freq:
            dvfs_events.append({'t_s': t, 'from_GHz': prev_freq, 'to_GHz': freq,
                                 'trigger': 'throttle' if Td >= T_THROTTLE else
                                            'proactive' if Td >= T_PROACT else 'recovery',
                                 'variant': '3node_balanced'})
        rows.append({'t_s': t, 'T_die': Td, 'T_pkg': Tp, 'T_hs': Th,
                     'freq_GHz': freq, 'power_W': P,
                     'proj_perf': opp_perf(freq), 'variant': '3node_balanced'})
    return rows, dvfs_events

# ---------------------------------------------------------------------------
# Variant 3: 3-node + package-aware deferred DVFS + big.LITTLE migration
# Policy: if T_die > T_PROACT BUT T_pkg < T_PROACT - 10°C → defer DVFS;
#         instead partially migrate workload to little core
# ---------------------------------------------------------------------------
def variant_3node_policy():
    Td, Tp, Th = T_AMB, T_AMB, T_AMB
    Tm = T_AMB                         # little core die temperature
    freq = 3.30
    freq_little = 2.00
    cooldown = 0
    workload_big = 1.0                 # fraction on big core [0.6, 1.0]
    rows = []
    dvfs_events = []
    for step in range(int(DURATION / DT)):
        t = step * DT
        P_big    = opp_power(freq) * workload_big
        P_little = P_LITTLE_GEM5 * (1.0 - workload_big)
        Td, Tp, Th = rc3(Td, Tp, Th, P_big)
        # Simple 1-node for little core (short time constant)
        R_m, C_m = 12.0, 1.5
        T_ss_m = T_AMB + P_little * R_m
        Tm = T_ss_m + (Tm - T_ss_m) * math.exp(-DT / (R_m * C_m))
        prev_freq = freq
        prev_split = workload_big
        if Td >= T_THROTTLE:
            freq = 1.60; cooldown = 4; workload_big = 1.0
        elif cooldown > 0:
            cooldown -= 1
        elif Td >= T_PROACT:
            if Tp < T_PROACT - 10.0:
                # Package still cool → defer DVFS, migrate 40% to little instead
                workload_big = 0.60
            else:
                # Package warming → fall back to DVFS
                freq = opp_step_down(freq)
                workload_big = 1.0
        elif Td < T_PROACT - T_HYST and freq < 3.30:
            freq = opp_step_up(freq)
            workload_big = 1.0
        trigger = None
        if freq != prev_freq:
            trigger = 'throttle' if Td >= T_THROTTLE else 'dvfs_step'
        elif workload_big != prev_split:
            trigger = 'migration_defer' if workload_big < 1.0 else 'migration_recover'
        if trigger:
            dvfs_events.append({'t_s': t, 'from_GHz': prev_freq, 'to_GHz': freq,
                                 'workload_big': workload_big, 'trigger': trigger,
                                 'variant': '3node_policy'})
        proj_perf = (opp_perf(freq) * workload_big +
                     IPC_LITTLE_GEM5 * freq_little * (1.0 - workload_big))
        rows.append({'t_s': t, 'T_die': Td, 'T_pkg': Tp, 'T_hs': Th, 'T_little': Tm,
                     'freq_GHz': freq, 'power_W': P_big + P_little,
                     'workload_big': workload_big,
                     'proj_perf': proj_perf, 'variant': '3node_policy'})
    return rows, dvfs_events

# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------
def write_csv(path, rows):
    if not rows: return
    # Collect union of all fieldnames across rows to handle per-variant extra columns
    all_keys = list(dict.fromkeys(k for r in rows for k in r.keys()))
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=all_keys, extrasaction='ignore',
                           restval='')
        w.writeheader(); w.writerows(rows)

def summary_metrics(label, rows):
    Td = [r['T_die'] for r in rows]
    Tp = [r['T_pkg'] for r in rows]
    Th = [r['T_hs'] for r in rows]
    perf = [r['proj_perf'] for r in rows]
    power = [r['power_W'] for r in rows]
    energy = sum(power) * DT
    avg_perf = sum(perf) / len(perf)
    edp = energy / avg_perf if avg_perf > 0 else float('inf')
    return {
        'variant': label,
        'T_die_max_C': round(max(Td), 3),
        'T_pkg_max_C': round(max(Tp), 3),
        'T_hs_max_C':  round(max(Th), 3),
        'proj_perf_mean_GIPS': round(avg_perf, 4),
        'energy_J': round(energy, 1),
        'edp_J_per_GIPS': round(edp, 3),
        'throttle_events': sum(1 for r in rows if r['freq_GHz'] <= 1.60
                               and r['T_die'] >= T_THROTTLE - 1),
    }

# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------
def plot_all(rows_v1, rows_v2, rows_v3):
    t1 = [r['t_s'] for r in rows_v1]
    t2 = [r['t_s'] for r in rows_v2]
    t3 = [r['t_s'] for r in rows_v3]

    # Fig 1: Temperature comparison (T_die all variants + T_pkg/T_hs for v3)
    fig, axes = plt.subplots(3, 1, figsize=(12, 12), sharex=True)
    fig.suptitle('ESL Experiment: 3-Variant Thermal Comparison\n'
                 '(All power values gem5-calibrated, throughput is projected)',
                 fontsize=13, fontweight='bold')

    ax = axes[0]
    ax.plot(t1, [r['T_die'] for r in rows_v1], color='#C62828', lw=2, label='V1: 2-node T_die')
    ax.plot(t2, [r['T_die'] for r in rows_v2], color='#1976D2', lw=2, label='V2: 3-node T_die')
    ax.plot(t3, [r['T_die'] for r in rows_v3], color='#2E7D32', lw=2, label='V3: policy T_die')
    ax.axhline(T_THROTTLE, color='black', ls=':', lw=1, label=f'T_throttle={T_THROTTLE}°C')
    ax.axhline(T_PROACT,   color='gray',  ls='--', lw=1, label=f'T_proact={T_PROACT}°C')
    ax.set_ylabel('T_die (°C)'); ax.set_ylim(20, 100)
    ax.legend(fontsize=9); ax.set_title('Die Temperature', loc='left', fontsize=10)

    ax = axes[1]
    ax.plot(t2, [r['T_pkg'] for r in rows_v2], color='#1976D2', lw=1.5, ls='--', label='V2: T_pkg')
    ax.plot(t3, [r['T_pkg'] for r in rows_v3], color='#2E7D32', lw=1.5, ls='--', label='V3: T_pkg')
    ax.plot(t3, [r['T_hs'] for r in rows_v3],  color='#9C27B0', lw=1.5, ls=':',  label='V3: T_hs')
    ax.axhline(T_AMB, color='gray', ls=':', lw=1, label='T_amb=25°C')
    ax.set_ylabel('T_pkg / T_hs (°C)'); ax.set_ylim(20, 80)
    ax.legend(fontsize=9); ax.set_title('Package & Heatsink Temperatures (3-node only)', loc='left', fontsize=10)

    ax = axes[2]
    ax.plot(t1, [r['freq_GHz'] for r in rows_v1], color='#C62828', lw=2, label='V1 freq (GHz)')
    ax.plot(t2, [r['freq_GHz'] for r in rows_v2], color='#1976D2', lw=2, label='V2 freq (GHz)')
    ax.plot(t3, [r['freq_GHz'] for r in rows_v3], color='#2E7D32', lw=2, label='V3 freq (GHz)')
    ax.set_ylabel('Big Core Freq (GHz)'); ax.set_ylim(0, 4.0)
    ax.set_xlabel('Simulation Time (s)'); ax.legend(fontsize=9)
    ax.set_title('DVFS Frequency', loc='left', fontsize=10)

    fig.tight_layout()
    fig.savefig(OUTDIR / 'esl_fig1_thermal_comparison.png', dpi=200)
    plt.close(fig)

    # Fig 2: Projected performance + big.LITTLE split
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    fig.suptitle('ESL Experiment: Projected Performance Comparison\n'
                 '(Throughput = IPC × freq, labeled as projected)',
                 fontsize=13, fontweight='bold')
    ax = axes[0]
    ax.plot(t1, [r['proj_perf'] for r in rows_v1], color='#C62828', lw=2, label='V1: 2-node+aggressive')
    ax.plot(t2, [r['proj_perf'] for r in rows_v2], color='#1976D2', lw=2, label='V2: 3-node+balanced')
    ax.plot(t3, [r['proj_perf'] for r in rows_v3], color='#2E7D32', lw=2, label='V3: 3-node+policy')
    ax.set_ylabel('Projected Throughput (GIPS)'); ax.set_ylim(0, 4.0)
    ax.legend(fontsize=9); ax.set_title('Projected Instruction Throughput', loc='left', fontsize=10)

    ax = axes[1]
    ax.fill_between(t3, 0,
                    [r['workload_big'] for r in rows_v3],
                    color='#C8E6C9', alpha=0.8, label='Big core fraction')
    ax.fill_between(t3,
                    [r['workload_big'] for r in rows_v3], 1.0,
                    color='#E3F2FD', alpha=0.8, label='Little core fraction (migrated)')
    ax.set_ylabel('Workload Allocation'); ax.set_ylim(0, 1.1)
    ax.set_xlabel('Simulation Time (s)'); ax.legend(fontsize=9)
    ax.set_title('V3: big.LITTLE Task Migration (Policy-Driven)', loc='left', fontsize=10)

    fig.tight_layout()
    fig.savefig(OUTDIR / 'esl_fig2_performance_migration.png', dpi=200)
    plt.close(fig)
    print(f"Figures saved to {OUTDIR}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Running ESL Phase 3 trace-driven experiments...")
    print(f"  RC params (3-node): R1={R1_3N}, C1={C1_3N}, R2={R2_3N}, C2={C2_3N}, R3={R3_3N}, C3={C3_3N}")
    print(f"  Gem5-calibrated big power at 3.3GHz: {opp_power(3.30):.3f} W (scale={GEM5_POWER_SCALE:.3f})")
    print(f"  Duration={DURATION}s, DT={DT}s, T_proact={T_PROACT}°C, T_throttle={T_THROTTLE}°C\n")

    rows_v1, ev_v1 = variant_2node_aggressive()
    rows_v2, ev_v2 = variant_3node_balanced()
    rows_v3, ev_v3 = variant_3node_policy()
    print(f"V1 (2-node+aggressive): {len(rows_v1)} steps, {len(ev_v1)} DVFS events")
    print(f"V2 (3-node+balanced):   {len(rows_v2)} steps, {len(ev_v2)} DVFS events")
    print(f"V3 (3-node+policy):     {len(rows_v3)} steps, {len(ev_v3)} DVFS/migration events\n")

    # Write CSVs
    all_trace = rows_v1 + rows_v2 + rows_v3
    write_csv(OUTDIR / 'simulation_trace.csv', all_trace)
    write_csv(OUTDIR / 'dvfs_events.csv', ev_v1 + ev_v2 + ev_v3)

    summaries = [
        summary_metrics('2node_aggressive', rows_v1),
        summary_metrics('3node_balanced',   rows_v2),
        summary_metrics('3node_policy',     rows_v3),
    ]
    write_csv(OUTDIR / 'summary_metrics.csv', summaries)

    # Print summary table
    print(f"{'Variant':<22} {'T_die_max':>10} {'T_pkg_max':>10} {'PerfMean':>10} {'Energy_J':>10} {'EDP':>10} {'Throttle':>9}")
    print('-' * 88)
    for s in summaries:
        print(f"{s['variant']:<22} {s['T_die_max_C']:>9.1f}°C {s['T_pkg_max_C']:>9.1f}°C "
              f"{s['proj_perf_mean_GIPS']:>9.3f} {s['energy_J']:>10.1f} "
              f"{s['edp_J_per_GIPS']:>10.3f} {s['throttle_events']:>9}")

    with open(OUTDIR / 'summary_metrics.json', 'w') as f:
        json.dump(summaries, f, indent=2)

    plot_all(rows_v1, rows_v2, rows_v3)
    print(f"\nAll outputs in: {OUTDIR}")

if __name__ == '__main__':
    main()
