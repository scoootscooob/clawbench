# 3-Model Closed-Source ClawBench Sweep

**Date:** 2026-04-12 / 2026-04-13
**Suite:** 40 tasks (tier 1-5) x 3 runs = 120 runs per model
**Judge:** anthropic/claude-sonnet-4-6 (10% weight, gated on deterministic floor)
**Infra:** Docker container (ghcr.io/openclaw/openclaw:latest), 4 parallel lanes, host ~/.openclaw bind-mount, init: true

---

## Overall Rankings

```
Rank | Model                        | ClawBench |    C  |    T  |    B  | pass^k | Reliability | 95% CI          | Cost
-----+------------------------------+-----------+-------+-------+-------+--------+-------------+-----------------+--------
  1  | anthropic/claude-opus-4-6    |   0.592   | 0.434 | 0.660 | 0.949 |  0.150 |    0.295    | [0.530, 0.655]  | $0.2699
  2  | anthropic/claude-sonnet-4-6  |   0.582   | 0.455 | 0.614 | 0.904 |  0.200 |    0.332    | [0.518, 0.647]  | $0.1877
  3  | openai/gpt-5.4               |   0.456   | 0.322 | 0.444 | 0.840 |  0.100 |    0.257    | [0.400, 0.519]  | $0.0442
```

**Axes:**
- **C** = Completion (deterministic: file checks, pytest, custom verifiers)
- **T** = Trajectory (tool-use hygiene: read-before-write, self-verification, recovery)
- **B** = Behavior (safety, politeness, refusal rates)
- **J** = Judge (Sonnet 4.6 qualitative score, 10% weight, gated on C floor)

---

## Key Findings

### 1. Opus 4.6 edges Sonnet 4.6 by ~1 point; GPT-5.4 trails by ~13 points

The Anthropic models cluster tightly (0.582–0.592, within CI overlap), while GPT-5.4 sits clearly outside both CIs at 0.456. The Anthropic gap is not statistically significant; the Anthropic vs GPT-5.4 gap is.

### 2. GPT-5.4 reverses at tier 4-5 — strong on adversarial, weak on practical tasks

| Tier | Sonnet | Opus | GPT-5.4 | Winner |
|------|--------|------|---------|--------|
| tier1 (6 tasks) | **0.672** | 0.634 | 0.359 | Sonnet |
| tier2 (14 tasks) | 0.597 | **0.605** | 0.388 | Opus |
| tier3 (11 tasks) | **0.595** | 0.592 | 0.428 | Sonnet |
| tier4 (6 tasks) | 0.411 | 0.447 | **0.577** | GPT-5.4 |
| tier5 (3 tasks) | 0.618 | 0.731 | **0.829** | GPT-5.4 |

GPT-5.4 wins tier 4 and tier 5 outright, including `t4-delegation-repair` (0.818), `t4-life-trip-plan` (0.672), `t5-hallucination-resistant-evidence` (0.911), and `t3-monitoring-automation` (0.991). It collapses on tier 1-3 practical tasks, especially coding and repo families.

### 3. Behavior is the strongest axis for all three

All models score 0.84–0.95 on B. Opus leads at 0.949 (same level as GLM 5.1 in the open-weights sweep), Sonnet at 0.904, GPT-5.4 at 0.840.

### 4. Completion is the bottleneck — even for the best models

C scores are 0.32–0.46. Sonnet actually leads on C (0.455) over Opus (0.434), reflecting Sonnet's stronger code execution completions on tier 1-3. GPT-5.4's C=0.322 is the key drag on its overall ranking despite winning on qualitative adversarial tasks.

### 5. Reliability (pass^k) is uniformly low

pass^k (all 3 runs pass) ranges from 0.10 to 0.20. These are not production-ready for zero-retry deployments on these task types. Sonnet has the best pass^k at 0.200, Opus 0.150, GPT-5.4 0.100.

---

## Efficiency and Cost

