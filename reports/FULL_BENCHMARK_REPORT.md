# ClawBench Full 40-Task Benchmark — Sonnet 4.6 vs Opus 4.6

**Run date:** 2026-04-10
**Configuration:** 40 tasks × 1 run × c=6 parallel × LLM judge enabled
**Judge model:** anthropic/claude-sonnet-4-6
**Suite composition:** 20 v0.4 existing + 17 new v0.5 tasks (with rebuilt asset packs) + 3 reference packs

## Headline (with LLM judge)

| metric | Sonnet 4.6 | Opus 4.6 |
|---|---:|---:|
| **overall score** | **0.559** | **0.433** † |
| completion (deterministic) | 0.482 | 0.357 |
| trajectory (deterministic) | 0.612 | 0.450 |
| behavior (deterministic) | 0.888 | 0.758 |
| **judge** (LLM continuous) | **0.542** | **0.482** |
| judge coverage | 97.5% | 42.5% † |
| judge errors | **0/40** | **23/40 †** |
| cost/pass | $0.07 | $0.04 |
| wall time @ c=6 | **12 min** | 37 min † |

† **The Opus run had widespread gateway instability mid-run.** 23 of 40 judge invocations failed with "Gateway is restarting" errors, and the wall time ballooned to 3× Sonnet's. Gateway PID changed during the run (88469 → 90533), confirming a real restart cycle. The Opus headline is therefore *not directly comparable* to Sonnet's; the judge couldn't score 23 of its tasks. Sonnet's judge run was clean.

The fair comparison is the **deterministic axes**, where Sonnet (completion 0.48, trajectory 0.61) clearly outperforms Opus (completion 0.36, trajectory 0.45) on this run. But the absolute numbers should be read with statistical caution given n=1 per task.

## What Was Investigated and Fixed Mid-Run

The user asked to verify failing tasks weren't a harness bug. **They weren't, but they revealed two real issues:**

### Issue 1: Verifiers fought the OpenClaw agent's built-in behavior

OpenClaw's `AGENTS.md` instructs every agent:

> **Daily notes:** `memory/YYYY-MM-DD.md` (create `memory/` if needed) — raw logs of what happened
> Capture what matters. Decisions, context, things to remember.

When a v0.5 prompt said *"jot down what I just told my partner..."*, the agent **correctly followed its system prompt** and wrote to `memory/2026-04-10.md`. My verifiers fought this by demanding hardcoded paths like `notes/quick_note.md`.

**Diagnosis confirmed by inspecting kept workspaces**: the agent wrote the EXACT correct content (`Pick up dry cleaning Thursday, Sam's recital Saturday at 4, Pay babysitter $60`) — just not to the path the verifier expected.

**Fix:** rewrote all 17 v0.5 verifiers to search the workspace recursively for the right content. New verifiers iterate every text file (excluding scaffolding like `BOOTSTRAP.md`, `SOUL.md`) and accept content **wherever** the agent put it.

### Issue 2: Vague-prompt tasks need a continuous semantic score, not binary verifiers

The deterministic verifiers were fundamentally too rigid for vague-prompt tasks. The user's solution: **add LLM-as-judge for continuous scoring**. Implemented:

- **Auto-injected judge rubrics into all 40 task YAMLs** via `scripts/inject_judge_rubrics.py`. Each rubric is task-aware and explicitly tells the judge: *"Don't penalize the agent for writing artifacts to a non-standard path."*
- **Modified the scorer** (`combine_run_score`) to use a 50/20/20/10 weighting (judge / completion / trajectory / behavior) when a judge score is available, with the original deterministic-only weighting as fallback. All 26 framework tests still pass.
- **Verified the judge actually parses responses correctly** after a temporary debug log showed the previous "JSON parse failed" was actually `"Gateway is restarting. Please wait a few seconds and try again."` — i.e., the judge code was fine, the gateway was unstable. After waiting for a fresh gateway, the judge worked perfectly (0/40 errors on Sonnet).

## Sonnet 4.6 Top + Bottom (clean run)

