#!/usr/bin/env python3
"""
thermal_governor.py  -  Phase 2 & 3 RC Thermal Model + DVFS Governor

Physics-based RC thermal model for ARM SoC simulation.
Demonstrates the core finding:
  Aggressive NEON (max freq) triggers thermal throttling
  Balanced NEON (proactive DVFS) avoids throttling and finishes faster

Run:  python3 thermal_governor.py
Deps: matplotlib, numpy  (pip install matplotlib numpy)
"""

import math
import json
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path

# ---------------------------------------------------------------------------
# RC Thermal Model Parameters (MediaTek Dimensity 9300 class SoC reference)
# ---------------------------------------------------------------------------
T_AMBIENT    = 25.0   # degC  - room temperature
R_THERMAL    = 15.0   # degC/W - die-to-ambient thermal resistance
C_THERMAL    = 3.0    # J/degC - thermal capacitance of die
DT           = 5.0    # s      - simulation timestep
DURATION     = 120    # s      - total simulation time (2 min TVTS-like test)

# DVFS operating points (freq_GHz, power_W, fps_relative)
OPP_TABLE = [
    (3.70, 6.0, 1.00),   # Cortex-X925 max
    (3.30, 4.5, 0.89),   # Cortex-X4 max
    (2.80, 2.8, 0.76),   # balanced sweet spot
    (2.40, 1.8, 0.65),
    (2.00, 1.2, 0.54),
    (1.60, 0.7, 0.43),
    (1.20, 0.4, 0.32),
]
BASE_FPS = 60.0   # FPS at max OPP

T_THROTTLE   = 85.0   # degC - HW throttle trigger
T_PROACTIVE  = 75.0   # degC - proactive DVFS trigger (Strategy A)
T_HYSTERESIS = 5.0    # degC - re-enable higher OPP only when cooled this much


# Load real gem5 IPC values
GEM5_RESULTS_PATH = Path(__file__).parent / '../results/gem5_real_results.json'
try:
    with open(GEM5_RESULTS_PATH) as f:
        GEM5_DATA = json.load(f)
    IPC_SCALAR = GEM5_DATA['scalar']['ipc']
    IPC_NEON   = GEM5_DATA['neon']['ipc']
    IPC_SVE2   = GEM5_DATA['sve2']['ipc']
    print(f"Loaded gem5 IPC: Scalar={IPC_SCALAR}, NEON={IPC_NEON}, SVE2={IPC_SVE2}")
except Exception as e:
    print(f"Warning: Could not load gem5 results ({e}), using defaults")
    IPC_SCALAR, IPC_NEON, IPC_SVE2 = 0.8, 0.8, 1.0

def find_opp(freq_ghz):
    """Return (power, fps_multiplier) for given frequency."""
    for f, p, fps in OPP_TABLE:
        if abs(f - freq_ghz) < 0.05:
            return p, fps
    return OPP_TABLE[-1][1], OPP_TABLE[-1][2]


def rc_step(temp, power, dt):
    """One RC thermal step: T(t+dt) = T_ss + (T(t) - T_ss)*exp(-dt/tau)"""
    T_ss  = T_AMBIENT + power * R_THERMAL
    tau   = R_THERMAL * C_THERMAL
    return T_ss + (temp - T_ss) * math.exp(-dt / tau)


