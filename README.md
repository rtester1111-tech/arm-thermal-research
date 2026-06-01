# ARM Thermal Research

This repository collects reproducible artifacts for a gem5 thermal-model audit,
and trace-driven ARM thermal scheduling experiments.

Two IEEE Embedded Systems Letters manuscripts based on the Paper 1 and Paper 2
tracks were submitted on 2026-06-01. The manuscripts are under review; this
repository is an artifact and engineering workspace, not a claim of acceptance.

Language-specific readmes:

- [English README](README.en.md)
- [Chinese README](README.zh.md)

If you are looking for the core research artifacts, start here:

- [Documentation index](docs/README.md)
- [Paper artifact workspace index](paper_artifacts/INDEX.md)
- [Operations scripts](scripts/ops/README.md)
- [Bug reports](bug-reports/README.md)
- [Validation](validation/README.md)
- [Results](results/README.md)
- [Public release checklist](PUBLIC_RELEASE_CHECKLIST.md)
- [Intellectual property notice](IP_NOTICE.en.md) / [Chinese](IP_NOTICE.zh.md)
- [Citation metadata](CITATION.cff)

The project covers two related tracks:

1. Paper 1: gem5 native Cauer RC thermal-model verification, including the
   absolute-zero initialization artifact and cross-solver validation.
2. Paper 2: gem5 thermal-node instrumentation and trace-driven
   package-aware scheduling experiments for ARM big.LITTLE-style systems.