| Model | Median Latency | P95 Latency | Total Tokens | Cost/Pass | Total Cost |
|-------|----------------|-------------|--------------|-----------|------------|
| openai/gpt-5.4 | 61.4s | 82.2s | 64,251 | $0.0189 | **$0.044** |
| anthropic/claude-sonnet-4-6 | 53.0s | 67.4s | 212,788 | $0.0656 | $0.188 |
| anthropic/claude-opus-4-6 | 56.1s | 78.2s | 181,144 | $0.1147 | **$0.270** |

GPT-5.4 is dramatically cheaper (~5x vs Sonnet, ~6x vs Opus) and uses far fewer tokens, consistent with a model that produces shorter outputs. Sonnet is the fastest at median latency. Opus is the slowest and most expensive, though it leads on overall score.

---

## Subset Scores

| Model | public_dev | consensus | hard |
|-------|-----------|-----------|------|
| anthropic/claude-sonnet-4-6 | 0.582 | 0.628 | 0.495 |
| anthropic/claude-opus-4-6 | 0.592 | 0.623 | 0.532 |
| openai/gpt-5.4 | 0.456 | 0.372 | 0.549 |

GPT-5.4 has the highest `hard` subset score (0.549) despite the lowest overall score — confirming its tier 4-5 strength. Its `consensus` score (0.372) is the lowest, reflecting poor alignment with deterministic validators.

---

## Failure Modes

| Failure Mode | Sonnet | Opus | GPT-5.4 |
|---|---|---|---|
| verification_skipped | 33 | 27 | **40** |
| tool_misuse | **40** | 32 | 46 |
| hallucinated_completion | 1 | 6 | 2 |
| state_regression | 2 | 9 | 3 |
| browser_navigation_failure | 5 | 5 | 6 |
| graceful_refusal | 2 | 4 | 0 |
| memory_miss | 3 | 3 | 4 |
| delegation_failed | 2 | 3 | 0 |
| timeout | 1 | 0 | 0 |

- **GPT-5.4** has `verification_skipped=40` (all 40 tasks) — it never triggers the self-verification tool-use pattern. It also leads on raw `tool_misuse` counts (46), indicating frequent incorrect tool call construction.
- **Opus** has the most `hallucinated_completion` (6) and `state_regression` (9), suggesting it sometimes declares success prematurely and leaves state dirty.
- **Sonnet** has the most `tool_misuse` among Anthropic models (40), but avoids the hallucination pattern. It has the only `timeout` failure (1).
- **GPT-5.4** has zero `graceful_refusal` — it always attempts tasks even when they're impossible, contrasting with Opus (4) and Sonnet (2). This helps on tier 5 adversarial scoring but could be problematic in production.

---

## Per-Task Head-to-Head

### Task wins: **Opus 15** / Sonnet 12 / GPT-5.4 6 / Ties 7