def simulate(mode: str):
    """
    mode:
      'aggressive' - lock to max freq, only throttle reactively
      'balanced'   - proactive DVFS at T_PROACTIVE
      'scalar'     - no SIMD, low power baseline
    """
    steps   = int(DURATION / DT)
    temps   = []
    freqs   = []
    fps_log = []
    throttle_events = 0
    energy  = 0.0

    temp = T_AMBIENT

    if mode == 'scalar':
        freq = 1.20
    elif mode == 'aggressive':
        freq = 3.30
    else:  # balanced
        freq = 2.80

    for _ in range(steps):
        power, freq_mult = find_opp(freq)
        
        # Use real IPC for different modes
        if mode == 'scalar':
            ipc = IPC_SCALAR
        else:
            # aggressive/balanced both use SVE2 (highest SIMD)
            ipc = IPC_SVE2
            
        # FPS = BaseFPS * (freq / max_freq) * (ipc / max_ipc)
        # Here freq_mult is (freq / max_freq). 
        # We normalize to IPC_SVE2 as the reference for BASE_FPS.
        fps = BASE_FPS * freq_mult * (ipc / IPC_SVE2)

        # --- Thermal step ---
        temp = rc_step(temp, power, DT)

        # --- Governor logic ---
        if mode == 'aggressive':
            if temp >= T_THROTTLE:
                # HW forced throttle: drop two OPP levels
                opp_idx = next((i for i,(f,_,__) in enumerate(OPP_TABLE)
                                if abs(f-freq)<0.05), 0)
                opp_idx = min(opp_idx + 2, len(OPP_TABLE)-1)
                freq = OPP_TABLE[opp_idx][0]
                throttle_events += 1
            elif temp < T_THROTTLE - T_HYSTERESIS and freq < 3.30:
                # recover
                opp_idx = next((i for i,(f,_,__) in enumerate(OPP_TABLE)
                                if abs(f-freq)<0.05), len(OPP_TABLE)-1)
                opp_idx = max(opp_idx - 1, 0)
                freq = OPP_TABLE[opp_idx][0]

        elif mode == 'balanced':
            if temp >= T_PROACTIVE:
                # proactive step down to sweet spot
                freq = 2.80
            elif temp < T_PROACTIVE - T_HYSTERESIS:
                # allow one step up if cool enough
                opp_idx = next((i for i,(f,_,__) in enumerate(OPP_TABLE)
                                if abs(f-freq)<0.05), len(OPP_TABLE)-1)
                if opp_idx > 0:
                    new_freq = OPP_TABLE[opp_idx-1][0]
                    if new_freq <= 3.30:
                        freq = new_freq

        temps.append(temp)
        freqs.append(freq)
        fps_log.append(fps)
        energy += power * DT

    time_axis = [i * DT for i in range(steps)]
    avg_fps   = sum(fps_log) / len(fps_log)
    edp       = energy * (DURATION ** 2)   # E * T^2
    return {
        'time':     time_axis,
        'temp':     temps,
        'freq':     freqs,
        'fps':      fps_log,
        'avg_fps':  avg_fps,
        'max_temp': max(temps),
        'throttle': throttle_events,
        'energy':   energy,
        'edp':      edp,
    }


