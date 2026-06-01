#!/usr/bin/env python3
"""
compute_errors.py — Quantitative Error Metrics for Thermal Solver Comparison

Computes four metrics comparing each solver/scenario against the analytical baseline:
  1. RMSE        — root-mean-square error over the full trace (K)
  2. Peak Error  — maximum instantaneous absolute error (K)
  3. Settling Time Deviation — |t_settle_solver - t_settle_analytical| (s)
  4. Steady-State Error — |T_final_solver - T_final_analytical| (K)

Scenarios evaluated:
  A. Python Backward Euler, correct init (should be near-zero error)
  B. Python Backward Euler, bug init (node_pkg = 0 K)
  C. gem5 unpatched (from results/phase5/fs_simulation_results.json)
  D. gem5 patched   (from results/phase5_v2/bugfix_validation_final.json)

Output:
  results/validation/error_metrics_summary.json
  results/validation/error_metrics_table.txt
"""

import numpy as np
import json
import os

# ── Parameters ─────────────────────────────────────────────────────────────────
R1, R2 = 5.0, 10.0
C1, C2 = 1.0, 5.0
T_AMB = 25.0
P = 3.0
T_END = 0.250   # s

SETTLE_THRESHOLD = 0.01  # K from steady-state (1% criterion)

BASE_DIR = os.path.join(os.path.dirname(__file__), "../..")
OUT_DIR = os.path.join(BASE_DIR, "results/validation")
os.makedirs(OUT_DIR, exist_ok=True)


# ── Analytical solution ────────────────────────────────────────────────────────

def two_node_analytical(t_arr, T0_die=T_AMB, T0_pkg=T_AMB, P=P):
    T1_ss = T_AMB + P * (R1 + R2)
    T2_ss = T_AMB + P * R2
    A = np.array([
        [-1/(C1*R1),       1/(C1*R1)          ],
        [ 1/(C2*R1),      -(1/R1+1/R2)/C2     ]
    ])
    theta0 = np.array([T0_die - T1_ss, T0_pkg - T2_ss])
    evals, evecs = np.linalg.eig(A)
    c = np.linalg.solve(evecs, theta0)
    T1 = np.zeros_like(t_arr, dtype=float)
    for i in range(2):
        T1 += evecs[0, i] * c[i] * np.exp(evals[i] * t_arr)
    return T1 + T1_ss


def backward_euler(t_end, dt, T1_init=T_AMB, T2_init=T_AMB, P=P):
    T1 = T1_init + 273.15
    T2 = T2_init + 273.15
    T_amb_K = T_AMB + 273.15
    times, T1_hist = [], []
    t = 0.0
    while t <= t_end + dt * 0.5:
        times.append(t)
        T1_hist.append(T1 - 273.15)
        A = np.array([[1/R1+C1/dt, -1/R1], [-1/R1, 1/R1+1/R2+C2/dt]])
        b = np.array([P+C1/dt*T1, T_amb_K/R2+C2/dt*T2])
        T_new = np.linalg.solve(A, b)
        T1, T2 = T_new
        t += dt
    return np.array(times), np.array(T1_hist)


# ── Metrics computation ────────────────────────────────────────────────────────

def settling_time(times, temps, T_ss, threshold=SETTLE_THRESHOLD):
    """First time temperature stays within threshold of T_ss."""
    for i in range(len(times)-1, -1, -1):
        if abs(temps[i] - T_ss) > threshold:
            return times[min(i+1, len(times)-1)]
    return times[0]


def compute_metrics(t_ref, T_ref, t_test, T_test, T_ss_anal):
    T_interp = np.interp(t_ref, t_test, T_test)
    rmse = np.sqrt(np.mean((T_ref - T_interp)**2))
    peak_err = np.max(np.abs(T_ref - T_interp))
    T_ss_test = T_test[-1]
    ss_error = abs(T_ss_test - T_ss_anal)
    t_settle_anal = settling_time(t_ref, T_ref, T_ss_anal)
    t_settle_test = settling_time(t_test, T_test, T_ss_anal)
    settle_dev = abs(t_settle_test - t_settle_anal)
    return {
        "rmse_K": round(rmse, 6),
        "peak_error_K": round(peak_err, 6),
        "steady_state_error_K": round(ss_error, 6),
        "settling_time_deviation_s": round(settle_dev, 6),
        "final_temp_C": round(T_ss_test, 4),
    }


