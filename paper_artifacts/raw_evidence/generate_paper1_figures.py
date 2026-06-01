#!/usr/bin/env python3
"""Generate vector PDF figures for Paper 1 without matplotlib.

The Codex runtime used for this handoff includes numpy and reportlab, but not
matplotlib.  This script keeps the figures reproducible from the canonical
CSV/JSON evidence files in this directory.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FIG_DIR = ROOT / "paper1_latex_draft" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

R1, R2 = 5.0, 10.0
C1, C2 = 1.0, 5.0
T_AMB_C = 25.0
T_AMB_K = 298.15
THERMAL_DT = 0.01


def two_node_closed_form(t_s: np.ndarray, t0_die=T_AMB_C, t0_pkg=T_AMB_C, p_w=3.0):
    """Closed-form die temperature for the 2-node Cauer network."""
    t1_ss = T_AMB_C + p_w * (R1 + R2)
    t2_ss = T_AMB_C + p_w * R2
    a = np.array([
        [-1 / (C1 * R1), 1 / (C1 * R1)],
        [1 / (C2 * R1), -(1 / R1 + 1 / R2) / C2],
    ])
    theta0 = np.array([t0_die - t1_ss, t0_pkg - t2_ss])
    evals, evecs = np.linalg.eig(a)
    coeff = np.linalg.solve(evecs, theta0)
    t1 = np.zeros_like(t_s, dtype=float)
    for i in range(2):
        t1 += evecs[0, i] * coeff[i] * np.exp(evals[i] * t_s)
    return t1 + t1_ss


def backward_euler_series(t_end_s, dt_s, t1_init_c=T_AMB_C, t2_init_c=T_AMB_C, power_fn=None):
    """Backward Euler die trace for the 2-node Cauer network."""
    if power_fn is None:
        power_fn = lambda _t: 3.0

    t1 = t1_init_c + 273.15
    t2 = t2_init_c + 273.15
    times = []
    temps = []
    t = 0.0
    while t <= t_end_s + 1e-12:
        times.append(t)
        temps.append(t1 - 273.15)
        p_w = float(power_fn(t))
        a00 = 1 / R1 + C1 / dt_s
        a01 = -1 / R1
        a10 = -1 / R1
        a11 = 1 / R1 + 1 / R2 + C2 / dt_s
        b0 = p_w + C1 / dt_s * t1
        b1 = T_AMB_K / R2 + C2 / dt_s * t2
        det = a00 * a11 - a01 * a10
        t1, t2 = (b0 * a11 - a01 * b1) / det, (a00 * b1 - b0 * a10) / det
        t += dt_s
    return np.array(times), np.array(temps)


def draw_polyline(c, points, color, width=1.2, dash=None):
    c.setStrokeColor(color)
    c.setLineWidth(width)
    c.setDash(dash or [])
    path = c.beginPath()
    path.moveTo(points[0][0], points[0][1])
    for x, y in points[1:]:
        path.lineTo(x, y)
    c.drawPath(path)
    c.setDash([])


def draw_marker(c, x, y, color, radius=2.0):
    c.setFillColor(color)
    c.circle(x, y, radius, stroke=0, fill=1)


def draw_axes(c, x0, y0, w, h, x_min, x_max, y_min, y_max, x_label, y_label, title):
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.8)
    c.line(x0, y0, x0 + w, y0)
    c.line(x0, y0, x0, y0 + h)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(x0 + w / 2, y0 + h + 16, title)
    c.setFont("Helvetica", 7)
    c.drawCentredString(x0 + w / 2, y0 - 22, x_label)
    c.saveState()
    c.translate(x0 - 32, y0 + h / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, y_label)
    c.restoreState()

    for i in range(6):
        xt = x_min + i * (x_max - x_min) / 5
        x = x0 + (xt - x_min) / (x_max - x_min) * w
        c.setStrokeColor(colors.lightgrey)
        c.line(x, y0, x, y0 + h)
        c.setStrokeColor(colors.black)
        c.line(x, y0 - 3, x, y0 + 3)
        c.drawCentredString(x, y0 - 12, f"{xt:g}")
    for i in range(5):
        yt = y_min + i * (y_max - y_min) / 4
        y = y0 + (yt - y_min) / (y_max - y_min) * h
        c.setStrokeColor(colors.lightgrey)
        c.line(x0, y, x0 + w, y)
        c.setStrokeColor(colors.black)
        c.line(x0 - 3, y, x0 + 3, y)
        c.drawRightString(x0 - 6, y - 2.5, f"{yt:.1f}")

    def mapper(xv, yv):
        x = x0 + (xv - x_min) / (x_max - x_min) * w
        y = y0 + (yv - y_min) / (y_max - y_min) * h
        return x, y

    return mapper


def draw_legend(c, x, y, entries):
    c.setFont("Helvetica", 7)
    for i, (label, color, dash) in enumerate(entries):
        yy = y - i * 11
        c.setStrokeColor(color)
        c.setLineWidth(1.6)
        c.setDash(dash or [])
        c.line(x, yy, x + 20, yy)
        c.setDash([])
        c.setFillColor(colors.black)
        c.drawString(x + 25, yy - 2.5, label)


def generate_cauer_topology():
    out = FIG_DIR / "cauer_topology.pdf"
    c = canvas.Canvas(str(out), pagesize=(5.2 * inch, 2.5 * inch))
    c.setTitle("Cauer two-node thermal topology")
    c.setFont("Helvetica", 8)
    y = 1.45 * inch
    x_die = 1.35 * inch
    x_pkg = 2.75 * inch
    x_amb = 4.15 * inch

    def node(x, label):
        c.setFillColor(colors.white)
        c.setStrokeColor(colors.black)
        c.circle(x, y, 5, fill=1)
        c.setFillColor(colors.black)
        c.drawCentredString(x, y + 14, label)

    def resistor(x1, x2, label):
        c.setStrokeColor(colors.black)
        c.setLineWidth(1)
        x = x1 + 8
        c.line(x1 + 5, y, x, y)
        seg = (x2 - x1 - 26) / 6
        pts = [(x, y)]
        up = True
        for i in range(1, 7):
            pts.append((x + i * seg, y + (6 if up else -6)))
            up = not up
        pts.append((x2 - 8, y))
        path = c.beginPath()
        path.moveTo(*pts[0])
        for p in pts[1:]:
            path.lineTo(*p)
        c.drawPath(path)
        c.line(x2 - 8, y, x2 - 5, y)
        c.drawCentredString((x1 + x2) / 2, y + 18, label)

    def capacitor(x, label):
        c.setStrokeColor(colors.black)
        c.line(x, y - 5, x, y - 38)
        c.line(x - 14, y - 38, x + 14, y - 38)
        c.line(x - 14, y - 48, x + 14, y - 48)
        c.line(x, y - 48, x, y - 75)
        c.line(x - 20, y - 75, x + 20, y - 75)
        c.line(x - 14, y - 80, x + 14, y - 80)
        c.line(x - 8, y - 85, x + 8, y - 85)
        c.drawCentredString(x + 35, y - 48, label)

    node(x_die, "T_die")
    node(x_pkg, "T_pkg")
    node(x_amb, "T_amb")
    resistor(x_die, x_pkg, "R_die")
    resistor(x_pkg, x_amb, "R_pkg")
    capacitor(x_die, "C_die")
    capacitor(x_pkg, "C_pkg")
    c.setStrokeColor(colors.HexColor("#2ca02c"))
    c.setLineWidth(1.2)
    c.line(x_die, y + 62, x_die, y + 12)
    c.setFillColor(colors.HexColor("#2ca02c"))
    c.triangle = None
    path = c.beginPath()
    path.moveTo(x_die, y + 12)
    path.lineTo(x_die - 4, y + 22)
    path.lineTo(x_die + 4, y + 22)
    path.close()
    c.drawPath(path, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.drawCentredString(x_die, y + 70, "P_in")
    c.setFont("Helvetica", 7)
    c.drawString(0.32 * inch, 0.25 * inch, "Thermal-electrical duality: power=current, temperature=voltage, ambient=ground/reference")
    c.showPage()
    c.save()
    return out


def generate_transient_comparison():
    out = FIG_DIR / "transient_comparison.pdf"
    c = canvas.Canvas(str(out), pagesize=landscape((5.6 * inch, 3.4 * inch)))
    c.setTitle("Five-way transient comparison")

    t_dense_ms = np.linspace(0, 250, 501)
    t_dense_s = t_dense_ms / 1000
    fixed_anal = two_node_closed_form(t_dense_s)
    bug_anal = two_node_closed_form(t_dense_s, t0_pkg=-273.15)
    t_be, fixed_be = backward_euler_series(0.25, THERMAL_DT)
    _, bug_be = backward_euler_series(0.25, THERMAL_DT, t2_init_c=-273.15)
    t_be_ms = t_be * 1000

    with open(HERE / "canonical_validation_table.csv", newline="") as f:
        rows = list(csv.reader(f))
    body = rows[1:]
    # Use column positions because the degree symbol in handoff CSVs may be
    # mojibake depending on the shell code page.
    t_anchor = np.array([float(r[0]) for r in body])
    spice_fixed = np.array([float(r[3]) for r in body])
    spice_bug = np.array([float(r[5]) for r in body])

    x0, y0, w, h = 0.55 * inch, 0.55 * inch, 4.45 * inch, 2.25 * inch
    map_xy = draw_axes(c, x0, y0, w, h, 0, 250, 10, 26.5,
                       "Time after startup (ms)", "Die temperature (°C)",
                       "Constant 3 W startup response")

    series = [
        ("Analytical closed-form", t_dense_ms, fixed_anal, colors.black, None, 1.5),
        ("Python BE fixed", t_be_ms, fixed_be, colors.HexColor("#2ca02c"), [4, 2], 1.4),
        ("SPICE fixed", t_anchor, spice_fixed, colors.HexColor("#1f77b4"), [1, 2], 1.4),
        ("Python BE bug", t_be_ms, bug_be, colors.HexColor("#d62728"), [4, 2], 1.5),
        ("SPICE bug", t_anchor, spice_bug, colors.HexColor("#ff7f0e"), [1, 2], 1.5),
    ]
    for _label, xs, ys, col, dash, lw in series:
        pts = [map_xy(float(x), float(y)) for x, y in zip(xs, ys)]
        draw_polyline(c, pts, col, lw, dash)
    for x, y in zip(t_anchor, spice_fixed):
        draw_marker(c, *map_xy(float(x), float(y)), colors.HexColor("#1f77b4"), 1.8)
    for x, y in zip(t_anchor, spice_bug):
        draw_marker(c, *map_xy(float(x), float(y)), colors.HexColor("#ff7f0e"), 1.8)

    draw_legend(c, 3.45 * inch, 2.55 * inch,
                [(label, col, dash) for label, _xs, _ys, col, dash, _lw in series])
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.black)
    c.drawString(0.72 * inch, 0.25 * inch,
                 "At 250 ms: fixed = 25.73 °C; bug-equivalent = 11.30-11.32 °C.")
    c.showPage()
    c.save()
    return out


def generate_residual_plot():
    out = FIG_DIR / "residual_python_vs_gem5.pdf"
    data = json.loads((HERE / "fs_simulation_results_final.json").read_text())
    metrics = json.loads((HERE / "error_metrics_summary.json").read_text())
    reported_rmse = metrics["gem5_patched"]["rmse_K"]

    # Reconstruct a Python BE trace driven by the first observed bigCluster power
    # in each 10 ms thermal step. This mirrors the handoff's RMSE scale and makes
    # the residual visually interpretable without needing the original remote
    # post-processing script.
    t1 = t2 = T_AMB_K
    current = T_AMB_C
    next_boundary = 10.0
    acc = []
    pred = []
    for d in data:
        t_ms = float(d["time_ms"])
        while t_ms >= next_boundary - 1e-9:
            p_w = acc[0] if acc else 0.0
            t1_arr, vals = backward_euler_series(THERMAL_DT, THERMAL_DT, t1 - 273.15, t2 - 273.15, lambda _t, p=p_w: p)
            # backward_euler_series returns the initial point and one updated point.
            current = float(vals[-1])
            # Recompute package node for continuity using the scalar step.
            a00 = 1 / R1 + C1 / THERMAL_DT
            a01 = -1 / R1
            a10 = -1 / R1
            a11 = 1 / R1 + 1 / R2 + C2 / THERMAL_DT
            b0 = p_w + C1 / THERMAL_DT * t1
            b1 = T_AMB_K / R2 + C2 / THERMAL_DT * t2
            det = a00 * a11 - a01 * a10
            t1, t2 = (b0 * a11 - a01 * b1) / det, (a00 * b1 - b0 * a10) / det
            current = t1 - 273.15
            acc = []
            next_boundary += 10.0
        pred.append(current)
        acc.append(float(d["dyn_power_W"]) + float(d["st_power_W"]))

    times_s = np.array([float(d["time_ms"]) / 1000 for d in data])
    gem5 = np.array([float(d["temp_C"]) for d in data])
    py_be = np.array(pred)
    residual = gem5 - py_be

    stride = max(1, len(data) // 2500)
    xs = times_s[::stride]
    ys_g = gem5[::stride]
    ys_p = py_be[::stride]
    ys_r = residual[::stride]

    c = canvas.Canvas(str(out), pagesize=landscape((6.0 * inch, 4.2 * inch)))
    c.setTitle("Patched gem5 residual against Python BE")

    map_top = draw_axes(c, 0.65 * inch, 2.25 * inch, 4.6 * inch, 1.35 * inch,
                        0, 55.2, 24.8, 29.0,
                        "Time (s)", "Temp. (°C)", "Patched gem5 vs Python BE")
    draw_polyline(c, [map_top(x, y) for x, y in zip(xs, ys_g)], colors.HexColor("#1f77b4"), 1.3)
    draw_polyline(c, [map_top(x, y) for x, y in zip(xs, ys_p)], colors.HexColor("#2ca02c"), 1.0, [4, 2])
    draw_legend(c, 4.2 * inch, 3.45 * inch,
                [("patched gem5", colors.HexColor("#1f77b4"), None),
                 ("Python BE", colors.HexColor("#2ca02c"), [4, 2])])

    max_abs = max(0.04, float(np.max(np.abs(ys_r))))
    map_bot = draw_axes(c, 0.65 * inch, 0.55 * inch, 4.6 * inch, 1.05 * inch,
                        0, 55.2, -max_abs, max_abs,
                        "Time (s)", "dT (°C)", "Residual: gem5 - Python BE")
    draw_polyline(c, [map_bot(x, y) for x, y in zip(xs, ys_r)], colors.HexColor("#d62728"), 1.0)
    c.setFont("Helvetica", 7)
    c.drawString(3.55 * inch, 0.35 * inch,
                 f"Reported RMSE from evidence JSON: {reported_rmse:.4f} K; peak error = {metrics['gem5_patched']['peak_error_K']:.4f} K")
    c.showPage()
    c.save()
    return out


def main():
    for path in [generate_cauer_topology(), generate_transient_comparison(), generate_residual_plot()]:
        print(path)


if __name__ == "__main__":
    main()
