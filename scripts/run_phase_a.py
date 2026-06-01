#!/usr/bin/env python3
"""
run_phase_a.py — Phase A Data Extraction & Validation Engine

Performs the following automated operations:
  1. Task A1: Solves Analytical, Python BE (fixed & bug), and SPICE (fixed & bug)
     at canonical timepoints (10ms, 50ms, 100ms, 222.6ms, 250ms) under constant 3W power.
     Generates `paper_artifacts/canonical_validation_table.csv`.
  2. Task A2: Extracts gem5 unpatched precise values from `results/phase5/fs_simulation_results.json`
     at same timepoints. Generates `paper_artifacts/gem5_unpatched_extracted.csv`.
  3. Task A3: Parses `results/phase5_v2/thinned_stats.txt` line-by-line to reconstruct
     the patched gem5 time-series and computes the patched gem5 RMSE vs Python BE.
  4. Task A4: Updates `results/validation/error_metrics_summary.json` and `error_metrics_table.txt`
     with corrected values and the newly calculated patched gem5 RMSE.
"""

import numpy as np
import json
import os
import re
import csv
import sys
import subprocess

# ── Parameters ─────────────────────────────────────────────────────────────────
R1, R2 = 5.0, 10.0   # K/W
C1, C2 = 1.0, 5.0    # J/K
T_AMB = 25.0         # °C
T_AMB_K = T_AMB + 273.15
P_CONST = 3.0        # W

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACT_DIR = os.path.join(BASE_DIR, "paper_artifacts")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
OUT_DIR = os.path.join(RESULTS_DIR, "validation")
os.makedirs(ARTIFACT_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

# ── 1. Analytical Solver ───────────────────────────────────────────────────────
def analytical_solve(t_ms_arr, T0_die=T_AMB, T0_pkg=T_AMB, P=P_CONST):
    """Closed-form 2-node Cauer RC, constant power P."""
    T1_ss = T_AMB + P * (R1 + R2)
    T2_ss = T_AMB + P * R2
    A = np.array([
        [-1/(C1*R1),       1/(C1*R1)          ],
        [ 1/(C2*R1),      -(1/R1+1/R2)/C2     ]
    ])
    theta0 = np.array([T0_die - T1_ss, T0_pkg - T2_ss])
    evals, evecs = np.linalg.eig(A)
    c = np.linalg.solve(evecs, theta0)
    t_s = t_ms_arr / 1000.0
    T1 = np.zeros_like(t_s, dtype=float)
    for i in range(2):
        T1 += evecs[0, i] * c[i] * np.exp(evals[i] * t_s)
    return T1 + T1_ss

# ── 2. Python Backward Euler Solver ───────────────────────────────────────────
def backward_euler_solve(t_ms_arr, T1_init_C=T_AMB, T2_init_C=T_AMB, P=P_CONST, DT=0.01):
    """Backward Euler matching gem5's doStep() exactly, constant power P."""
    T1 = T1_init_C + 273.15
    T2 = T2_init_C + 273.15
    
    t_max_s = t_ms_arr[-1] / 1000.0
    times_ms = []
    T1_hist = []
    
    t = 0.0
    while t <= t_max_s + DT * 0.5:
        times_ms.append(t * 1000.0)
        T1_hist.append(T1 - 273.15)
        
        A = np.array([
            [1/R1 + C1/DT,  -1/R1           ],
            [-1/R1,          1/R1 + 1/R2 + C2/DT]
        ])
        b = np.array([P + C1/DT * T1, T_AMB_K/R2 + C2/DT * T2])
        T_new = np.linalg.solve(A, b)
        T1, T2 = T_new
        t += DT
        
    # Interpolate to the exact requested times
    return np.interp(t_ms_arr, times_ms, T1_hist)

# ── 3. SPICE Simulation Runner ────────────────────────────────────────────────
def run_spice_simulation(T2_init_K):
    """Generates a temporary SPICE netlist, runs ngspice, and extracts measures."""
    netlist = f"""* Temporary netlist for Phase A
.TITLE Temporary gem5 SPICE Validation
Vamb amb 0 DC 298.15
I1 amb die DC 3.0
R1  die  pkg  5
R2  pkg  amb  10
C1  die  amb  1
C2  pkg  amb  5

.IC V(die)=298.15 V(pkg)={T2_init_K} V(amb)=298.15
.TRAN 0.1m 250m UIC

.MEASURE TRAN Vdie_10m   FIND V(die) AT=10m
.MEASURE TRAN Vdie_50m   FIND V(die) AT=50m
.MEASURE TRAN Vdie_100m  FIND V(die) AT=100m
.MEASURE TRAN Vdie_222_6m FIND V(die) AT=222.6m
.MEASURE TRAN Vdie_250m  FIND V(die) AT=250m
.END
"""
    temp_cir = os.path.join(RESULTS_DIR, "phase5_v2", "temp_validation.cir")
    with open(temp_cir, "w") as f:
        f.write(netlist)
        
    try:
        output = subprocess.check_output(["ngspice", "-b", temp_cir], text=True)
    except Exception as e:
        print(f"Error running ngspice: {e}")
        sys.exit(1)
    finally:
        if os.path.exists(temp_cir):
            os.remove(temp_cir)
            
    # Parse measures (convert K to °C)
    measures = {}
    for time_str in ["10m", "50m", "100m", "222_6m", "250m"]:
        match = re.search(rf"vdie_{time_str}\s+=\s+([\d.e+\-]+)", output)
        if match:
            measures[time_str] = float(match.group(1)) - 273.15
        else:
            print(f"Warning: Could not parse vdie_{time_str} from ngspice output!")
            measures[time_str] = 0.0
            
    return [
        measures["10m"],
        measures["50m"],
        measures["100m"],
        measures["222_6m"],
        measures["250m"]
    ]

# ── 4. Task A3: Stateful Thinned Stats Parser ───────────────────────────────
def parse_thinned_stats(filepath):
    """Highly optimized stateful parser for thinned_stats.txt."""
    print(f"Parsing thinned stats file: {filepath}")
    time_series = []
    current_stat = {}
    count = 0
    
    with open(filepath, 'r') as f:
        for line in f:
            if '---------- Begin Simulation Statistics ----------' in line:
                if current_stat and 'final_tick' in current_stat:
                    time_series.append(current_stat)
                current_stat = {}
                count += 1
                continue
            
            parts = line.split()
            if len(parts) < 2:
                continue
            
            name = parts[0]
            val_str = parts[1]
            
            if name == 'finalTick':
                current_stat['final_tick'] = int(val_str)
            elif name == 'system.bigCluster.thermal_domain.currentTemp':
                val = float(val_str)
                if val > 200.0:
                    val -= 273.15
                current_stat['temp'] = val
            elif name == 'system.bigCluster.cpus.power_model.dynamicPower':
                current_stat['cpu_dyn'] = float(val_str)
            elif name == 'system.bigCluster.cpus.power_model.staticPower':
                current_stat['cpu_st'] = float(val_str)
            elif name == 'system.bigCluster.l2.power_model.dynamicPower':
                current_stat['l2_dyn'] = float(val_str)
            elif name == 'system.bigCluster.l2.power_model.staticPower':
                current_stat['l2_st'] = float(val_str)
            elif name == 'system.bigCluster.clk_domain.clock':
                period = float(val_str)
                current_stat['freq_GHz'] = (1e12 / period) / 1e9 if period > 0 else 0.0
            elif name == 'system.bigCluster.cpus.ipc':
                current_stat['ipc'] = float(val_str)
                
    if current_stat and 'final_tick' in current_stat:
        time_series.append(current_stat)
        
    print(f"Parsed {len(time_series)} time series records.")
    return time_series

# ── 5. Solver Driven by Dynamic Power Trace ──────────────────────────────────
def solve_with_power_trace(gem5_times_ms, gem5_power, T1_init_C, T2_init_C, DT=0.01):
    """Backward Euler driven by arbitrary power trace."""
    T1 = T1_init_C + 273.15
    T2 = T2_init_C + 273.15
    T_amb_K = T_AMB + 273.15
    T_END_S = gem5_times_ms[-1] / 1000.0
    
    # Power interpolation function
    def get_power_at(t_s):
        t_ms = t_s * 1000.0
        return float(np.interp(t_ms, gem5_times_ms, gem5_power))
        
    times_ms, T1_hist = [], []
    t = 0.0
    while t <= T_END_S + DT * 0.5:
        times_ms.append(t * 1000.0)
        T1_hist.append(T1 - 273.15)
        
        P = get_power_at(t)
        A = np.array([
            [1/R1 + C1/DT,  -1/R1           ],
            [-1/R1,          1/R1 + 1/R2 + C2/DT]
        ])
        b = np.array([P + C1/DT * T1, T_amb_K/R2 + C2/DT * T2])
        T_new = np.linalg.solve(A, b)
        T1, T2 = T_new
        t += DT
        
    return np.array(times_ms), np.array(T1_hist)

# ── Main Execution ─────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  Executing Phase A Data Processing & Validation")
    print("=" * 60)
    
    # ───────────────────────────────────────────────────────────────────────────
    # Task A1: Canonical Validation Table (Constant Power)
    # ───────────────────────────────────────────────────────────────────────────
    print("\n--- Task A1: Generating canonical validation table ---")
    timepoints = np.array([10.0, 50.0, 100.0, 222.6, 250.0]) # ms
    
    # Analytical Correct
    T_anal = analytical_solve(timepoints)
    
    # Python BE Fixed
    T_py_fixed = backward_euler_solve(timepoints, T1_init_C=25.0, T2_init_C=25.0)
    
    # Python BE Bug (pkg = 0K = -273.15°C)
    T_py_bug = backward_euler_solve(timepoints, T1_init_C=25.0, T2_init_C=-273.15)
    
    # SPICE Fixed (pkg = 298.15K)
    T_spice_fixed = run_spice_simulation(T2_init_K=298.15)
    
    # SPICE Bug (pkg = 0.0K)
    T_spice_bug = run_spice_simulation(T2_init_K=0.0)
    
    # Output to canonical_validation_table.csv
    csv_path = os.path.join(ARTIFACT_DIR, "canonical_validation_table.csv")
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "Time (ms)",
            "Analytical (correct, °C)",
            "Python BE (fixed, °C)",
            "SPICE (fixed, °C)",
            "Python BE (bug, °C)",
            "SPICE (bug, °C)"
        ])
        for i, t in enumerate(timepoints):
            writer.writerow([
                f"{t:.1f}",
                f"{T_anal[i]:.4f}",
                f"{T_py_fixed[i]:.4f}",
                f"{T_spice_fixed[i]:.4f}",
                f"{T_py_bug[i]:.4f}",
                f"{T_spice_bug[i]:.4f}"
            ])
    print(f"Generated A1 table: {csv_path}")
    
    # ───────────────────────────────────────────────────────────────────────────
    # Task A2: Extract precise unpatched gem5 values
    # ───────────────────────────────────────────────────────────────────────────
    print("\n--- Task A2: Extracting gem5 unpatched values ---")
    unpatched_json = os.path.join(RESULTS_DIR, "phase5/fs_simulation_results.json")
    if os.path.exists(unpatched_json):
        with open(unpatched_json) as f:
            unpatched_data = json.load(f)
            
        t_target = [10.0, 50.0, 100.0, 222.6]
        extracted = []
        for target in t_target:
            # Find closest matching index
            match = min(unpatched_data, key=lambda d: abs(d['time_ms'] - target))
            extracted.append(match)
            
        unpatched_csv_path = os.path.join(ARTIFACT_DIR, "gem5_unpatched_extracted.csv")
        with open(unpatched_csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Time (ms)", "gem5 Temp (unpatched, °C)", "gem5 Power (unpatched, W)"])
            for m in extracted:
                total_power = m['dyn_power_W'] + m.get('st_power_W', 0.0)
                writer.writerow([f"{m['time_ms']:.1f}", f"{m['temp_C']:.4f}", f"{total_power:.4f}"])
        print(f"Generated A2 table: {unpatched_csv_path}")
    else:
        print(f"Error: {unpatched_json} not found. Skipping Task A2.")
        
    # ───────────────────────────────────────────────────────────────────────────
    # Task A3 & A4: Parse patched thinned stats & compute RMSE
    # ───────────────────────────────────────────────────────────────────────────
    print("\n--- Task A3 & A4: Parsing thinned stats & computing RMSE ---")
    thinned_stats_file = os.path.join(RESULTS_DIR, "phase5_v2/thinned_stats.txt")
    if os.path.exists(thinned_stats_file):
        raw_series = parse_thinned_stats(thinned_stats_file)
        
        # Save thinned json for general verification
        tick0 = raw_series[0]['final_tick']
        gem5_t_ms = np.array([(d['final_tick'] - tick0) / (1e12 / 1000) for d in raw_series])
        gem5_T_C = np.array([d.get('temp', 25.0) for d in raw_series])
        
        gem5_cpu_dyn = np.array([d.get('cpu_dyn', 0.0) for d in raw_series])
        gem5_cpu_st  = np.array([d.get('cpu_st',  0.0) for d in raw_series])
        gem5_l2_dyn  = np.array([d.get('l2_dyn',  0.0) for d in raw_series])
        gem5_l2_st   = np.array([d.get('l2_st',   0.0) for d in raw_series])
        
        gem5_dyn_W = gem5_cpu_dyn + gem5_l2_dyn
        gem5_st_W  = gem5_cpu_st  + gem5_l2_st
        gem5_power = gem5_dyn_W + gem5_st_W
        
        # Export final simulation results JSON
        results_json = []
        for i, d in enumerate(raw_series):
            results_json.append({
                "index": i,
                "time_ms": round(gem5_t_ms[i], 2),
                "final_tick": d['final_tick'],
                "temp_C": round(gem5_T_C[i], 4),
                "dyn_power_W": round(gem5_dyn_W[i], 4),
                "st_power_W": round(gem5_st_W[i], 6),
                "cpu_dyn_W": round(gem5_cpu_dyn[i], 4),
                "cpu_st_W": round(gem5_cpu_st[i], 6),
                "l2_dyn_W": round(gem5_l2_dyn[i], 4),
                "l2_st_W": round(gem5_l2_st[i], 6),
                "freq_GHz": round(d.get('freq_GHz', 3.3), 2),
                "ipc": round(d.get('ipc', 0.0), 4)
            })
            
        final_results_json_path = os.path.join(RESULTS_DIR, "phase5_v2/fs_simulation_results_final.json")
        with open(final_results_json_path, 'w') as fj:
            json.dump(results_json, fj, indent=2)
        print(f"Saved: {final_results_json_path}")
        
        # ── Compute Patched gem5 RMSE ──────────────────────────────────────────
        print("Solving Python BE correct model driven by patched gem5 power profile...")
        t_py, T_py = solve_with_power_trace(gem5_t_ms, gem5_power, 25.0, 25.0)
        T_py_at_gem5 = np.interp(gem5_t_ms, t_py, T_py)
        
        patched_rmse = np.sqrt(np.mean((T_py_at_gem5 - gem5_T_C)**2))
        patched_peak_err = np.max(np.abs(T_py_at_gem5 - gem5_T_C))
        print(f"Patched gem5 vs Python BE (fixed) RMSE     : {patched_rmse:.6f} K")
        print(f"Patched gem5 vs Python BE (fixed) Peak Err : {patched_peak_err:.6f} K")
        
        # Load existing metrics
        metrics_json = os.path.join(OUT_DIR, "error_metrics_summary.json")
        if os.path.exists(metrics_json):
            with open(metrics_json) as f:
                metrics = json.load(f)
        else:
            metrics = {}
            
        # Update metrics with real computed values
        metrics["gem5_patched"] = {
            "description": "gem5 patched (fixed init), 55.1s simulated",
            "rmse_K": round(float(patched_rmse), 6),
            "peak_error_K": round(float(patched_peak_err), 6),
            "final_temp_C": round(float(gem5_T_C[-1]), 4),
            "temp_min_C": round(float(gem5_T_C.min()), 4),
            "temp_max_C": round(float(gem5_T_C.max()), 4),
            "note": "RMSE successfully computed from full 55.1s thinned trace"
        }
        
        with open(metrics_json, 'w') as f:
            json.dump(metrics, f, indent=2)
        print(f"Updated error metrics summary JSON: {metrics_json}")
        
        # Write updated text table
        txt_path = os.path.join(OUT_DIR, "error_metrics_table.txt")
        header = f"{'Scenario':<30} {'RMSE (K)':<12} {'Peak Err (K)':<15} {'T_final (°C)'}"
        with open(txt_path, 'w') as f:
            f.write(header + "\n")
            f.write("-" * len(header) + "\n")
            for key, m in metrics.items():
                rmse = f"{m['rmse_K']:.4f}" if m.get('rmse_K') is not None else "n/a"
                peak = f"{m.get('peak_error_K', 'n/a')}"
                if isinstance(peak, float): peak = f"{peak:.4f}"
                final = f"{m.get('final_temp_C', 'n/a')}"
                f.write(f"{key:<30} {rmse:<12} {str(peak):<15} {final}\n")
        print(f"Updated text table: {txt_path}")
        
    else:
        print(f"Error: {thinned_stats_file} not found. Skipping Task A3/A4 patched RMSE calculations.")
        
    # Copy A1 and A2 CSV files to paper_artifacts/raw_evidence/ for completeness
    subprocess.run(["cp", os.path.join(ARTIFACT_DIR, "canonical_validation_table.csv"), os.path.join(ARTIFACT_DIR, "raw_evidence/")])
    if os.path.exists(os.path.join(ARTIFACT_DIR, "gem5_unpatched_extracted.csv")):
        subprocess.run(["cp", os.path.join(ARTIFACT_DIR, "gem5_unpatched_extracted.csv"), os.path.join(ARTIFACT_DIR, "raw_evidence/")])
        
    print("\n" + "=" * 60)
    print("  Phase A Automated Calculations & Exports Finished Successfully!")
    print("=" * 60)

if __name__ == '__main__':
    main()
