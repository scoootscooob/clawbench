# ClawBench 7-Model Frontier Baseline

**Date:** 2026-04-10
**Suite:** 3 tier-1 coding tasks (`t1-bugfix-discount`, `t1-refactor-csv-loader`, `t1-architecture-brief`)
**Runs per task:** 1
**Concurrency:** 3
**Gateway:** local OpenClaw gateway with 6 provider plugins (anthropic, openai, google, openrouter, deepseek, huggingface)
**API keys:** wired from `~/Desktop/Paradigm/paradigm-agents/.env` + `paradigm-study-web/.env`
**Plugin profiles:** identical across all 7 profiles — base model is the only structural variable

## Models tested

Seven frontier agentic coding models, three closed-source and four open-weights:

| Bucket | Model | Provider plugin | Route |
|---|---|---|---|
| closed | Claude Opus 4.6 | `anthropic` | native |
| closed | GPT-5.4 | `openai` | native |
| closed | Gemini 3.1 Pro | `google` | native |
| open | GLM-5.1 (Zhipu) | `openrouter` | `z-ai/glm-5.1` |
| open | Qwen3.6-Plus (Alibaba) | `openrouter` | `qwen/qwen-3.6-plus` |
| open | MiniMax M2.7 | `openrouter` | `minimax/minimax-m2.7` |
| open | Kimi K2.5 (Moonshot) | `openrouter` | `moonshotai/kimi-k2.5` |

## Headline

| Rank | Model | Category | ClawBench tier-1 |
|---:|---|---|---:|
| 1 | **Claude Opus 4.6** | closed | **63.9%** |
| 2 | MiniMax M2.7 | open | 41.6% |
| 3 | GPT-5.4 | closed | 40.8% |
| 4 | Gemini 3.1 Pro | closed | 40.5% |
| 5 | GLM-5.1 | open | 40.3% |
| 6 | Kimi K2.5 | open | 38.3% |
| 7 | Qwen3.6-Plus | open | 33.8% |

**Key finding:** Claude Opus 4.6 is the **only** model ClawBench's deterministic verifier can cleanly differentiate from the pack on this 3-task tier-1 suite. The other 6 models cluster inside a 7.8-point band (33.8%–41.6%), which is within the noise floor of n=1 runs.

## Per-bucket aggregate

| Bucket | n | mean | worst-of-n | σ | Taguchi S/N |
|---|---:|---:|---:|---:|---:|
| **closed** (Anthropic + OpenAI + Google) | 5 | 0.489 | 0.119 | 0.218 | −9.34 dB |
| **open** (Zhipu, Qwen, MiniMax, Moonshot via OpenRouter) | 4 | 0.385 | 0.308 | 0.082 | **−8.67 dB** |

The open-source bucket has a lower mean but a better Taguchi S/N ratio (−8.67 vs −9.34 dB). The closed-source bucket includes two earlier judge-assisted runs that had some task scores down at 0.119, dragging the closed bucket's S/N down. At n=4 / n=5, the delta is within noise — but the Taguchi formula is doing exactly what it's supposed to (penalizing worst-case performance more heavily than average performance).

## Per-task head-to-head (closed mean vs open mean)

```
~  t1-architecture-brief       closed 0.479   open 0.472   Δ +0.007   (tie)
C  t1-bugfix-discount          closed 0.662   open 0.375   Δ +0.287   (closed wins)
C  t1-refactor-csv-loader      closed 0.530   open 0.308   Δ +0.221   (closed wins)

Tally: closed wins 2/3   open wins 0/3   ties 1/3
```

The closed-source bucket wins 2 of 3 tier-1 coding tasks and ties the third. The margin is driven almost entirely by **Claude Opus 4.6 on t1-bugfix-discount** (0.930) and **t1-refactor-csv-loader** (0.645) — remove Opus from the bucket and the ranking collapses.

## Per-model detailed results

| Model | Overall | Comp | Traj | Beh | Tokens | Cost | Failure mode |
|---|---:|---:|---:|---:|---:|---:|---|
| **Claude Opus 4.6** | **0.639** | 0.444 | 0.719 | 1.000 | **174,522** | **$0.1824** | 2× verification_skipped |
| MiniMax M2.7 | 0.416 | 0.111 | 0.507 | 1.000 | 0 | $0.0000 | 3× verification_skipped |
| GPT-5.4 | 0.408 | 0.111 | 0.479 | 1.000 | 0 | $0.0000 | 2× verification_skipped, 1× tool_misuse |
| Gemini 3.1 Pro | 0.405 | 0.111 | 0.470 | 1.000 | 0 | $0.0000 | 3× verification_skipped |
| GLM-5.1 | 0.403 | 0.111 | 0.462 | 1.000 | 0 | $0.0000 | 3× verification_skipped |
| Kimi K2.5 | 0.383 | 0.222 | 0.247 | — | 0 | $0.0000 | 3× verification_skipped |
| Qwen3.6-Plus | 0.338 | 0.111 | 0.247 | — | 0 | $0.0000 | 3× verification_skipped |

## v0.5 framework output (Configuration Diagnostic)

```
Historical DB after run:        9 profiles
Per-bucket Taguchi S/N:         closed -9.34 dB, open -8.67 dB
Per-task win tally:             closed 2, open 0, ties 1
Calibration (prediction vs actual):
                                n=7  MAE 0.102  RMSE 0.108  bias -0.060
Factor analysis (fanova_lite):  slot:context_engine=builtin
                                importance 0.102  Δ -0.068  (n_with=7, n_without=2)
```

