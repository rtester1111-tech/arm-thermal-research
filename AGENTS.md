# AGENTS.md

## Project Context

This repository is for an IEEE Embedded Systems Letters submission project.

The target artifact is a 4-page technical letter, not a full-length journal or conference paper. All writing, editing, experiments, figures, and evidence packaging should respect the short-letter scope.

## Working Rules

1. Treat this as an IEEE Embedded Systems Letters submission project.
2. Keep the paper scoped as a 4-page technical letter. Do not expand it into a long paper.
3. Do not broaden claims. Do not describe a bug fix as an over-sized contribution.
4. Preserve technical correctness in every edit.
5. Before modifying paper text, perform a claim-evidence check:
   - identify the claim being changed,
   - locate the supporting data, figure, table, citation, or source file,
   - note any mismatch before editing.
6. Do not delete experiment conditions, numeric values, figure/table provenance, or citations unless the deletion is explicitly justified and does not weaken reproducibility.
7. English polishing should follow IEEE technical style:
   - concise,
   - precise,
   - evidence-oriented,
   - neutral in tone.
   Avoid AI-generated marketing tone, inflated novelty language, and promotional phrasing.
8. If evidence is insufficient, mark the point as a weakness, limitation, or item requiring remote/server verification. Do not invent results.
9. After every modification, report:
   - which files changed,
   - what changed,
   - why the change was made,
   - what verification was performed or still remains.
10. Any change that could affect experimental conclusions must be proposed first. Do not directly edit conclusion-changing claims, numbers, experiment setup, or validation interpretation without first presenting the recommended change.

## Default Review Checklist

Before finalizing paper edits, verify:

- Active paper text has no stale numeric claims.
- Tables match the source CSV/JSON/log evidence.
- Figures match their stated source data.
- Citations still support the sentence they are attached to.
- Page-count pressure is handled by compression, not by removing critical evidence.
- Any unresolved evidence gap is documented instead of hidden.
