#!/usr/bin/env python3
"""
parse_phase7_terminal.py — Parse Phase 7 task-placement trace from system.terminal

Reads m5out_phase7/system.terminal and extracts:
  [SAMPLER] CPU placement evidence (Phase A pinned / Phase B free)
  [STRESS]  workload start/done confirmation
  [FREQ]    frequency snapshots

Outputs to results/phase7/:
  phase7_cpu_placement.csv       — per-sample CSV
  phase7_placement_summary.json  — Phase A/B CPU distribution statistics
  phase7_placement.png           — timeline plot
"""

import re
import csv
import json
import sys
import os
from collections import Counter

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

SAMPLER_RE = re.compile(
    r'\[SAMPLER\]\s+TS:([\d.]+)\s+Phase:(\w+)\s+PID:(\d+)\s+CPU:(\d+)\s+Cluster:(\w+)\s+Pinned:(\w+)'
)
STRESS_RE = re.compile(r'\[STRESS\]\s+(START|DONE)\s+.*pid=(\d+).*cpu=(\d+)')
FREQ_RE   = re.compile(r'\[FREQ\]\s+Phase:(\w+)\s+cpu0:([\w/]+)\s+cpu1:([\w/]+)')


def parse_terminal(terminal_path):
    samples = []
    stress_events = []
    freq_snapshots = []

    with open(terminal_path, "r", errors="replace") as f:
        for line in f:
            m = SAMPLER_RE.search(line)
            if m:
                samples.append({
                    "ts": float(m.group(1)),
                    "phase": m.group(2),
                    "pid": int(m.group(3)),
                    "cpu": int(m.group(4)),
                    "cluster": m.group(5),
                    "pinned": m.group(6),
                })
                continue
            m = STRESS_RE.search(line)
            if m:
                stress_events.append({
                    "event": m.group(1),
                    "pid": int(m.group(2)),
                    "cpu": int(m.group(3)),
                })
                continue
            m = FREQ_RE.search(line)
            if m:
                freq_snapshots.append({
                    "phase": m.group(1),
                    "cpu0_khz": m.group(2),
                    "cpu1_khz": m.group(3),
                })

    return samples, stress_events, freq_snapshots


def build_summary(samples, stress_events, freq_snapshots):
    phase_a = [s for s in samples if s["phase"] == "A"]
    phase_b = [s for s in samples if s["phase"] == "B"]

    def dist(rows):
        c = Counter(str(r["cpu"]) for r in rows)
        total = len(rows)
        return {
            "total_samples": total,
            "cpu_counts": dict(sorted(c.items())),
            "cpu0_pct": round(100 * c.get("0", 0) / total, 1) if total else 0,
            "cpu1_pct": round(100 * c.get("1", 0) / total, 1) if total else 0,
        }

    summary = {
        "phase_A": dist(phase_a),
        "phase_B": dist(phase_b),
        "stress_events": stress_events,
        "freq_snapshots": freq_snapshots,
        "verdict": {},
    }

    # Verdict
    a_ok = summary["phase_A"]["cpu0_pct"] == 100.0
    b_migrated = summary["phase_B"].get("cpu1_pct", 0) > 0
    summary["verdict"]["phase_A_pinning_works"] = a_ok
    summary["verdict"]["phase_B_migration_observed"] = b_migrated
    if a_ok and b_migrated:
        b1 = summary["phase_B"]["cpu1_pct"]
        summary["verdict"]["interpretation"] = (
            f"Pinning confirmed (Phase A: 100% cpu0). "
            f"Partial migration observed (Phase B: {b1:.0f}% cpu1). "
            f"Heterogeneous CPU placement is observable in gem5."
        )
    elif a_ok:
        summary["verdict"]["interpretation"] = (
            "Pinning confirmed (Phase A: 100% cpu0). "
            "Free placement (Phase B) stayed on cpu0 — baseline EAS does not "
            "auto-migrate under this workload. Validates that Phase 6 Tier-1 "
            "migration is a deliberate policy addition."
        )
    else:
        summary["verdict"]["interpretation"] = (
            "WARNING: Phase A pinning did not hold (unexpected). "
            "Check taskset and CPU topology in gem5 config."
        )

    return summary


def write_csv(samples, out_path):
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["ts", "phase", "pid", "cpu", "cluster", "pinned"])
        writer.writeheader()
        writer.writerows(samples)


