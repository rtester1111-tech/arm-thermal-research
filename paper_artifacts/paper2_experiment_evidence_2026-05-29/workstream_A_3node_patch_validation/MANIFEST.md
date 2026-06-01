# Workstream A Evidence Manifest
# 3-Node ThermalNode Temperature Export — Patched gem5 Smoke Run

Date: 2026-05-29
Build environment: local Linux/gem5 full-system test host
gem5 version: DEVELOP-FOR-25.1
Patch applied: patches/thermal_node_temperature_stat.patch (manually adapted for functor API)

## Files

| File | Bytes | SHA256 | Purpose |
|------|-------|--------|---------|
| stats.txt | 921600 (901 KB) | c028a199d37f58d6ebc953ce780f13a8c3d73938e3876fd336a73ced1cda20dd | gem5 periodic stats output, 2 complete dumps |
| config.ini | private local run artifact | omitted from public release | Full gem5 SimObject configuration |

## Smoke Run Command

```
gem5.opt --outdir=<output-dir> \
  configs/example/arm/fs_thermal.py \
  --kernel=<path-to-vmlinux> \
  --disk=~/.cache/gem5/arm64-ubuntu-20.04-img-1.0.0 \
  --bootloader=~/.cache/gem5/arm64-bootloader-foundation-2.0.0 \
  --cpu-type=timing --machine-type=VExpress_GEM5_Foundation \
  --big-cpus=1 --little-cpus=1 --caches \
  --big-cpu-clock=3.3GHz --little-cpu-clock=2.0GHz --mem-size=2GiB \
  --enable-3node --thermal-step=0.01 --stats-period=0.1 --ambient-temp=25C \
  --r-die-pkg=5.0 --r-pkg-amb=10.0 --r-pkg-hs=2.0 \
  --r-hs-amb=8.0 --c-die=1.0 --c-pkg=5.0 --c-hs=15.0
```

## SimObject Index Mapping (from config.ini)

| thermal_components index | Type | Role |
|--------------------------|------|------|
| 00 | ThermalNode | T_die — big cluster junction (connected to bigCluster.thermal_domain) |
| 01 | ThermalResistor | R_die_pkg |
| 02 | ThermalNode | T_pkg — package node |
| 03 | ThermalCapacitor | C_die |
| 04 | ThermalNode | T_hs — heatsink node |
| 05 | ThermalResistor | R_pkg_hs |
| 06 | ThermalNode | T_amb — ambient reference (ThermalNode fixed at ambient) |
| 07 | ThermalCapacitor | C_pkg |
| 08 | ThermalResistor | R_hs_amb |
| 09 | ThermalCapacitor | C_hs |
| 10 | ThermalReference | Ambient reference entity |

## Stat Paths in stats.txt

```
system.thermal_components0.temperature   # T_die
system.thermal_components2.temperature   # T_pkg
system.thermal_components4.temperature   # T_hs
system.thermal_components6.temperature   # T_amb (reference, fixed)
```

Note: stats.txt uses unpadded indices (0, 2, 4, 6), while config.ini uses
zero-padded indices (00, 02, 04, 06). The parser must match the unpadded form.

## Observed Values (2 stat dumps, ~0.2 s simulated)

| Node | Dump 1 (°C) | Dump 2 (°C) | Physical interpretation |
|------|------------|------------|------------------------|
| T_die (comp0) | 28.614 | 28.896 | Rising — CPU power ~2.2 W heating die |
| T_pkg (comp2) | 25.006 | 25.020 | Slow rise — heat diffusing through R_die_pkg=5 K/W |
| T_hs  (comp4) | 25.000 | 25.000 | Flat — tau_hs = R_hs_amb × C_hs = 8×15 = 120 s |
| T_amb (comp6) | 25.000 | 25.000 | Fixed reference |

## RC Parameters Used

| Parameter | Value | Unit |
|-----------|-------|------|
| R_die_pkg | 5.0 | K/W |
| R_pkg_hs  | 2.0 | K/W |
| R_hs_amb  | 8.0 | K/W |
| C_die     | 1.0 | J/K |
| C_pkg     | 5.0 | J/K |
| C_hs      | 15.0 | J/K |
| tau_die   | ~5 s | (R_die_pkg × C_die) |
| tau_pkg   | ~50 s | approx |
| tau_hs    | ~120 s | (R_hs_amb × C_hs) |
| T_amb     | 25.0 | °C |
