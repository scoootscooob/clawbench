# Contributing Tasks to ClawBench

This guide explains how to add a new task to the ClawBench suite. Every
task is a triple of:

1. A YAML definition under `tasks/tier{1..5}/`
2. An asset pack under `tasks/assets/<asset_pack_id>/`
3. One or more verifier scripts inside the asset pack

The 100-task plan in `CLAWBENCH_100_TASK_PLAN.md` lists every task slot.
The reference implementations to pattern-match against are:

- `tasks/tier1/t1-fs-quick-note.yaml` + `tasks/assets/t1_fs_quick_note/`
- `tasks/tier2/t2-fs-cleanup-downloads.yaml` + `tasks/assets/t2_fs_cleanup_downloads/`
- `tasks/tier2/t2-sys-memory-roundtrip.yaml` + `tasks/assets/t2_sys_memory_roundtrip/`

## Authoring rules (non-negotiable)

1. **Vague user prompt.** Real-human voice. No numbered steps. No
   parameter lists. No "do all of the following".
2. **Hidden requirements.** All structure (file names, schemas, time
   windows, priority rules) lives in workspace files, not the prompt.
3. **Multi-stage.** Discover → plan → act → verify. Tier 4 adds recovery.
4. **Frontier separators.** At least one design element that bunches
   weak agents and separates strong ones (dedupe, timezone math, corrupt
   input, mutually exclusive constraints, ambiguity, no-fabrication).
5. **Sandboxed.** No real external sends. Email/cal/cron in workspace.
6. **Verifiable.** Every assertion runs as a Python verifier with a
   non-zero exit code on failure. No LLM judges in the primary path.
7. **No fabrication tolerance.** Where the agent could hallucinate, the
   verifier explicitly checks grounding.

## Verifier conventions

- One verifier script per `execution_check` in the YAML
- Script lives next to its asset pack: `tasks/assets/<pack>/<script>.py`
- Script reads files from the current working directory (the workspace)
- Script prints `PASS:` on success, `FAIL:` on failure
- Script exits 0 on pass, 1 on fail
- No external dependencies beyond stdlib + `pyyaml`

## How to add a task in ~30 minutes

1. **Pick a task slot** from `CLAWBENCH_100_TASK_PLAN.md`
2. **Write the YAML** following the pattern of an existing same-tier task
3. **Create the asset pack directory** at `tasks/assets/<pack_id>/`
4. **Author the workspace fixtures** (config files, sample data, broken
   inputs, etc.)
5. **Author one verifier per execution_check** in the YAML
6. **Test with a "good agent" mock** — manually create the expected
   outputs in `/tmp/<task>_good/` and run every verifier (all should pass)
7. **Test with a "bad agent" mock** — create wrong/missing outputs in
   `/tmp/<task>_bad/` and run every verifier (all should fail)
8. **Commit**

## v0.5 framework integration

When you author a profile (`profiles/<name>.yaml`), the framework
automatically:

- Computes a Profile Fingerprint
- Looks up neighbors in the historical database
- Predicts your score before you run anything
- After running, detects surprises against the prediction
- Updates the historical database

Run the diagnostic CLI:

    python -m clawbench.diagnose_cli profiles/your_profile.yaml

To pre-seed a fresh database with the synthetic 40-profile ecosystem
(useful for demos and tests):

    python scripts/seed_historical_db.py

To verify the framework code itself:

    python tests/test_v05_framework.py
    python tests/test_e2e_significance.py
