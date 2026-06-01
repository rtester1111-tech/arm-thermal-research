# Contributing to arm-thermal-research

Thank you for your interest in contributing to this academic research project.

## Scope

This repository documents a closed research study on ARM heterogeneous thermal management and DVFS simulation using gem5. Contributions that improve reproducibility, fix inaccuracies, or extend the simulation methodology are welcome.

## How to Contribute

### Reporting Issues

- Use GitHub Issues to report errors in the documentation, simulation scripts, or research data.
- For suspected errors in the mathematical models or simulation results, please include the specific formula, script, and the observed vs. expected behavior.

### Submitting Changes

1. Fork the repository and create a branch from `main`.
2. Make your changes with clear, descriptive commit messages.
3. Ensure any modified Python scripts pass basic linting (`python3 -m py_compile <script>`).
4. Open a pull request with a summary of the change and its motivation.

### Areas Where Contributions Are Especially Welcome

- **Phase 6 implementation**: big.LITTLE / DynamIQ EAS heterogeneous task migration (see `PHASE5_6_IMPLEMENTATION_PLAN.md`).
- **gem5 Absolute-Zero Bug patch**: A source-level C++ fix for `src/sim/power/thermal_model.cc` upstream.
- **McPAT integration**: Scripts to automate gem5 stats → McPAT XML → power extraction pipeline.
- **Additional workloads**: New SIMD benchmark kernels (e.g., H.265 entropy coding, FFT).

## Code Style

- C sources follow K&R style with 4-space indentation.
- Python scripts target Python 3.8+ and use `numpy`/`matplotlib` from the standard scientific stack.
- Shell scripts use `#!/usr/bin/env bash` and `set -euo pipefail`.

## Citation

If you use this work in academic research, please cite it using the metadata in `CITATION.cff`.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