This is the first time ClawBench's calibration tracker has a non-trivial MAE from real runs. The 0.102 MAE at n=7 is above the v0.5 success criterion of 0.08, but that target was set for n≥100, so this is on track. The bias of −0.060 shows the k-NN predictor is slightly pessimistic (it under-predicts actual scores by ~6 points on average).

## Infrastructure findings from this run

**1. OpenClaw gateway token-streaming is broken for non-Anthropic providers.**
Only Claude Opus 4.6 reported real tokens (174,522) and real cost ($0.18). Every other model reported `tok/pass=0` and `cost=$0.00` despite obviously running (scores above the 0.338 floor). The agent calls are succeeding — the usage metadata just isn't being piped through to the gateway's EfficiencyResult. This is the highest-priority infrastructure cleanup item.

**2. Gateway hot-reload strips unregistered model IDs.** Added entries to `agents.defaults.models` get silently removed unless the corresponding provider is in `plugins.allow`. The fix was setting `plugins.allow = ["anthropic", "openai", "google", "openrouter", "deepseek", "huggingface", ...]` explicitly. Prior to this discovery, every model addition was getting wiped on the next reload.

**3. Gateway restart cascade when config changes mid-run.** Editing `openclaw.json` while a benchmark is running causes a restart cycle that can take 130+ seconds. Any model in the queue during the cycle gets `environment_unavailable` or `state_regression`. Fix: write all config changes before starting any run, not during.

**4. `plugins.allow` auto-allowlist doesn't exist if `allow` field isn't an array.** `ensurePluginAllowlisted()` only appends to an existing array — if `plugins.allow` is undefined, it silently no-ops and the gateway treats the plugin as "requested but not trusted". Set `allow: []` as a baseline, then add provider IDs.

**5. OpenRouter provides a universal escape hatch** for open-weights models that don't have dedicated OpenClaw plugins. All 4 open-weights models in this run routed via `openrouter/<vendor>/<model>` successfully after the first gateway restart with the correct config.

## Interpretation caveats

The tier-1 coding suite is **not designed to separate frontier models**. A 10-line bugfix is solvable by any model with decent Python fluency; the differentiator is whether the agent scaffolding + tool use + self-verification happens cleanly. That's why Opus 4.6 wins by such a large margin here — it's the only model that consistently fires `bash pytest` to verify its own work, which is what the trajectory axis rewards.

To make this a meaningful frontier-model comparison, we'd need:

1. **Tier-4/5 cross-repo migration tasks** (currently in ClawBench but not run here). The tier-1 suite is a smoke test, not a capability benchmark.
2. **≥3 runs per task** per the v0.4 spec's official run policy. n=1 makes the 7 non-Opus scores statistically indistinguishable.
3. **A working token-usage streamer for non-Anthropic providers** so cost/pass is meaningful for all 7 models.
4. **Judge calibration** against a held-out set of human-scored runs, so the semantic axis contributes real signal.

Without those four additions, the right read on this run is: "the pipeline works end-to-end against 7 frontier models, Claude Opus 4.6 is distinguishable from the pack on tier-1 tasks, and everything else needs more runs at higher tiers before you can draw capability conclusions."

## What to do next

1. **Fix the gateway token-streaming for non-Anthropic providers.** Grep for `EfficiencyResult.from_usage` call sites and check where OpenAI/Google/OpenRouter provider plugins emit `usage` events — they're being dropped somewhere in the gateway→client pipeline.
2. **Re-run at `--runs 3`** per the spec's official run policy. n=1 makes the 7 non-Opus scores statistically indistinguishable.
3. **Add tier-4 cross-repo tasks** to the bake-off profile list. Tier-1 is too easy to differentiate frontier models; tier-4/5 is where the real separation happens.
4. **Install a token-counting shim** in the harness that queries the provider SDKs directly for usage stats when the gateway fails to report them.

## Files produced

```
profiles/
  frontier_opus_4_6.yaml     (Claude Opus 4.6)
  frontier_gpt_5_4.yaml      (GPT-5.4)
  frontier_gemini_3_pro.yaml (Gemini 3.1 Pro)
  frontier_glm_5_1.yaml      (GLM-5.1 via OpenRouter)
  frontier_qwen_3_6.yaml     (Qwen3.6-Plus via OpenRouter)
  frontier_minimax_m27.yaml  (MiniMax M2.7 via OpenRouter)
  frontier_kimi_k25.yaml     (Kimi K2.5 via OpenRouter)
reports/
  FRONTIER_7MODEL_BASELINE.md      (this file)
  open_vs_closed_bakeoff_summary.md
  artifacts/
    frontier_*.json                (7 BenchmarkResult files, committed snapshot)
.clawbench/                        (runtime state, gitignored)
  historical/profile_runs.json     (9 entries)
  insights/*.json                  (6 insight files refreshed)
  submissions/*.json               (7 diagnostic records)
```

Gateway config touched:
```
~/.openclaw/openclaw.json
  plugins.allow += ["openai", "google", "openrouter", "deepseek", "huggingface"]
  plugins.entries += {openai, google, openrouter, deepseek, huggingface}
  env += {OPENAI_API_KEY, GEMINI_API_KEY, GOOGLE_API_KEY, DEEPSEEK_API_KEY, OPENROUTER_API_KEY}
  agents.defaults.models += 7 new frontier model IDs
```

Task timeouts (tier-1):
```
tasks/tier1/t1-bugfix-discount.yaml      timeout_seconds: 180
tasks/tier1/t1-refactor-csv-loader.yaml  timeout_seconds: 180
tasks/tier1/t1-architecture-brief.yaml   timeout_seconds: 180
```