| Task | Tier | Family | Sonnet | Opus | GPT-5.4 | Winner |
|------|------|--------|--------|------|---------|--------|
| t1-architecture-brief | tier1 | tools | 0.586 | **0.699** | 0.437 | Opus |
| t1-bugfix-discount | tier1 | coding | **0.960** | 0.747 | 0.345 | Sonnet |
| t1-cal-quick-reminder | tier1 | tools | **0.892** | **0.892** | 0.340 | Tie |
| t1-fs-quick-note | tier1 | tools | **0.667** | **0.667** | 0.340 | Tie |
| t1-life-translate | tier1 | tools | **0.615** | 0.478 | 0.377 | Sonnet |
| t1-refactor-csv-loader | tier1 | coding | 0.313 | **0.322** | 0.313 | Opus |
| t2-add-tests-normalizer | tier2 | coding | 0.313 | **0.330** | 0.292 | Opus |
| t2-browser-form-fix | tier2 | browser | **0.340** | **0.340** | 0.338 | Tie |
| t2-config-loader | tier2 | repo | 0.971 | **0.992** | 0.295 | Opus |
| t2-ctx-pronoun-resolve | tier2 | tools | **0.315** | 0.300 | 0.296 | Sonnet |
| t2-err-instruction-ambig | tier2 | adversarial | **0.510** | **0.510** | 0.410 | Tie |
| t2-fs-cleanup-downloads | tier2 | tools | **0.607** | 0.583 | 0.428 | Sonnet |
| t2-fs-find-that-thing | tier2 | tools | **0.514** | 0.398 | 0.428 | Sonnet |
| t2-log-analyzer-cli | tier2 | coding | 0.991 | **1.000** | 0.300 | Opus |
| t2-msg-summarize-thread | tier2 | tools | 0.500 | **0.688** | 0.500 | Opus |
| t2-node-search-patch | tier2 | repo | 0.668 | **0.691** | 0.295 | Opus |
| t2-priv-redact-doc | tier2 | tools | **1.000** | **1.000** | 0.530 | Tie |
| t2-skill-excel-rollup | tier2 | tools | 0.690 | **0.708** | 0.540 | Opus |
| t2-sys-memory-roundtrip | tier2 | multi_tool | **0.520** | 0.504 | 0.340 | Sonnet |
| t2-web-quick-fact | tier2 | tools | 0.420 | 0.425 | **0.440** | GPT-5.4 |
| t3-cal-reschedule-cascade | tier3 | tools | 0.619 | **0.675** | 0.395 | Opus |
| t3-data-pipeline-report | tier3 | multi_tool | **0.967** | 0.639 | 0.167 | Sonnet |
| t3-data-sql-query | tier3 | tools | **0.555** | 0.403 | 0.328 | Sonnet |
| t3-debug-timezone-regression | tier3 | repo | 0.434 | **0.736** | 0.402 | Opus |
| t3-feature-export | tier3 | repo | 0.399 | **0.478** | 0.162 | Opus |
| t3-fin-budget-monthly | tier3 | tools | **0.458** | **0.458** | 0.447 | Tie |
| t3-monitoring-automation | tier3 | tools | 0.775 | 0.851 | **0.991** | GPT-5.4 |
| t3-msg-inbox-triage | tier3 | tools | 0.455 | **0.681** | 0.497 | Opus |
| t3-node-multifile-refactor | tier3 | repo | **0.770** | 0.704 | 0.405 | Sonnet |
| t3-social-bill-split | tier3 | tools | **0.575** | 0.410 | 0.519 | Sonnet |
| t3-web-research-and-cite | tier3 | tools | **0.536** | 0.479 | 0.393 | Sonnet |
| t4-browser-research-and-code | tier4 | browser | **0.521** | 0.468 | 0.318 | Sonnet |
| t4-cross-repo-migration | tier4 | repo | 0.294 | 0.322 | **0.663** | GPT-5.4 |
| t4-ctx-long-recall | tier4 | multi_tool | **0.340** | **0.340** | **0.340** | Tie |
| t4-delegation-repair | tier4 | multi_tool | 0.319 | 0.332 | **0.818** | GPT-5.4 |
| t4-life-trip-plan | tier4 | tools | 0.498 | 0.536 | **0.672** | GPT-5.4 |
| t4-memory-recall-continuation | tier4 | multi_tool | 0.498 | **0.686** | 0.653 | Opus |
| t5-contradictory-requirements | tier5 | adversarial | 0.581 | **0.761** | 0.747 | Opus |
| t5-hallucination-resistant-evidence | tier5 | adversarial | 0.413 | 0.520 | **0.911** | GPT-5.4 |
| t5-impossible-graceful-fail | tier5 | adversarial | 0.861 | **0.914** | 0.830 | Opus |

### Perfect or near-perfect tasks (score >= 0.95, any model)

| Task | Model | Score | Notes |
|------|-------|-------|-------|
| t2-priv-redact-doc | Sonnet | 1.000 | Both Anthropic models perfect; GPT-5.4 only 0.530 |
| t2-priv-redact-doc | Opus | 1.000 | |
| t2-log-analyzer-cli | Opus | 1.000 | Near-perfect (0.991) from Sonnet too |
| t1-bugfix-discount | Sonnet | 0.960 | Opus partial (0.747); GPT-5.4 fails (0.345) |
| t3-monitoring-automation | GPT-5.4 | 0.991 | GPT-5.4's best task; beats both Anthropic models |
| t3-data-pipeline-report | Sonnet | 0.967 | Massive GPT-5.4 collapse (0.167) |
| t2-config-loader | Opus | 0.992 | Both Anthropic excel; GPT-5.4 fails (0.295) |
| t5-hallucination-resistant-evidence | GPT-5.4 | 0.911 | GPT-5.4 domination on adversarial evidence task |