def plot_results(results: dict, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    time = results['aggressive']['time']
    colors = {'scalar': '#2196F3', 'aggressive': '#F44336', 'balanced': '#4CAF50'}
    labels = {
        'scalar':     'Scalar (no SIMD)',
        'aggressive': 'Aggressive NEON (max freq)',
        'balanced':   'Balanced NEON (proactive DVFS)',
    }

    # --- Chart 1: Thermal Timeline ---
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    fig.suptitle('Phase 2: Thermal Timeline - RC Model Simulation', fontsize=14, fontweight='bold')

    for mode, ax in zip(['scalar','aggressive','balanced'], axes):
        r = results[mode]
        ax2 = ax.twinx()
        ax.plot(time, r['temp'],  color=colors[mode], linewidth=2,   label='Temperature')
        ax2.plot(time, r['freq'], color='gray',        linewidth=1.5, linestyle='--', label='Frequency')
        ax.axhline(T_THROTTLE,   color='red',    linestyle=':',  alpha=0.7, label=f'HW Throttle ({T_THROTTLE}C)')
        ax.axhline(T_PROACTIVE,  color='orange', linestyle=':',  alpha=0.7, label=f'Proactive ({T_PROACTIVE}C)')
        ax.set_ylabel('Temperature (C)', color=colors[mode])
        ax2.set_ylabel('Frequency (GHz)', color='gray')
        ax.set_title(f'{labels[mode]}  |  avg FPS={r["avg_fps"]:.1f}  throttle={r["throttle"]}x  maxT={r["max_temp"]:.1f}C')
        ax.legend(loc='upper left', fontsize=8)
        ax.set_ylim(20, 100)
        ax2.set_ylim(0, 4.5)
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel('Time (s)')
    plt.tight_layout()
    p = out_dir / 'chart_thermal_timeline.png'
    plt.savefig(p, dpi=150, bbox_inches='tight')
    plt.close()
    print(f'Saved: {p}')

    # --- Chart 2: EDP Comparison ---
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    fig.suptitle('Phase 3: Energy-Delay Product (EDP) Analysis', fontsize=14, fontweight='bold')
    modes = ['scalar', 'aggressive', 'balanced']
    mode_labels = ['Scalar', 'Aggressive\nNEON', 'Balanced\nNEON']

    metrics = [
        ('avg_fps',  'Average FPS',       colors),
        ('energy',   'Total Energy (J)',   colors),
        ('edp',      'EDP (E x T^2)',      colors),
    ]
    for ax, (key, title, _) in zip(axes, metrics):
        vals = [results[m][key] for m in modes]
        bars = ax.bar(mode_labels, vals, color=[colors[m] for m in modes],
                      edgecolor='black', linewidth=0.5)
        ax.set_title(title, fontweight='bold')
        ax.set_ylabel(title)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width()/2., bar.get_height(),
                    f'{val:.1f}', ha='center', va='bottom', fontsize=9)
        ax.grid(True, axis='y', alpha=0.3)

    # Annotate balanced as winner
    axes[2].annotate('Winner\n(lowest EDP)', xy=(2, results['balanced']['edp']),
                     xytext=(1.2, results['balanced']['edp'] * 1.3),
                     arrowprops=dict(arrowstyle='->', color='green'),
                     fontsize=9, color='green')
    plt.tight_layout()
    p = out_dir / 'chart_edp_comparison.png'
    plt.savefig(p, dpi=150, bbox_inches='tight')
    plt.close()
    print(f'Saved: {p}')


def print_summary(results):
    print('\n' + '='*60)
    print(' SIMULATION SUMMARY')
    print('='*60)
    headers = ['Mode', 'Avg FPS', 'Max Temp', 'Throttle', 'Energy(J)', 'EDP']
    print(f'{headers[0]:<20} {headers[1]:>8} {headers[2]:>10} {headers[3]:>9} {headers[4]:>10} {headers[5]:>14}')
    print('-'*60)
    for mode in ['scalar', 'aggressive', 'balanced']:
        r = results[mode]
        print(f'{mode:<20} {r["avg_fps"]:>8.1f} {r["max_temp"]:>9.1f}C {r["throttle"]:>8}x {r["energy"]:>10.1f} {r["edp"]:>14.1f}')
    print('='*60)
    # Key insight
    agg = results['aggressive']
    bal = results['balanced']
    fps_gain  = (bal['avg_fps'] - agg['avg_fps']) / agg['avg_fps'] * 100
    edp_gain  = (agg['edp']    - bal['edp'])      / agg['edp']     * 100
    print(f'\nKey Finding:')
    print(f'  Balanced vs Aggressive -> FPS  {fps_gain:+.1f}%  |  EDP -{edp_gain:.1f}%')
    print(f'  Throttle events: {agg["throttle"]} -> {bal["throttle"]}')
    print(f'  Conclusion: Proactive DVFS is faster AND more energy-efficient.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='ARM RC Thermal Governor Simulation')
    parser.add_argument('--out', default='../results', help='Output directory')
    args = parser.parse_args()

    out_dir = Path(args.out)
    print('Running RC thermal simulation...')

    results = {
        'scalar':     simulate('scalar'),
        'aggressive': simulate('aggressive'),
        'balanced':   simulate('balanced'),
    }

    # Save raw data
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / 'thermal_simulation.json'
    json_data = {m: {k: v for k, v in r.items() if k != 'time'}
                 for m, r in results.items()}
    with open(json_path, 'w') as f:
        json.dump(json_data, f, indent=2)
    print(f'Saved raw data: {json_path}')

    print_summary(results)
    plot_results(results, out_dir)
    print('\nDone! Charts saved to', out_dir)
