# paper_artifacts Public Artifact Index

This folder contains the paper-adjacent source, evidence, and scripts used by
the submitted IEEE Embedded Systems Letters artifacts.

Submission status: Paper 1 and Paper 2 were submitted on 2026-06-01 and are
under review. This directory is an artifact workspace, not a publication claim.

## Manuscript Snapshots

| Path | Contents |
|---|---|
| `paper1_latex_draft/` | Paper 1 LaTeX source snapshot and figures |
| `paper2_latex_draft/` | Paper 2 LaTeX source snapshot and figures |

Cover letters, portal-generated reviewer PDFs, and submission packages are kept
outside the public Git index.

## Paper 1 Evidence

| Path | Contents |
|---|---|
| `raw_evidence/` | gem5 bug/fixed outputs, SPICE cross-check files, validation CSV/JSON |
| `canonical_validation_table.csv` | compact validation table used by the paper workflow |
| `gem5_unpatched_extracted.csv` | extracted unpatched gem5 trace used for comparison |

## Paper 2 Evidence

| Path | Contents |
|---|---|
| `paper2_experiment_evidence_2026-05-29/run_esl_trace_experiments.py` | trace-driven experiment script |
| `paper2_experiment_evidence_2026-05-29/phase3_esl_experiments/` | curated CSV/JSON/PNG outputs for the Paper 2 evaluation |
| `paper2_experiment_evidence_2026-05-29/gem5_run_outputs/` | curated gem5-derived plots and summaries |
| `paper2_experiment_evidence_2026-05-29/workstream_A_3node_patch_validation/` | 3-node instrumentation smoke-run evidence; generated local `config.ini` is intentionally excluded |

## Shared Scripts

| Path | Contents |
|---|---|
| `scripts/` | copies of paper-adjacent run and parsing helpers |
| `archive/simulation_older_versions/` | older simulation helpers retained for provenance |

## Not Publicly Indexed

The following are intentionally ignored or removed from the public Git index:

- submission portal packages and compressed exports;
- cover letters and author-portal checklists;
- remote-AI handoff folders and internal task plans;
- reviewer-risk or adversarial review notes;
- future unpublished planning directories and uncurated experiment logs.

Use the top-level `README.md` and `PUBLIC_RELEASE_CHECKLIST.md` as the public
entry points.