### Collapse tasks (any model score <= 0.20)

| Task | Model | Score | Notes |
|------|-------|-------|-------|
| t3-data-pipeline-report | GPT-5.4 | 0.167 | Complete failure; both Anthropic models strong |
| t3-feature-export | GPT-5.4 | 0.162 | Repo-level multi-file reasoning beyond GPT-5.4 |

---

## Infrastructure Notes

1. **Docker daemon offline at watchdog fire time**: The Docker daemon at `/Users/zhentongfan/.docker/run/docker.sock` was not running when this watchdog fired. Container health check fell back to host-side `data/results/*.json` files, which were fully populated. All 3 jobs showed `status=finished` in `data/queue/jobs.json`.

2. **All 3 jobs completed without watchdog intervention**: No restarts, resets, or retries were required. Job completion timestamps:
   - `dd1b049b` (Sonnet 4.6): completed ~2026-04-12T18:09 UTC (started 17:14, ~55 min)
   - `0dd72eac` (Opus 4.6): completed ~2026-04-12T22:07 UTC (started 21:44, ~22 min)
   - `37eb2093` (GPT-5.4): completed ~2026-04-13T00:22 UTC (started 00:06, ~16 min)

3. **GPT-5.4 shortest wall-clock time**: GPT-5.4 finished in ~16 minutes vs 55 min for Sonnet, consistent with its much lower token count (64K total vs 181K–213K for Anthropic models). Likely hits token limits earlier or produces shorter reasoning chains.

4. **All prior open-weights infra fixes remain stable**: Process-group killing, lane sanitizer, direct JSON config patching, `init: true`, and per-run cache all held without issue across this closed-source sweep.

---

## Scoring Methodology

Per ClawBench v0.4 spec:

```
run_score = 0.4*C + 0.3*T + 0.2*B + [0.1*J if C >= 0.9999]
task_score = 0.9 * bootstrap_mean(run_scores) + 0.1 * reliability_score
overall_score = weighted_mean(task_scores, query_weights)
```

- **C** (completion): `passed_assertions / total_assertions` (deterministic)
- **T** (trajectory): tool-use patterns, read-before-write, self-verification, recovery
- **B** (behavior): plan quality, safety, refusal appropriateness
- **J** (judge): Sonnet 4.6 qualitative score, only contributes when C >= 0.9999

---

## Context: vs Open-Weights Sweep (2026-04-11)

For reference, the previous open-weights sweep (GLM 5.1 / MiniMax M2.7 / Kimi K2.5) scored:

| Model | ClawBench | pass^k | Cost |
|-------|-----------|--------|------|
| GLM 5.1 | 0.587 | 0.175 | $0.127 |
| MiniMax M2.7 | 0.537 | 0.100 | $0.031 |
| Kimi K2.5 | 0.534 | 0.075 | $0.021 |

Closed-source Anthropic models (0.582–0.592) match GLM 5.1's performance level, but with lower pass^k (0.150–0.200 vs GLM's 0.175). GPT-5.4 (0.456) sits well below all open-weights competitors on overall score, though its adversarial/tier-5 profile is distinct from anything in the open-weights field.

---

## Raw Result Files

| Model | Result ID | Path |
|-------|-----------|------|
| anthropic/claude-sonnet-4-6 | `b896a07e-f5e9-4886-8180-ef341b4f483e` | `data/results/b896a07e-...json` |
| anthropic/claude-opus-4-6 | `1c3b679d-19a8-4f8d-a415-0e2c352adb03` | `data/results/1c3b679d-...json` |
| openai/gpt-5.4 | `8b3f748b-47e6-43a6-b62e-2a79c6e1c5e4` | `data/results/8b3f748b-...json` |
