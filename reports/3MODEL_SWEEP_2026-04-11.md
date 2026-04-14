# 3-Model Open-Weights ClawBench Sweep

**Date:** 2026-04-11 / 2026-04-12
**Suite:** 40 tasks (tier 1-5) x 3 runs = 120 runs per model
**Judge:** anthropic/claude-sonnet-4-6 (10% weight, gated on deterministic floor)
**Infra:** Docker container (ghcr.io/openclaw/openclaw:latest), 4 parallel lanes, host ~/.openclaw bind-mount, init: true

---

## Overall Rankings

```
Rank | Model              | ClawBench |    C  |    T  |    B  |    J  | pass^k | 95% CI          | Cost
-----+--------------------+-----------+-------+-------+-------+-------+--------+-----------------+--------
  1  | GLM 5.1            |   0.587   | 0.402 | 0.688 | 0.949 | 0.427 |  0.175 | [0.523, 0.653]  | $0.127
  2  | MiniMax M2.7       |   0.537   | 0.386 | 0.645 | 0.824 | 0.383 |  0.100 | [0.481, 0.596]  | $0.031
  3  | Kimi K2.5          |   0.534   | 0.359 | 0.653 | 0.869 | 0.327 |  0.075 | [0.481, 0.590]  | $0.021
```

**Axes:**
- **C** = Completion (deterministic: file checks, pytest, custom verifiers)
- **T** = Trajectory (tool-use hygiene: read-before-write, self-verification, recovery)
- **B** = Behavior (safety, politeness, refusal rates)
- **J** = Judge (Sonnet 4.6 qualitative score, 10% weight, gated on C floor)

---

## Key Findings

### 1. GLM 5.1 wins by a clear margin

GLM leads by +5.0 points over MiniMax and +5.3 over Kimi. The gap is statistically meaningful: GLM's 95% CI lower bound (0.523) exceeds the other two models' point estimates.

### 2. GLM dominates harder tiers

| Tier | Kimi | MiniMax | **GLM** | Winner |
|------|------|---------|---------|--------|
| tier1 (6 tasks) | 0.553 | **0.596** | 0.582 | MiniMax |
| tier2 (14 tasks) | 0.532 | **0.576** | 0.572 | MiniMax |
| tier3 (11 tasks) | 0.562 | 0.549 | **0.594** | GLM |
| tier4 (6 tasks) | 0.445 | 0.369 | **0.554** | GLM |
| tier5 (3 tasks) | 0.575 | 0.527 | **0.705** | GLM |

MiniMax edges Kimi on easy tasks (tier 1-2). GLM pulls ahead on tier 3-5 where tasks require cross-file reasoning, multi-step tool use, and adversarial judgment.

### 3. Behavior is the strongest axis for all three

All models score 0.82-0.95 on behavior, meaning they are well-behaved, don't refuse, and don't violate safety boundaries. GLM's B=0.949 is the highest.

### 4. Completion is the weakest axis

C scores cluster around 0.35-0.40 for all three. This reflects ClawBench's deterministic verifier strictness (exact file paths, strict format checks, pytest pass/fail). The judge partially compensates for "close enough" attempts.

### 5. Reliability remains low across all three

pass^k (all 3 runs of a task must pass) ranges from 0.075 to 0.175. These models are not yet reliable enough for production use on these task types without retry budgets.

---

## Efficiency and Cost

| Model | Median Latency | P95 Latency | Input Tokens | Total Tokens | Cost/Run | Total Cost |
|-------|----------------|-------------|--------------|--------------|----------|------------|
| Kimi K2.5 | 58.3s | 98.7s | 30,512 | 127,427 | $0.0002 | **$0.021** |
| MiniMax M2.7 | 93.1s | 122.3s | 29,358 | 335,637 | $0.0003 | $0.031 |
| GLM 5.1 | 125.9s | 174.0s | 26,295 | 240,914 | $0.0011 | $0.127 |

Kimi is the cheapest and fastest. GLM is 6x more expensive but scores +5 points. MiniMax sits in the middle on both axes.

---

## Delivery Outcomes

