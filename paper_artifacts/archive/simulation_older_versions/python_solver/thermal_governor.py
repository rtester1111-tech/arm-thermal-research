#!/usr/bin/env python3
"""
thermal_governor.py  -  V2 Advanced RC Thermal Model, DVFS Governor, & Experimental Sweeps

Physics-based 2-node Cauer RC thermal model for ARM Cortex-X4 SoC simulation,
incorporating Arrhenius-based temperature-dependent leakage power, hysteresis,
multiple advanced governor strategies, bursty workloads, and big.LITTLE core migration.

Generates 8 high-fidelity research-grade charts and updated JSON logs for V2 verification.
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
# Global Constants & Simulation Parameters
# ---------------------------------------------------------------------------
T_AMBIENT      = 25.0   # degC - Ambient / Room temperature
T_THROTTLE     = 85.0   # degC - Hardware forced throttle trigger
T_PROACTIVE    = 75.0   # degC - Proactive DVFS trigger (Strategy A)
T_HYSTERESIS   = 5.0    # degC - Cooldown threshold (re-enable higher OPP)
DT             = 5.0    # s    - Simulation timestep
DURATION       = 300    # s    - Simulation duration (Extended to 300s for steady-state)

# DVFS operating points: (freq_GHz, power_W, fps_relative)
# Upgraded with the 3.00 GHz OPP sweet spot
OPP_TABLE = [
    (3.70, 6.0, 1.00),   # Cortex-X925 max
    (3.30, 4.5, 0.89),   # Cortex-X4 max
    (3.00, 3.5, 0.82),   # Sweet spot 1
    (2.80, 2.8, 0.76),   # Sweet spot 2
    (2.40, 1.8, 0.65),
    (2.00, 1.2, 0.54),
    (1.60, 0.7, 0.43),
    (1.20, 0.4, 0.32),
]
BASE_FPS = 60.0

# ---- 1-Node Thermal baseline (V1) ----
R_THERMAL = 15.0   # degC/W - Die-to-ambient thermal resistance
C_THERMAL = 3.0    # J/degC - Thermal capacitance

# ---- 2-Node Cauer RC Thermal Parameters (V2) ----
R1_THERMAL = 5.0    # degC/W - Die-to-package thermal resistance
C1_THERMAL = 1.0    # J/degC - Die thermal capacitance
R2_THERMAL = 10.0   # degC/W - Package-to-ambient thermal resistance
C2_THERMAL = 5.0    # J/degC - Package thermal capacitance
# Note: R1_THERMAL + R2_THERMAL = 15.0 (V1 resistance), maintaining steady-state compatibility

# ---- Temperature-Dependent Leakage Model Parameters ----
LEAK_RATIO_REF = 0.30    # Leakage portion of total power at reference temp (30%)
T_LEAK_REF     = 40.0    # Reference temperature (degC)
LEAK_COEFF     = 0.035   # Temperature-leakage exponential coefficient (1/degC)

# ---------------------------------------------------------------------------
# Workload-Specific Factors (P2 Model Improvements)
# ---------------------------------------------------------------------------
CURRENT_WORKLOAD = 'brightness'
WORKLOAD_FACTORS = {
    'brightness': {
        'power_factor': 1.00,  # Baseline memory-bound activity
        'fps_factor': 1.00,    # Baseline instruction density
    },
    'idct': {
        'power_factor': 1.15,  # 15% dynamic power increase due to dense ALU switching activity
        'fps_factor': 0.70,    # Heavier workload lowers absolute FPS throughput by 30%
    }
}

# ---------------------------------------------------------------------------
# Load real gem5 IPC values (Supports dynamic workload profiles)
# ---------------------------------------------------------------------------
IPC_SCALAR = 0.833
IPC_NEON   = 0.718
IPC_SVE2   = 1.000

def load_ipc_profile(workload='brightness'):
    global IPC_SCALAR, IPC_NEON, IPC_SVE2, CURRENT_WORKLOAD
    CURRENT_WORKLOAD = workload
    if workload == 'idct':
        o3_idct_path = Path(__file__).parent / '../results/gem5_o3cpu_idct_results.json'
        scalar_def, neon_def, sve2_def = 0.650, 1.250, 2.100  # Compute workloads usually have higher SIMD IPC scaling
        path = o3_idct_path
    else:
        o3_path = Path(__file__).parent / '../results/gem5_o3cpu_results.json'
        atomic_path = Path(__file__).parent / '../results/gem5_real_results.json'
        path = o3_path if o3_path.exists() else atomic_path
        scalar_def, neon_def, sve2_def = 0.833, 0.718, 1.000

    if path.exists():
        try:
            with open(path) as f:
                data = json.load(f)
            IPC_SCALAR = data['scalar']['ipc']
            IPC_NEON   = data['neon']['ipc']
            IPC_SVE2   = data['sve2']['ipc']
            print(f"Loaded gem5 IPC for [{workload}] from {path.name}: Scalar={IPC_SCALAR}, NEON={IPC_NEON}, SVE2={IPC_SVE2}")
        except Exception as e:
            print(f"Error loading {path.name} ({e}), using default placeholders for [{workload}]")
            IPC_SCALAR, IPC_NEON, IPC_SVE2 = scalar_def, neon_def, sve2_def
    else:
        IPC_SCALAR, IPC_NEON, IPC_SVE2 = scalar_def, neon_def, sve2_def
        print(f"No gem5 JSON found for [{workload}] at {path}, using default placeholders: Scalar={IPC_SCALAR}, NEON={IPC_NEON}, SVE2={IPC_SVE2}")

# Load default profile on start
load_ipc_profile('brightness')

# ---------------------------------------------------------------------------
# Core Modeling Functions
# ---------------------------------------------------------------------------
def find_opp(freq_ghz):
    """Return (power, fps_multiplier) for a given frequency."""
    for f, p, fps in OPP_TABLE:
        if abs(f - freq_ghz) < 0.05:
            return p, fps
    return OPP_TABLE[-1][1], OPP_TABLE[-1][2]

def power_with_leakage(base_power, temp, enabled=True):
    """P_total = P_dynamic + P_leak(temp) using Arrhenius-based scaling."""
    if not enabled:
        return base_power
    p_dynamic = base_power * (1.0 - LEAK_RATIO_REF)
    
    # Cap temperature input to prevent non-physical exponential runaway and OverflowErrors.
    # Real silicon thermal shutdown or device failure limits leakage saturation at extreme temps.
    temp_capped = min(temp, 100.0)
    
    p_leak = base_power * LEAK_RATIO_REF * math.exp(LEAK_COEFF * (temp_capped - T_LEAK_REF))
    return p_dynamic + p_leak

def rc_step_2node(T_die, T_pkg, power, dt):
    """Cauer 2-node thermal model with sub-stepping for numerical stability."""
    sub_steps = 50  # dt=5s -> 0.1s sub-steps
    sub_dt = dt / sub_steps
    for _ in range(sub_steps):
        dT_die = (power - (T_die - T_pkg) / R1_THERMAL) / C1_THERMAL * sub_dt
        dT_pkg = ((T_die - T_pkg) / R1_THERMAL - (T_pkg - T_AMBIENT) / R2_THERMAL) / C2_THERMAL * sub_dt
        T_die += dT_die
        T_pkg += dT_pkg
    return T_die, T_pkg

def get_workload_intensity(t, pattern='sustained'):
    """Return workload scaling factor based on time and simulation pattern."""
    if pattern == 'sustained':
        return 1.0
    elif pattern == 'bursty':
        cycle = t % 15
        if cycle < 3:    return 1.0   # High intensity (e.g. I-frame)
        elif cycle < 5:  return 0.7   # Medium intensity (e.g. P-frame)
        else:            return 0.4   # Low intensity (e.g. B-frame)
    elif pattern == 'ramp':
        return min(1.0, 0.3 + 0.7 * (t / DURATION))
    return 1.0

# ---------------------------------------------------------------------------
# Simulator Loop
# ---------------------------------------------------------------------------
def simulate(mode: str, workload_pattern: str = 'sustained', enable_leakage: bool = True, use_2node: bool = True):
    """
    Simulate thermal dynamics over DURATION with selected mode, workload and models.
    Modes: 'scalar', 'neon_aggressive', 'neon_balanced', 'sve2_aggressive', 'sve2_balanced',
           'sve2_gradual', 'sve2_predictive'
    """
    steps = int(DURATION / DT)
    temps_die = []
    temps_pkg = []
    freqs = []
    fps_log = []
    throttle_events = 0
    energy = 0.0
    
    temp_die = T_AMBIENT
    temp_pkg = T_AMBIENT
    
    # Establish initial frequency (Cold boot starts at max available frequency)
    if mode == 'scalar':
        freq = 1.20
    elif 'aggressive' in mode:
        freq = 3.30
    else:  # balanced, gradual, predictive
        freq = 3.30  # cold-boot at max frequency for fair comparison
        
    cooldown_timer = 0
    prev_temp = T_AMBIENT
    
    for step_idx in range(steps):
        t = step_idx * DT
        base_power, freq_mult = find_opp(freq)
        
        # Workload scaling (incorporating dynamic workload factors for power)
        intensity = get_workload_intensity(t, workload_pattern)
        power_factor = WORKLOAD_FACTORS[CURRENT_WORKLOAD]['power_factor']
        scaled_power = base_power * intensity * power_factor
        
        # Leakage adjustment
        power = power_with_leakage(scaled_power, temp_die, enable_leakage)
        
        # Fetch appropriate IPC
        if mode == 'scalar':
            ipc = IPC_SCALAR
        elif 'neon' in mode:
            ipc = IPC_NEON
        else:  # sve2
            ipc = IPC_SVE2
            
        # FPS calculation (incorporating dynamic workload factors for instruction complexity)
        fps_factor = WORKLOAD_FACTORS[CURRENT_WORKLOAD]['fps_factor']
        fps = BASE_FPS * freq_mult * (ipc / IPC_SVE2) * intensity * fps_factor
        
        # Heat transfer step
        if use_2node:
            temp_die, temp_pkg = rc_step_2node(temp_die, temp_pkg, power, DT)
            temp = temp_die
        else:
            # 1-node equivalent
            T_ss = T_AMBIENT + power * R_THERMAL
            tau = R_THERMAL * C_THERMAL
            temp_die = T_ss + (temp_die - T_ss) * math.exp(-DT / tau)
            temp = temp_die
            temp_pkg = T_AMBIENT
            
        # Decrement cooldown timer
        if cooldown_timer > 0:
            cooldown_timer -= 1
            
        # --- HW safety throttle Net override (Global Hardware Protection) ---
        # If temperature hits T_THROTTLE, hardware directly overrides software
        # governor and drops frequency to a safe state (1.60 GHz) to prevent damage.
        if mode != 'scalar' and temp >= T_THROTTLE:
            freq = 1.60
            throttle_events += 1
            cooldown_timer = 4  # lock at low freq for 20s to allow cooling
        else:
            # Governor Decision Loop
            if 'aggressive' in mode:
                if temp < T_THROTTLE - T_HYSTERESIS and freq < 3.30:
                    opp_idx = next((i for i,(f,_,__) in enumerate(OPP_TABLE) if abs(f-freq)<0.05), len(OPP_TABLE)-1)
                    opp_idx = max(opp_idx - 1, 0)
                    freq = OPP_TABLE[opp_idx][0]
                    
            elif 'balanced' in mode:
                if cooldown_timer <= 0 and temp >= T_PROACTIVE:
                    freq = 2.80
                    cooldown_timer = 3  # Hysteresis lock: hold for 3 steps (15 seconds)
                elif temp < T_PROACTIVE - T_HYSTERESIS and cooldown_timer <= 0:
                    opp_idx = next((i for i,(f,_,__) in enumerate(OPP_TABLE) if abs(f-freq)<0.05), len(OPP_TABLE)-1)
                    if opp_idx > 1:
                        freq = OPP_TABLE[opp_idx-1][0]  # Recover one OPP level at a time
                        
            elif 'gradual' in mode:
                if temp >= T_PROACTIVE + 5:
                    freq = 2.80
                elif temp >= T_PROACTIVE:
                    freq = 3.00
                elif temp < T_PROACTIVE - T_HYSTERESIS and cooldown_timer <= 0:
                    opp_idx = next((i for i,(f,_,__) in enumerate(OPP_TABLE) if abs(f-freq)<0.05), len(OPP_TABLE)-1)
                    if opp_idx > 1:
                        freq = OPP_TABLE[opp_idx-1][0]
                        
            elif 'predictive' in mode:
                dTdt = (temp - prev_temp) / DT
                if dTdt > 0.8:
                    freq = min(freq, 2.80)
                elif dTdt > 0.3:
                    freq = min(freq, 3.00)
                elif dTdt < -0.1 and temp < T_PROACTIVE - T_HYSTERESIS and cooldown_timer <= 0:
                    opp_idx = next((i for i,(f,_,__) in enumerate(OPP_TABLE) if abs(f-freq)<0.05), len(OPP_TABLE)-1)
                    if opp_idx > 1:
                        freq = OPP_TABLE[opp_idx-1][0]
                        
        temps_die.append(temp_die)
        temps_pkg.append(temp_pkg)
        freqs.append(freq)
        fps_log.append(fps)
        energy += power * DT
        prev_temp = temp
        
    time_axis = [i * DT for i in range(steps)]
    avg_fps = sum(fps_log) / len(fps_log)
    edp = energy / avg_fps if avg_fps > 0 else float('inf')  # V2 Bugfix: J/FPS
    
    return {
        'time': time_axis,
        'temp_die': temps_die,
        'temp_pkg': temps_pkg,
        'temp': temps_die,
        'freq': freqs,
        'fps': fps_log,
        'avg_fps': avg_fps,
        'max_temp': max(temps_die),
        'throttle': throttle_events,
        'energy': energy,
        'edp': edp,
    }

# ---------------------------------------------------------------------------
# big.LITTLE Task Migration Simulation Model
# ---------------------------------------------------------------------------
def simulate_biglittle():
    """big.LITTLE: big core offloads tasks to mid core when exceeding proactive thermal threshold."""
    steps = int(DURATION / DT)
    big_temp, big_pkg = T_AMBIENT, T_AMBIENT
    mid_temp, mid_pkg = T_AMBIENT, T_AMBIENT
    big_freq = 3.30
    mid_freq = 2.00
    MID_IPC_FACTOR = 0.60
    MID_POWER_MAX = 1.20   # Power consumption of A720 mid core @ 2.0 GHz
    
    R1_MID, C1_MID = 8.0, 0.5
    R2_MID, C2_MID = 12.0, 3.0
    
    workload_big = 1.0
    results = {'temp': [], 'freq': [], 'fps': [], 'mid_temp': [], 'split': []}
    energy = 0.0
    
    for step_idx in range(steps):
        if big_temp >= T_PROACTIVE:
            workload_big = 0.60  # migrate 40% workload to mid core
        elif big_temp < T_PROACTIVE - T_HYSTERESIS:
            workload_big = 1.00  # fully run on big core
        workload_mid = 1.0 - workload_big
        
        power_factor = WORKLOAD_FACTORS[CURRENT_WORKLOAD]['power_factor']
        big_power = power_with_leakage(find_opp(big_freq)[0] * workload_big * power_factor, big_temp)
        mid_power = power_with_leakage(MID_POWER_MAX * workload_mid * power_factor, mid_temp)
        
        big_temp, big_pkg = rc_step_2node(big_temp, big_pkg, big_power, DT)
        
        # Mid core Cauer 2-node simulation
        sub_steps = 50
        sub_dt = DT / sub_steps
        for _ in range(sub_steps):
            d1 = (mid_power - (mid_temp - mid_pkg) / R1_MID) / C1_MID * sub_dt
            d2 = ((mid_temp - mid_pkg) / R1_MID - (mid_pkg - T_AMBIENT) / R2_MID) / C2_MID * sub_dt
            mid_temp += d1
            mid_pkg += d2
            
        _, big_mult = find_opp(big_freq)
        fps_factor = WORKLOAD_FACTORS[CURRENT_WORKLOAD]['fps_factor']
        fps_big = BASE_FPS * big_mult * workload_big * fps_factor
        fps_mid = BASE_FPS * 0.54 * MID_IPC_FACTOR * workload_mid * fps_factor
        fps = fps_big + fps_mid
        
        energy += (big_power + mid_power) * DT
        results['temp'].append(big_temp)
        results['mid_temp'].append(mid_temp)
        results['freq'].append(big_freq)
        results['fps'].append(fps)
        results['split'].append(workload_big)
        
    results['avg_fps'] = sum(results['fps']) / len(results['fps'])
    results['max_temp'] = max(results['temp'])
    results['energy'] = energy
    results['edp'] = energy / results['avg_fps'] if results['avg_fps'] > 0 else float('inf')
    results['throttle'] = 0
    results['time'] = [i * DT for i in range(steps)]
    return results

# ---------------------------------------------------------------------------
# Parametric Sweeping
# ---------------------------------------------------------------------------
def sweep_t_dvfs(sweep_mode='sve2_balanced'):
    """Sweep proactive trigger temperature from 65 to 83 degC."""
    global T_PROACTIVE
    original = T_PROACTIVE
    sweep = []
    for t in np.arange(65, 84, 1):
        T_PROACTIVE = t
        r = simulate(sweep_mode)
        sweep.append({
            't_dvfs': float(t),
            'avg_fps': r['avg_fps'],
            'max_temp': r['max_temp'],
            'energy': r['energy'],
            'throttle': r['throttle'],
            'edp': r['edp']
        })
    T_PROACTIVE = original
    return sweep

# ---------------------------------------------------------------------------
# Plotting Engine (Generates 8 high-fidelity charts)
# ---------------------------------------------------------------------------
def generate_all_plots(results: dict, sweep: list, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    
    # 1. Chart 1: V2 Thermal Timeline (5 Core Modes)
    fig, axes = plt.subplots(5, 1, figsize=(14, 16), sharex=True)
    fig.suptitle('Chart 1: V2 Extended Thermal Timeline - Cauer 2-Node Model', fontsize=15, fontweight='bold', y=0.99)
    modes_c1 = ['scalar', 'neon_aggressive', 'neon_balanced', 'sve2_aggressive', 'sve2_balanced']
    colors_c1 = {'scalar': '#1E88E5', 'neon_aggressive': '#D32F2F', 'neon_balanced': '#388E3C', 'sve2_aggressive': '#7B1FA2', 'sve2_balanced': '#F57C00'}
    
    for idx, (mode, ax) in enumerate(zip(modes_c1, axes)):
        r = results[mode]
        ax2 = ax.twinx()
        ax.plot(r['time'], r['temp_die'], color=colors_c1[mode], linewidth=2.5, label='Die Temp')
        ax.plot(r['time'], r['temp_pkg'], color=colors_c1[mode], linestyle=':', alpha=0.7, label='Pkg Temp')
        ax2.plot(r['time'], r['freq'], color='#555555', linewidth=1.5, linestyle='--', label='Freq (GHz)')
        
        ax.axhline(T_THROTTLE, color='#C62828', linestyle='-.', alpha=0.7, label=f'HW Throttle ({T_THROTTLE}C)')
        ax.axhline(T_PROACTIVE, color='#F57F17', linestyle='-.', alpha=0.7, label=f'Proactive ({T_PROACTIVE}C)')
        
        ax.set_ylabel('Temp (C)', color=colors_c1[mode], fontweight='bold')
        ax2.set_ylabel('Freq (GHz)', color='#555555')
        ax.set_title(f"Mode: {mode.upper()} | Avg FPS: {r['avg_fps']:.1f} | Throttles: {r['throttle']}x | Max Die Temp: {r['max_temp']:.1f}C", fontsize=10, loc='left', pad=4)
        ax.set_ylim(20, 105)
        ax2.set_ylim(0, 4.2)
        if idx == 0:
            ax.legend(loc='upper left', frameon=True, fontsize=8)
            
    axes[-1].set_xlabel('Simulation Time (s)', fontweight='bold')
    plt.tight_layout()
    plt.savefig(out_dir / 'chart_thermal_timeline_v2.png', dpi=150, bbox_inches='tight')
    plt.close()
    
    # 2. Chart 2: V2 EDP Metric Comparison (5 Core Modes)
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    fig.suptitle('Chart 2: V2 Energy-Delay Product (EDP) Metric Evaluation', fontsize=14, fontweight='bold', y=0.98)
    mode_labels = ['Scalar', 'Neon\nAgg', 'Neon\nBal', 'SVE2\nAgg', 'SVE2\nBal']
    colors_c2 = ['#1E88E5', '#D32F2F', '#388E3C', '#7B1FA2', '#F57C00']
    
    metrics = [
        ('avg_fps', 'Average FPS (Higher is Better)', 'FPS'),
        ('energy', 'Total Energy Consumption (Lower is Better)', 'Joules'),
        ('edp', 'Energy-Delay Product (EDP, J/FPS) (Lower is Better)', 'J/FPS'),
    ]
    
    for idx, (key, title, unit) in enumerate(metrics):
        vals = [results[m][key] for m in modes_c1]
        bars = axes[idx].bar(mode_labels, vals, color=colors_c2, edgecolor='black', linewidth=0.5)
        axes[idx].set_title(title, fontsize=10, fontweight='bold')
        axes[idx].set_ylabel(unit)
        for bar, val in zip(bars, vals):
            axes[idx].text(bar.get_x() + bar.get_width()/2., bar.get_height() + (max(vals)*0.01),
                           f'{val:.1f}' if val < 1000 else f'{val:.0f}', ha='center', va='bottom', fontsize=8)
            
    plt.tight_layout()
    plt.savefig(out_dir / 'chart_edp_comparison_v2.png', dpi=150, bbox_inches='tight')
    plt.close()
    
    # 3. Chart 3: Pareto Frontier for T_dvfs Sweep
    fig, ax = plt.subplots(figsize=(10, 6))
    fps_vals = [s['avg_fps'] for s in sweep]
    temp_vals = [s['max_temp'] for s in sweep]
    t_dvfs_vals = [s['t_dvfs'] for s in sweep]
    
    sc = ax.scatter(fps_vals, temp_vals, c=t_dvfs_vals, cmap='RdYlGn_r', s=120, edgecolors='black', zorder=3)
    cbar = plt.colorbar(sc, label='T_dvfs Proactive Threshold (°C)')
    
    for s in sweep[::2]:  # Annotate every alternate sweep point
        ax.annotate(f"{s['t_dvfs']:.0f}°C", (s['avg_fps'], s['max_temp']),
                    textcoords="offset points", xytext=(4, 4), fontsize=8, fontweight='bold')
        
    ax.axhline(T_THROTTLE, color='#C62828', linestyle=':', linewidth=1.5, label='HW Throttle (85°C)')
    ax.set_xlabel('Average Performance (FPS)', fontweight='bold')
    ax.set_ylabel('Peak Core Temperature (°C)', fontweight='bold')
    ax.set_title('Chart 3: Pareto Frontier of T_dvfs Sweep (65°C - 83°C)', fontsize=12, fontweight='bold')
    ax.legend(loc='upper left')
    plt.savefig(out_dir / 'chart_pareto_tdvfs.png', dpi=150, bbox_inches='tight')
    plt.close()
    
    # 4. Chart 4: Governor Comparisons (Agg, Bal, Gradual, Pred)
    fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=True)
    fig.suptitle('Chart 4: Thermal & Frequency Profiles of 4 DVFS Governors (SVE2)', fontsize=14, fontweight='bold')
    govs = ['sve2_aggressive', 'sve2_balanced', 'sve2_gradual', 'sve2_predictive']
    gov_labels = {'sve2_aggressive': 'Aggressive', 'sve2_balanced': 'Balanced', 'sve2_gradual': 'Gradual', 'sve2_predictive': 'Predictive'}
    colors_c4 = {'sve2_aggressive': '#D32F2F', 'sve2_balanced': '#388E3C', 'sve2_gradual': '#1E88E5', 'sve2_predictive': '#7B1FA2'}
    
    for idx, (gov, ax) in enumerate(zip(govs, axes)):
        r = results[gov]
        ax2 = ax.twinx()
        ax.plot(r['time'], r['temp_die'], color=colors_c4[gov], linewidth=2, label='Die Temp')
        ax2.plot(r['time'], r['freq'], color='#666666', linestyle='--', linewidth=1.5, label='Freq (GHz)')
        
        ax.axhline(T_THROTTLE, color='#C62828', linestyle=':', alpha=0.5)
        ax.set_ylabel('Temp (C)', color=colors_c4[gov], fontweight='bold')
        ax2.set_ylabel('Freq (GHz)', color='#666666')
        ax.set_title(f"Governor: {gov_labels[gov]} | Avg FPS: {r['avg_fps']:.1f} | Throttles: {r['throttle']}x | Energy: {r['energy']:.0f}J | EDP: {r['edp']:.1f}", fontsize=9, loc='left')
        ax.set_ylim(20, 105)
        ax2.set_ylim(0, 4.2)
        
    axes[-1].set_xlabel('Time (s)', fontweight='bold')
    plt.tight_layout()
    plt.savefig(out_dir / 'chart_governor_comparison.png', dpi=150, bbox_inches='tight')
    plt.close()
    
    # 5. Chart 5: Bursty Workload Simulation
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    fig.suptitle('Chart 5: Workload Patterns Thermal Comparison (SVE2 Balanced)', fontsize=14, fontweight='bold')
    
    patterns = [('sustained', 'Sustained Continuous Load (1.0 constant)'), ('bursty', 'Bursty Video Frames Load (Periodic Peak/Valley)')]
    colors_c5 = ['#D32F2F', '#0288D1']
    
    for idx, (patt, desc) in enumerate(patterns):
        r = simulate('sve2_balanced', workload_pattern=patt)
        ax = axes[idx]
        ax2 = ax.twinx()
        ax.plot(r['time'], r['temp_die'], color=colors_c5[idx], linewidth=2.5, label='Die Temp')
        ax.plot(r['time'], r['temp_pkg'], color=colors_c5[idx], linestyle=':', alpha=0.7, label='Pkg Temp')
        
        # Plot relative intensity scaling
        intensities = [get_workload_intensity(t, patt) for t in r['time']]
        ax2.fill_between(r['time'], 0, intensities, color='#BBDEFB', alpha=0.3, label='Workload Intensity')
        
        ax.set_ylabel('Temp (C)', color=colors_c5[idx], fontweight='bold')
        ax2.set_ylabel('Load Intensity', color='#0288D1')
        ax.set_ylim(20, 95)
        ax2.set_ylim(0, 1.2)
        ax.set_title(desc, fontsize=10, loc='left', pad=4)
        
    axes[-1].set_xlabel('Time (s)', fontweight='bold')
    plt.tight_layout()
    plt.savefig(out_dir / 'chart_bursty_workload.png', dpi=150, bbox_inches='tight')
    plt.close()
    
    # 6. Chart 6: big.LITTLE Task Migration vs DVFS
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    fig.suptitle('Chart 6: Performance & Thermal Balancing - big.LITTLE Migration vs SVE2 Balanced DVFS', fontsize=14, fontweight='bold')
    
    r_bl = simulate_biglittle()
    r_dvfs = results['sve2_balanced']
    
    # Top panel: Temperature
    axes[0].plot(r_bl['time'], r_bl['temp'], color='#E64A19', linewidth=2.5, label='big.LITTLE Big Core Die')
    axes[0].plot(r_bl['time'], r_bl['mid_temp'], color='#43A047', linewidth=1.5, linestyle=':', label='big.LITTLE Mid Core Die')
    axes[0].plot(r_dvfs['time'], r_dvfs['temp_die'], color='#1976D2', linewidth=2.0, linestyle='--', label='SVE2 Balanced DVFS Core Die')
    axes[0].set_ylabel('Temp (C)', fontweight='bold')
    axes[0].set_ylim(20, 90)
    axes[0].legend(loc='upper right')
    axes[0].set_title('Die Temperature Comparison')
    
    # Middle panel: FPS
    axes[1].plot(r_bl['time'], r_bl['fps'], color='#E64A19', linewidth=2.5, label='big.LITTLE Combined Output')
    axes[1].plot(r_dvfs['time'], r_dvfs['fps'], color='#1976D2', linewidth=2.0, linestyle='--', label='SVE2 Balanced DVFS Output')
    axes[1].set_ylabel('Performance (FPS)', fontweight='bold')
    axes[1].set_ylim(15, 65)
    axes[1].legend(loc='upper right')
    axes[1].set_title(f"Performance (Avg: big.LITTLE = {r_bl['avg_fps']:.1f} FPS, DVFS = {r_dvfs['avg_fps']:.1f} FPS)")
    
    # Bottom panel: big.LITTLE Migration Workload Allocation
    axes[2].fill_between(r_bl['time'], 0, r_bl['split'], color='#FFCCBC', alpha=0.7, label='Big Core Allocation')
    axes[2].fill_between(r_bl['time'], r_bl['split'], 1.0, color='#C8E6C9', alpha=0.7, label='Mid Core Allocation')
    axes[2].set_ylabel('Workload Ratio', fontweight='bold')
    axes[2].set_ylim(0, 1.1)
    axes[2].legend(loc='upper right')
    axes[2].set_title('big.LITTLE Active Task Partitioning')
    
    axes[-1].set_xlabel('Time (s)', fontweight='bold')
    plt.tight_layout()
    plt.savefig(out_dir / 'chart_biglittle_vs_dvfs.png', dpi=150, bbox_inches='tight')
    plt.close()
    
    # 7. Chart 7: Temperature-Dependent Leakage Effect
    fig, ax = plt.subplots(figsize=(10, 6))
    r_leak = results['sve2_aggressive']  # Has leakage enabled
    r_noleak = simulate('sve2_aggressive', enable_leakage=False)
    
    ax.plot(r_leak['time'], r_leak['temp_die'], color='#D32F2F', linewidth=2.5, label='With Leakage Model (V2)')
    ax.plot(r_noleak['time'], r_noleak['temp_die'], color='#1976D2', linewidth=2.0, linestyle='--', label='Dynamic Only Model (V1)')
    
    ax.axhline(T_THROTTLE, color='#555555', linestyle=':', alpha=0.7)
    ax.set_ylabel('Die Temperature (°C)', fontweight='bold')
    ax.set_xlabel('Simulation Time (s)', fontweight='bold')
    ax.set_title(f"Chart 7: Temperature-Dependent Leakage Thermal Amplification (SVE2 Aggressive)\nPeak Temp Delta: {r_leak['max_temp'] - r_noleak['max_temp']:.1f}°C", fontsize=11, fontweight='bold')
    ax.legend(loc='upper left')
    ax.set_ylim(20, 105)
    plt.savefig(out_dir / 'chart_leakage_effect.png', dpi=150, bbox_inches='tight')
    plt.close()
    
    # 8. Chart 8: Thermal Models Comparison (1-Node vs 2-Node)
    fig, ax = plt.subplots(figsize=(10, 6))
    r_2n = results['sve2_aggressive']
    r_1n = simulate('sve2_aggressive', use_2node=False)
    
    ax.plot(r_2n['time'], r_2n['temp_die'], color='#7B1FA2', linewidth=2.5, label='2-Node Die Temperature')
    ax.plot(r_2n['time'], r_2n['temp_pkg'], color='#388E3C', linewidth=1.5, linestyle=':', label='2-Node Package Temperature')
    ax.plot(r_1n['time'], r_1n['temp_die'], color='#D32F2F', linewidth=2.0, linestyle='--', label='1-Node Die Temperature (V1)')
    
    ax.set_ylabel('Temperature (°C)', fontweight='bold')
    ax.set_xlabel('Simulation Time (s)', fontweight='bold')
    ax.set_title('Chart 8: Thermal Transients Evaluation (1-Node Model vs 2-Node Cauer)', fontsize=11, fontweight='bold')
    ax.legend(loc='lower right')
    ax.set_ylim(20, 105)
    plt.savefig(out_dir / 'chart_rc_model_comparison.png', dpi=150, bbox_inches='tight')
    plt.close()
    
    print("V2 Plotting completed successfully. 8 plots saved.")

# ---------------------------------------------------------------------------
# Summary Output
# ---------------------------------------------------------------------------
def print_v2_summary(results):
    print('\n' + '='*85)
    print(' ARM CORTEX-X4 V2 THERMAL SIMULATION COMPREHENSIVE SUMMARY')
    print('='*85)
    headers = ['Mode', 'Avg FPS', 'Max Temp', 'Throttle', 'Energy(J)', 'EDP (J/FPS)']
    print(f'{headers[0]:<22} {headers[1]:>10} {headers[2]:>12} {headers[3]:>10} {headers[4]:>12} {headers[5]:>14}')
    print('-'*85)
    for mode in results:
        r = results[mode]
        print(f'{mode:<22} {r["avg_fps"]:>10.2f} {r["max_temp"]:>11.2f}C {r["throttle"]:>9}x {r["energy"]:>12.1f} {r["edp"]:>14.2f}')
    print('='*85)

# ---------------------------------------------------------------------------
# Main Driver
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='ARM V2 Advanced Thermal RC Governor Simulation')
    parser.add_argument('--out', default='../results', help='Output directory')
    parser.add_argument('--workload', default='brightness', choices=['brightness', 'idct'], help='Workload profile to load IPC values for')
    args = parser.parse_args()
    
    # Dynamically load the selected workload IPC profile before simulating
    load_ipc_profile(args.workload)
    
    out_dir = Path(args.out)
    print(f'Starting V2 RC Advanced Thermal Simulation for [{args.workload}] workload...')
    
    # Run the core 5 simulation configurations
    results = {
        'scalar':           simulate('scalar'),
        'neon_aggressive':  simulate('neon_aggressive'),
        'neon_balanced':    simulate('neon_balanced'),
        'sve2_aggressive':  simulate('sve2_aggressive'),
        'sve2_balanced':    simulate('sve2_balanced'),
        # Run alternative governors for comparisons
        'sve2_gradual':     simulate('sve2_gradual'),
        'sve2_predictive':  simulate('sve2_predictive'),
    }
    
    # Execute Parameter Sweep
    print("Running proactive DVFS trigger sweep (T_dvfs)...")
    sweep_data = sweep_t_dvfs()
    
    # Save V2 Raw JSON Data
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / 'thermal_simulation_v2.json'
    json_data = {
        m: {k: v for k, v in r.items() if k != 'time'}
        for m, r in results.items()
    }
    with open(json_path, 'w') as f:
        json.dump(json_data, f, indent=2)
    print(f"Saved raw simulation data: {json_path}")
    
    sweep_path = out_dir / 'sweep_tdvfs.json'
    with open(sweep_path, 'w') as f:
        json.dump(sweep_data, f, indent=2)
    print(f"Saved parameter sweep data: {sweep_path}")
    
    # Print formatted output
    print_v2_summary(results)
    
    # Generate 8 research-grade plots
    print("Generating comprehensive V2 charts...")
    generate_all_plots(results, sweep_data, out_dir)
    print(f"\nDone! V2 implementation completed successfully. Visualizations stored in {out_dir}")