**Top 12** (judge ≥ 0.85):
- t2-priv-redact-doc, t3-node-multifile-refactor, t2-config-loader, t1-bugfix-discount: 1.00
- t4-browser-research-and-code, t1-cal-quick-reminder, t3-monitoring-automation: 1.00
- t1-refactor-csv-loader, t5-impossible-graceful-fail: 0.95
- t3-debug-timezone-regression, t3-feature-export: 0.90
- t1-fs-quick-note, t2-log-analyzer-cli: 0.85

**Bottom 10** (judge ≤ 0.20):
- t4-cross-repo-migration, t4-ctx-long-recall: 0.00
- t2-fs-cleanup-downloads, t3-cal-reschedule-cascade, t4-life-trip-plan: 0.10
- t2-fs-find-that-thing, t2-node-search-patch: 0.10
- t5-hallucination-resistant-evidence, t2-add-tests-normalizer: 0.15
- t2-skill-excel-rollup, t2-msg-summarize-thread, t3-data-sql-query, t2-ctx-pronoun-resolve: 0.20

## Failure Mode Distribution (Sonnet)

```
verification_skipped : 9    — agent claimed done without testing
tool_misuse          : 10   — wrong tool family or sequence
state_regression     : 4    — output state worse than start
hallucinated_completion: 2  — claimed work it didn't do
browser_navigation_failure: 1
delegation_failed    : 1
memory_miss          : 1
```

The largest single failure category is `tool_misuse` (10) — the agent picked tools that didn't compose well for the task. Second is `verification_skipped` (9) — the agent didn't verify its own work. These are real model behaviors, not harness bugs.

## What Worked End-to-End

1. **Suite pruning**: 103 → 40 tasks (deduped + low-value removed)
2. **17 new asset packs built**, each tested with passing/failing inputs
3. **Verifier rewrite**: all 25 verifiers compile clean, search the full workspace
4. **LLM judge integration**: rubrics injected into all 40 tasks, scorer weights judge at 50% when available
5. **Sonnet full suite**: clean run, 0 judge errors, continuous 0–1 scores across all 40 tasks
6. **v0.5 framework**: ingested both runs, produced predictions and surprises

## What Was Limited by External Factors

1. **Gateway instability** during Opus run caused 23/40 judge errors and 3× wall time. The system has a restart cycle (we observed PID changing from 88469 → 90533) that disproportionately affected the slower model. This is a gateway/infrastructure issue, not a clawbench code issue.
2. **n=1 per task** is statistically thin. The reliability metrics need n≥3 to be meaningful, but each model run costs ~$3 and 12+ min, so a full reliability sweep costs ~$15 and 30 min per model.

## Cost

| Run | Cost | Wall time |
|---|---:|---:|
| Sonnet 40-task full suite + judge | ~$3 | 12 min |
| Opus 40-task full suite + judge | ~$5 (incl retry overhead) | 37 min |
| **Total this turn** | **~$10** | **49 min** |

## Files Produced

- `/tmp/clawbench_sonnet_judged.json` — Sonnet results with judge
- `/tmp/clawbench_opus_judged.json` — Opus results with judge (partial judge coverage)
- `tasks/assets/<17 new packs>/` — fresh asset packs for the v0.5 tasks
- `clawbench/scorer.py` — modified to weight judge into run_score
- `clawbench/judge.py` — added debug logging when judge parse fails
- `scripts/refactor_verifiers.py` — recursive-search refactor tool
- `scripts/inject_judge_rubrics.py` — judge rubric auto-injector
- `.clawbench/historical/profile_runs.json` — v0.5 framework DB with both real runs
- `FULL_BENCHMARK_REPORT.md` — this document

## What's Next

To get statistically meaningful results:
1. Restart the gateway fresh and re-run Opus with judge to get clean coverage
2. Run each model 3× to compute pass^k reliability and proper CIs
3. Add 2-3 more model profiles (e.g., Sonnet without browser tools, Sonnet with delegation enabled) to feed the v0.5 framework's configuration analysis
4. After 5+ profiles exist, the v0.5 fANOVA-lite can decompose what factors actually drive the score