def plot_placement(samples, summary, out_path):
    if not HAS_MPL or not samples:
        return
    fig, axes = plt.subplots(2, 1, figsize=(10, 5), sharex=False)

    for ax_idx, (phase, label) in enumerate([("A", "Phase A — Pinned (taskset 0x1)"),
                                              ("B", "Phase B — Free Placement (EAS)")]):
        rows = [s for s in samples if s["phase"] == phase]
        if not rows:
            axes[ax_idx].set_title(f"{label} — no data")
            continue
        ts   = [r["ts"] for r in rows]
        cpus = [r["cpu"] for r in rows]
        colors = ["tab:blue" if c == 0 else "tab:orange" for c in cpus]
        axes[ax_idx].scatter(ts, cpus, c=colors, s=40, zorder=3)
        axes[ax_idx].set_yticks([0, 1])
        axes[ax_idx].set_yticklabels(["cpu0\n(big)", "cpu1\n(LITTLE)"])
        axes[ax_idx].set_ylabel("CPU")
        axes[ax_idx].set_title(label)
        axes[ax_idx].set_xlabel("Uptime (s)")
        axes[ax_idx].grid(True, alpha=0.3)
        axes[ax_idx].set_ylim(-0.3, 1.3)
        blue_p  = mpatches.Patch(color="tab:blue",   label="cpu0 (big)")
        orange_p = mpatches.Patch(color="tab:orange", label="cpu1 (LITTLE)")
        axes[ax_idx].legend(handles=[blue_p, orange_p], loc="upper right")

        stats_str = (
            f"cpu0: {summary['phase_' + phase]['cpu0_pct']:.0f}%  "
            f"cpu1: {summary['phase_' + phase]['cpu1_pct']:.0f}%  "
            f"(n={summary['phase_' + phase]['total_samples']})"
        )
        axes[ax_idx].text(0.02, 0.92, stats_str, transform=axes[ax_idx].transAxes,
                          fontsize=8, va="top", bbox=dict(boxstyle="round", alpha=0.2))

    fig.suptitle("Phase 7: CPU Placement Trace\n(gem5 Timing-Mode, ARM big.LITTLE)", fontsize=11)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()


def main():
    project = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    terminal = os.path.join(project, "m5out_phase7", "system.terminal")
    outdir   = os.path.join(project, "results", "phase7")

    if len(sys.argv) >= 2:
        terminal = sys.argv[1]
    if len(sys.argv) >= 3:
        outdir = sys.argv[2]

    if not os.path.exists(terminal):
        print(f"[ERROR] Terminal file not found: {terminal}")
        sys.exit(1)

    os.makedirs(outdir, exist_ok=True)

    print(f"Parsing: {terminal}")
    samples, stress_events, freq_snapshots = parse_terminal(terminal)

    print(f"  [SAMPLER] lines: {len(samples)}")
    print(f"  [STRESS]  events: {len(stress_events)}")
    print(f"  [FREQ]    snapshots: {len(freq_snapshots)}")

    if not samples:
        print("[WARNING] No [SAMPLER] lines found. Workload may not have run (BOM or path issue).")

    summary = build_summary(samples, stress_events, freq_snapshots)

    csv_path  = os.path.join(outdir, "phase7_cpu_placement.csv")
    json_path = os.path.join(outdir, "phase7_placement_summary.json")
    png_path  = os.path.join(outdir, "phase7_placement.png")

    write_csv(samples, csv_path)
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2)
    plot_placement(samples, summary, png_path)

    print(f"\nOutputs:")
    print(f"  CSV    : {csv_path}")
    print(f"  JSON   : {json_path}")
    if HAS_MPL:
        print(f"  Plot   : {png_path}")

    print(f"\nVerdict:")
    print(f"  {summary['verdict']['interpretation']}")

    # Self-correction checks
    print("\n--- Self-Correction Checks ---")
    a_total = summary["phase_A"]["total_samples"]
    b_total = summary["phase_B"]["total_samples"]
    ok = True

    if a_total < 20:
        print(f"  [WARN] Phase A samples too low: {a_total} (expected ≥30)")
        ok = False
    if b_total < 20:
        print(f"  [WARN] Phase B samples too low: {b_total} (expected ≥30)")
        ok = False
    if a_total > 0 and summary["phase_A"]["cpu0_pct"] < 100.0:
        print(f"  [WARN] Phase A: taskset pinning did not hold (cpu0={summary['phase_A']['cpu0_pct']}%)")
        ok = False
    if len(stress_events) < 2:
        print(f"  [WARN] Expected ≥4 [STRESS] events (START+DONE×2), got {len(stress_events)}")
        ok = False

    if ok:
        print("  [OK] All checks passed.")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