def main():
    # Reference grid
    t_ref = np.linspace(0, T_END, int(T_END / 1e-5) + 1)
    T_anal = two_node_analytical(t_ref)
    T_ss_anal = T_AMB + P * (R1 + R2)  # 70°C theoretical; ~25.03°C at 250ms

    # Use the actual analytical value at t_end as pseudo-steady-state for the
    # short (250ms) window — full steady state at 70°C takes ~5*tau_pkg = 375 s
    T_ss_window = T_anal[-1]

    results = {}

    # Scenario A: Python BE, correct init
    t_a, T_a = backward_euler(T_END, 0.01)
    results["python_BE_correct"] = compute_metrics(t_ref, T_anal, t_a, T_a, T_ss_window)
    results["python_BE_correct"]["description"] = "Python Backward Euler, node_pkg=25°C (correct)"

    # Scenario B: Python BE, bug init
    t_b, T_b = backward_euler(T_END, 0.01, T2_init=-273.15)
    results["python_BE_bug"] = compute_metrics(t_ref, T_anal, t_b, T_b, T_ss_window)
    results["python_BE_bug"]["description"] = "Python Backward Euler, node_pkg=0K (bug)"

    # Scenario C: gem5 unpatched (load from JSON)
    phase5_json = os.path.join(BASE_DIR, "results/phase5/fs_simulation_results.json")
    if os.path.exists(phase5_json):
        with open(phase5_json) as f:
            phase5_data = json.load(f)
        t_g5 = np.array([d['time_ms'] / 1000 for d in phase5_data])
        T_g5 = np.array([d['temp_C'] for d in phase5_data])
        results["gem5_unpatched"] = compute_metrics(t_ref, T_anal, t_g5, T_g5, T_ss_window)
        results["gem5_unpatched"]["description"] = "gem5 unpatched (Absolute-Zero Bug)"
    else:
        results["gem5_unpatched"] = {"description": "data not found", "rmse_K": None}

    # Scenario D: gem5 patched (load final JSON)
    phase55_json = os.path.join(BASE_DIR, "results/phase5_v2/bugfix_validation_final.json")
    if os.path.exists(phase55_json):
        with open(phase55_json) as f:
            summary = json.load(f)
        p55 = summary.get("phase5_5_fixed", {})
        results["gem5_patched"] = {
            "description": "gem5 patched (fixed init), 55.1s simulated",
            "rmse_K": None,  # full trace not available as time-series here
            "final_temp_C": p55.get("temp_final_C"),
            "temp_min_C": p55.get("temp_min_C"),
            "temp_max_C": p55.get("temp_max_C"),
            "note": "RMSE not computed (55s trace not loaded as array)"
        }
    else:
        results["gem5_patched"] = {"description": "data not found"}

    # ── Print table ───────────────────────────────────────────────────────────
    header = f"{'Scenario':<30} {'RMSE (K)':<12} {'Peak Err (K)':<15} {'SS Err (K)':<12} {'T_final (°C)'}"
    print(header)
    print("-" * len(header))

    for key, m in results.items():
        rmse = f"{m['rmse_K']:.4f}" if m.get('rmse_K') is not None else "n/a"
        peak = f"{m.get('peak_error_K', 'n/a')}"
        if isinstance(peak, float):
            peak = f"{peak:.4f}"
        ss_err = f"{m.get('steady_state_error_K', 'n/a')}"
        if isinstance(ss_err, float):
            ss_err = f"{ss_err:.4f}"
        final = f"{m.get('final_temp_C', 'n/a')}"
        print(f"{key:<30} {rmse:<12} {str(peak):<15} {str(ss_err):<12} {final}")

    # Save
    out_path = os.path.join(OUT_DIR, "error_metrics_summary.json")
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {out_path}")

    # Text table
    txt_path = os.path.join(OUT_DIR, "error_metrics_table.txt")
    with open(txt_path, 'w') as f:
        f.write(header + "\n")
        f.write("-" * len(header) + "\n")
        for key, m in results.items():
            rmse = f"{m['rmse_K']:.4f}" if m.get('rmse_K') is not None else "n/a"
            peak = f"{m.get('peak_error_K', 'n/a')}"
            if isinstance(peak, float): peak = f"{peak:.4f}"
            ss_err = f"{m.get('steady_state_error_K', 'n/a')}"
            if isinstance(ss_err, float): ss_err = f"{ss_err:.4f}"
            final = f"{m.get('final_temp_C', 'n/a')}"
            f.write(f"{key:<30} {rmse:<12} {str(peak):<15} {str(ss_err):<12} {final}\n")
    print(f"Saved: {txt_path}")


if __name__ == '__main__':
    main()