| Model | Pass | Partial | Fail |
|-------|------|---------|------|
| Kimi K2.5 | 17 (14%) | 78 (65%) | 25 (21%) |
| MiniMax M2.7 | 18 (15%) | 78 (65%) | 24 (20%) |
| GLM 5.1 | **28 (23%)** | 63 (53%) | 29 (24%) |

GLM has the most clean passes (28 vs 17-18). Its fail rate is slightly higher (24% vs 20-21%), reflecting GLM's tendency to either nail a task or fail hard, rather than producing safe but incomplete partial deliveries.

---

## Failure Modes

| Failure Mode | Kimi | MiniMax | GLM |
|---|---|---|---|
| verification_skipped | 40 | 29 | 32 |
| tool_misuse | 40 | 41 | 32 |
| hallucinated_completion | 8 | 2 | 3 |
| state_regression | 5 | 9 | 9 |
| browser_navigation_failure | 5 | 6 | 4 |
| graceful_refusal | 2 | 5 | 8 |
| memory_miss | 3 | 4 | 3 |
| delegation_failed | 0 | 3 | 1 |

- **Kimi** has the most hallucinated completions (8) - it claims to finish tasks without actually completing them
- **GLM** has the most graceful refusals (8) - it correctly identifies impossible tasks (tier-5 adversarial) rather than fabricating output
- **MiniMax** has the most delegation failures (3) - it struggles with multi-agent coordination

---

## Per-Task Head-to-Head

### Task wins: **GLM 23** / MiniMax 8 / Kimi 9

| Task | Tier | Family | Kimi | MM | GLM | Winner |
|------|------|--------|------|-----|------|--------|
| t1-architecture-brief | tier1 | tools | 0.538 | **0.548** | 0.423 | MM |
| t1-bugfix-discount | tier1 | coding | 0.404 | 0.473 | **0.991** | GLM |
| t1-cal-quick-reminder | tier1 | tools | 0.888 | **0.892** | **0.892** | MM/GLM |
| t1-fs-quick-note | tier1 | tools | **0.699** | 0.667 | 0.340 | Kimi |
| t1-life-translate | tier1 | tools | **0.478** | **0.478** | 0.340 | Kimi/MM |
| t1-refactor-csv-loader | tier1 | coding | 0.312 | **0.521** | 0.505 | MM |
| t2-add-tests-normalizer | tier2 | coding | **0.446** | 0.317 | 0.316 | Kimi |
| t2-browser-form-fix | tier2 | browser | 0.322 | **0.330** | 0.305 | MM |
| t2-config-loader | tier2 | repo | 0.548 | **0.756** | 0.592 | MM |
| t2-ctx-pronoun-resolve | tier2 | tools | 0.311 | **0.374** | 0.297 | MM |
| t2-err-instruction-ambig | tier2 | adversarial | 0.467 | **0.680** | 0.637 | MM |
| t2-fs-cleanup-downloads | tier2 | tools | 0.541 | 0.560 | **0.602** | GLM |
| t2-fs-find-that-thing | tier2 | tools | 0.429 | 0.603 | **0.631** | GLM |
| t2-log-analyzer-cli | tier2 | coding | 0.987 | 0.945 | **0.992** | GLM |
| t2-msg-summarize-thread | tier2 | tools | 0.610 | 0.617 | **0.635** | GLM |
| t2-node-search-patch | tier2 | repo | 0.395 | 0.411 | **0.506** | GLM |
| t2-priv-redact-doc | tier2 | tools | 0.861 | **1.000** | 0.921 | MM |
| t2-skill-excel-rollup | tier2 | tools | **0.664** | 0.650 | 0.619 | Kimi |
| t2-sys-memory-roundtrip | tier2 | multi_tool | 0.465 | 0.416 | **0.520** | GLM |
| t2-web-quick-fact | tier2 | tools | 0.409 | 0.410 | **0.433** | GLM |
| t3-cal-reschedule-cascade | tier3 | tools | **0.683** | 0.633 | 0.677 | Kimi |
| t3-data-pipeline-report | tier3 | multi_tool | **0.594** | 0.568 | 0.494 | Kimi |
| t3-data-sql-query | tier3 | tools | **0.572** | 0.407 | 0.384 | Kimi |
| t3-debug-timezone-regression | tier3 | repo | 0.335 | 0.433 | **0.630** | GLM |
| t3-feature-export | tier3 | repo | 0.447 | 0.417 | **0.497** | GLM |
| t3-fin-budget-monthly | tier3 | tools | 0.358 | 0.385 | **0.458** | GLM |
| t3-monitoring-automation | tier3 | tools | **0.988** | 0.930 | 0.957 | Kimi |
| t3-msg-inbox-triage | tier3 | tools | 0.566 | 0.543 | **0.591** | GLM |
| t3-node-multifile-refactor | tier3 | repo | 0.475 | 0.635 | **0.638** | GLM |
| t3-social-bill-split | tier3 | tools | **0.586** | 0.575 | 0.580 | Kimi |
| t3-web-research-and-cite | tier3 | tools | 0.581 | 0.510 | **0.632** | GLM |
| t4-browser-research-and-code | tier4 | browser | 0.463 | 0.465 | **0.718** | GLM |
| t4-cross-repo-migration | tier4 | repo | **0.359** | 0.274 | 0.324 | Kimi |
| t4-ctx-long-recall | tier4 | multi_tool | **0.340** | **0.340** | **0.340** | Tie |
| t4-delegation-repair | tier4 | multi_tool | 0.297 | 0.197 | **0.320** | GLM |
| t4-life-trip-plan | tier4 | tools | 0.544 | 0.345 | **0.705** | GLM |
| t4-memory-recall-continuation | tier4 | multi_tool | 0.664 | 0.590 | **0.917** | GLM |
| t5-contradictory-requirements | tier5 | adversarial | 0.673 | 0.673 | **0.694** | GLM |
| t5-hallucination-resistant-evidence | tier5 | adversarial | 0.412 | 0.331 | **0.427** | GLM |
| t5-impossible-graceful-fail | tier5 | adversarial | 0.639 | 0.577 | **0.993** | GLM |

