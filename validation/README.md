# Validation

This folder contains the numerical and analytical checks that support the bug
claim and the thermal model comparison.

Chinese counterpart: [README.zh.md](README.zh.md)

## Contents

- [Analytical solution](analytical/analytical_solution.py)
- [Independent Backward Euler solver](implicit_solver/implicit_solver.py)
- [Timestep sweep](timestep_sweep/timestep_sweep.py)
- [Cross-check comparison](crosscheck/three_way_comparison.py)
- [SPICE cross-check notes](crosscheck/spice_crosscheck.md)
- [Error metrics](error_metrics/compute_errors.py)
- [Intellectual property notice](../IP_NOTICE.en.md)

## Use this folder when you need

- The closed-form thermal baseline
- The numerical solver that reproduces gem5's bugged trajectory
- Error and convergence evidence for the simulation claims
