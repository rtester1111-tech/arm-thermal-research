# Phase 5 v2 Patched Full-System Run

This directory contains the curated public outputs for the patched full-system
gem5 thermal validation run.

## Public Files

- `bugfix_validation_final.json`: compact run summary for the final patched
  run.
- `bugfix_validation_summary.json`: earlier partial summary retained for
  provenance.
- `fs_temp_vs_time_final.png`: full-system temperature trace plot.
- `fs_power_vs_time_final.png`: dynamic-power trace plot.
- `fs_frequency_vs_time_final.png`: frequency trace plot.
- `comparison_bugfix_final.png` and `comparison_bugfix_validation.png`:
  before/after validation plots.

## Large Raw Trace

The full raw trace `fs_simulation_results_final.json` is intentionally excluded
from Git because it is approximately 75.7 MB. Keep the local file for audit and
archive it as a release asset or Zenodo artifact if reviewers request the full
trace.

The compact public summary reports a completed 55.1162 s run with 275582
records, a 25.0 C minimum temperature, a 28.7075 C final temperature, and
`fix_validated: true`.
