# Public Release Checklist

This checklist defines what can be safely exposed in the public GitHub artifact
after the Paper 1 and Paper 2 ESL submissions.

Submission status: Paper 1 and Paper 2 were submitted to IEEE Embedded Systems
Letters on 2026-06-01. They are under review, not accepted publications.

## Public Now

- `paper_artifacts/paper1_latex_draft/`: Paper 1 source snapshot used for the
  submitted ESL manuscript.
- `paper_artifacts/paper2_latex_draft/`: Paper 2 source snapshot.
- `bug-reports/`: gem5 thermal-node initialization report and reproduction
  material.
- `validation/`: independent analytical, Python, and SPICE validation material.
- `results/validation/`, `results/phase5*`, `results/phase6/`, and
  `results/phase7/`: curated plots and JSON summaries used for Paper 1/2
  evidence, after checking file size.
- `scripts/` and `workloads/`: reproducibility helpers and workloads, after
  confirming paths are generic and no local credentials are embedded.
- `docs/`: curated methodology, limitations, related work, and calibration notes.

## Keep Private For Now

- Private future-work planning, raw logs, generated run directories, and
  strategy that have not been curated into a public artifact release.
- Local gem5 output directories:
  - `m5out*/`
  - `logs/`
- Portal-generated reviewer PDFs, submission confirmations, screenshots, and
  any downloaded files from IEEE/ScholarOne/Author Portal.
- Submission portal/export packages:
  - `paper_artifacts/submission_package_*/`
  - `paper_artifacts/submission_package_*.zip`
  - `paper_artifacts/submission_package_*.7z`
- Remote handoff and AI planning directories:
  - `ai_workspace/`
  - `ai_workspace/docs/`
  - `ai_workspace/remote_server_handoff_*/`
  - `ai_workspace/archive/notes/`
  - `ai_workspace/archive/project_history/`
- Personal workflow notes that include private AI prompts, review drafts,
  account setup steps, or unpublished future-work strategy.
- Cover letters, reviewer-risk notes, and submission checklists, unless they
  are specifically rewritten as public-facing artifact documentation.
- Any archive that bundles more than the curated source/evidence files, such as
  ad hoc `.zip` or `.7z` packages, unless its manifest has been reviewed.

## Required Checks Before Making GitHub Public

1. Run a secret scan over tracked files:

   ```bash
   rg -n --hidden --glob '!/.git/**' --glob '!PUBLIC_RELEASE_CHECKLIST.md' \
     '(ghp_|github_pat_|BEGIN (RSA|OPENSSH|DSA|EC|PRIVATE) KEY|Authorization:|Bearer |token=|access_token|password|passwd|secret|api[_-]?key)'
   ```

2. Check for local-only paths and personal infrastructure:

   ```bash
   rg -n --hidden --glob '!/.git/**' --glob '!PUBLIC_RELEASE_CHECKLIST.md' \
     '(C:/Users|C:\\Users|X:|/mnt/|10\.[0-9]+\.[0-9]+\.[0-9]+|sshfs|forkasder@)'
   ```

3. Confirm the git remote does not contain an embedded token:

   ```bash
   git remote -v
   ```

   If a token appears in the URL, rotate or revoke it before public release and
   replace the remote with a normal HTTPS or SSH URL.

4. Review untracked files:

   ```bash
   git status --short
   ```

   Do not add private future-work planning, m5out directories, portal
   downloads, or private submission screenshots.

5. Create a submission artifact tag after the public tree is clean:

   ```bash
   git tag paper1-paper2-submission-2026-06-01
   ```

6. Optional but recommended: archive the clean tag on Zenodo to obtain a DOI for
   future revision/camera-ready artifact availability statements.

## Disclosure Language

Suggested repository notice:

> This repository contains artifacts for two IEEE Embedded Systems Letters
> manuscripts submitted on 2026-06-01. The manuscripts are currently under
> review. Results should be interpreted as modeled or simulated unless a file
> explicitly states that it is measured hardware data.
