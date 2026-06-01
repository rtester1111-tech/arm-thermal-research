# Simulation Scope and Future Hardware Calibration

This repository is a simulation artifact. The submitted Paper 1 and Paper 2
results were not calibrated against measurements from a physical ARM device.

The current evidence base consists of:

- gem5 thermal-model behavior and configuration traces;
- analytical, Python, and SPICE cross-checks for the Cauer RC path;
- trace-driven co-simulation for package-aware scheduling experiments;
- generated figures, logs, and scripts included in the public artifact tree.

No board-level temperature traces, silicon power measurements, hardware
power-monitor logs, external power-meter captures, or hardware sensor
calibration files are included or claimed.

## How to Interpret the Current Results

Paper 1 uses simulation and independent solvers to check physical
admissibility of gem5's native Cauer RC thermal path. The key result is the
thermal-initialization artifact and its correction; it does not require matching
a specific silicon device.

Paper 2 evaluates a trace-driven package-aware scheduling mechanism inside a
gem5-based workflow. Its RC parameters are simulation parameters, not
measurements fitted to a named physical chip. The paper should therefore be read
as a simulator-level artifact, not as a hardware characterization study.

## What Hardware Calibration Would Require

A future hardware-calibrated extension would need new evidence before making
device-specific claims:

1. A named target platform, board revision, operating system, cooling condition,
   ambient temperature, and firmware/kernel configuration.
2. Time-aligned temperature, power, frequency, and workload traces collected
   under controlled workloads.
3. A documented procedure for fitting RC parameters from those traces.
4. A hold-out validation run showing that the fitted parameters predict an
   independent workload or thermal transient.
5. A clear uncertainty discussion covering sensor placement, sampling rate,
   power attribution, and thermal boundary conditions.

Until those measurements exist, this repository intentionally describes hardware
calibration as future work only.
