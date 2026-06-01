# ARM Thermal Research

This repository documents connected research efforts on ARM and gem5 thermal
behavior:

1. A gem5 native Cauer RC thermal-model audit that identified an absolute-zero
   initialization artifact in `ThermalModel::startup()`.
2. A cross-solver validation workflow spanning closed-form analysis, an
   independent Backward Euler solver, SPICE equivalent circuits, unpatched
   gem5, and patched gem5.
3. A trace-driven thermal scheduling study that instruments gem5 thermal nodes
   and evaluates package-aware migration/DVFS behavior for heterogeneous
   multicore systems.

Two IEEE Embedded Systems Letters manuscripts based on these tracks were
submitted on 2026-06-01. They are under review; this repository is a public
artifact workspace and does not imply acceptance.

## Highlights

- The bug report shows that intermediate thermal nodes in gem5 can remain at
  0 K if they are not initialized by a domain or reference object.
- The validation artifacts use a five-way verification loop: analytical
  closed-form solutions, an independent Backward Euler solver, SPICE,
  unpatched gem5, and patched gem5.
- The scheduling study separates die, package, and heatsink dynamics with a
  three-node Cauer RC model, then evaluates trace-driven package-aware
  migration before DVFS throttling.
- The repository preserves figures, scripts, patches, and claim-evidence
  material so reviewers and readers can inspect the artifact trail.

![Three-way verification](results/validation/three_way_comparison.png)

## Repository Map

- `paper_artifacts/INDEX.md` - public index for paper-adjacent artifact files
- `paper_artifacts/paper1_latex_draft/` - Paper 1 submitted-source snapshot
- `paper_artifacts/paper2_latex_draft/` - Paper 2 submitted-source snapshot
- `validation/` - analytical and numerical verification
- `bug-reports/` - bug report, repro script, and expected vs observed tables
- `workloads/` - benchmark sources
- `results/` - figures, JSON summaries, and run outputs
- `scripts/` - run and maintenance helpers
- `src/` - SIMD kernel sources

## Quick Start

### Reproduce the gem5 bug

```bash
bash bug-reports/gem5-thermal-node-init/reproduce.sh
```

### Run the independent solver

```bash
pip install -r requirements.txt
python3 validation/implicit_solver/implicit_solver.py
```

### Run the analytical solution

```bash
python3 validation/analytical/analytical_solution.py
```

### Run the DVFS simulation

```bash
python3 scripts/thermal_governor.py --workload idct
python3 scripts/thermal_governor.py --workload brightness
```

### Build SIMD kernels

```bash
sudo apt install gcc-aarch64-linux-gnu qemu-user
cd src && make compare
```

## Key Results

- Paper 1 validation: analytical, Python, and SPICE fixed baselines agree
  within 0.001 K under the canonical 3.0 W step input.
- Paper 1 full-system patched gem5 run: the reconstructed Python solver
  matches gem5 with 0.0082 K RMSE and 0.034 K peak error over 55.116 s.
- Paper 2 trace-driven study: the three-node model defers the first thermal
  intervention by 85 simulated seconds compared with a two-node baseline.
- Paper 2 package-aware policy: DVFS oscillation events drop from 13 to 1 in
  the modeled 600 s sustained-load experiment, with modeled peak package
  temperature reduced by 4.5 C.

These results are modeled or simulated unless explicitly marked as measured
hardware data.

## More Reading

- [Documentation index](docs/README.md)
- [Paper artifact workspace index](paper_artifacts/INDEX.md)
- [Operations scripts](scripts/ops/README.md)
- [Bug reports](bug-reports/README.md)
- [Validation](validation/README.md)
- [Results](results/README.md)
- [Public release checklist](PUBLIC_RELEASE_CHECKLIST.md)
- [Citation metadata](CITATION.cff)