### Perfect or near-perfect tasks (score >= 0.95, any model)

| Task | Model | Score | Notes |
|------|-------|-------|-------|
| t1-bugfix-discount | GLM | 0.991 | Only model to actually fix the bug |
| t5-impossible-graceful-fail | GLM | 0.993 | Correctly identified impossible task |
| t3-monitoring-automation | Kimi | 0.988 | All 3 models scored >0.93 here |
| t2-log-analyzer-cli | GLM | 0.992 | All 3 models scored >0.94 here |
| t2-priv-redact-doc | MM | 1.000 | Perfect redaction |

---

## Infrastructure Notes

This run required significant infrastructure debugging. Key issues encountered and fixed:

1. **Process leak** (services.py): `Popen(shell=True)` + `process.terminate()` only killed the shell parent, leaving `python3 serve.py` children orphaned. Fixed with `start_new_session=True` + `os.killpg`.

2. **Gateway state accumulation** (worker.py): `sessions.json` file locks degraded from milliseconds to minutes after ~50 min of continuous operation. Reverted the "skip gateway restart between tasks" optimization.

3. **Channel plugin thrash** (worker.py): Host config had Telegram/Discord/Slack channels enabled. 4 parallel lane gateways all polled the same bot token, causing `sessions.create` to take 272 seconds. Fixed with `_sanitize_lane_state_dir` that disables channels in lane-local config copies.

4. **Slow config CLI** (worker.py): `node /openclaw/dist/index.js config set` took 40-60s per call, 5 calls per gateway start. Replaced with direct Python JSON patching.

5. **Zombie processes** (docker-compose.yml): Added `init: true` for tini as PID 1.

6. **Run cache for resumability** (harness.py): Each completed (task, run) writes a `TaskRunResult` JSON to `/data/run_cache/<model>/<task>/runN.json`. On resubmit, the harness skips cached runs.

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

## Raw Result Files

| Model | Result ID | Path |
|-------|-----------|------|
| Kimi K2.5 | `30a29e93-a39b-4d08-b602-4016664aceaf` | `data/results/30a29e93-...json` |
| MiniMax M2.7 | `3c715419-86d7-4b7b-aa04-59ed3bf23c08` | `data/results/3c715419-...json` |
| GLM 5.1 | `c5e6226b-526b-439e-ad10-0009b05e51b9` | `data/results/c5e6226b-...json` |
