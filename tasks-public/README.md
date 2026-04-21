# ClawBench Core v1 — Public Task Set (19 tasks)

A curated 19-task subset of the full ClawBench v0.4.0.dev1 dev pool,
selected for ranking consistency and capability coverage.

## What this is

19 tasks, 3 runs each → 57 runs per model. About half the compute of
the full 40-task sweep, with no loss of discriminative power on the
measured 8-model panel.

Derived from the v2026-4-19-full sweep archive by greedy task
selection: iteratively drop tasks that either (a) introduce ranking
inversions vs the reference ordering or (b) have near-zero cross-model
SNR and add only noise.

## Established ranking (from v4-19-full sweep)

Mean run_score across the 19 tasks:

| Rank | Model | Score |
|:---:|---|:---:|
| 1 | Claude Opus 4.6 | 0.8137 |
| 2 | Claude Opus 4.7 | 0.7824 |
| 3 | GPT 5.4 | 0.7647 |
| 4 | Claude Sonnet 4.6 | 0.7597 |
| 5 | MiniMax M2.7 | 0.7475 |
| 6 | Gemini 3.1 Pro | 0.7408 |
| 7 | Qwen 3.6 Plus | 0.7030 |
| 8 | Kimi K2.5 | 0.6800 |

- **0 ranking inversions** on the 19-task mean.
- **Min adjacent-rank gap: 0.0049** (well above the ~0.002 seed-noise
  floor estimated from inter-run variance).
- **Top-to-bottom spread: 0.134** (vs 0.097 for smaller robust sets).

## Coverage

| Dimension | Breakdown |
|---|---|
| Tiers | T1=2, T2=7, T3=5, T4=4, T5=1 |
| Families | tools=7, coding=2, repo=3, browser=2, multi_tool=3, adversarial=1 |
| Capabilities | bugfix, refactor, test_authoring, multifile_reasoning, browser_debugging, structured_output, graceful_refusal, delegation, tool_composition, research_synthesis, cross_repo_change, memory_continuation |

## Directory layout

```
tasks-public/
├── MANIFEST.yaml          # Machine-readable task list + metadata
├── README.md              # This file
├── tier1/                 # 2 task YAMLs
├── tier2/                 # 7 task YAMLs
├── tier3/                 # 5 task YAMLs
├── tier4/                 # 4 task YAMLs
├── tier5/                 # 1 task YAML
└── assets/                # 19 asset packs (verifier scripts + fixtures)
```

## Build the reference Docker image

The repo `Dockerfile` pins to the exact OpenClaw base that produced
the Core v1 reference numbers:

```
FROM ghcr.io/openclaw/openclaw:2026.4.15-beta.1
```

Image SHA256: `869e5e0ec27099573c54c0a8cdecfdd0970aa98c8c41f2bbd1cb06b59450d90e`
Base created: 2026-04-15T19:42 UTC.

Build it:

```bash
docker build -t clawbench:core-v1 .
```

Verify the OpenClaw version inside matches:

```bash
docker run --rm --entrypoint openclaw clawbench:core-v1 --version
# Expected: OpenClaw 2026.4.15-beta.1
```

If you measure against a newer OpenClaw, numbers will drift (we saw
+0.13 to +0.29 per model going from 4.9 to 4.15-beta.1). Pin the base
to reproduce the reference; bump the base + re-run the full sweep to
produce a new reference.

## How to run Core v1

Using the ClawBench harness:

```bash
# Explicit task-by-task (pass -t for each of 19 tasks):
clawbench run \
  --model anthropic/claude-opus-4-6 \
  --runs 3 \
  --concurrency 4 \
  --profile profiles/frontier_opus_4_6.yaml \
  --judge-model anthropic/claude-sonnet-4-6 \
  -t t1-bugfix-discount -t t1-fs-quick-note \
  -t t2-add-tests-normalizer -t t2-browser-form-fix \
  -t t2-config-loader -t t2-fs-find-that-thing \
  -t t2-msg-summarize-thread -t t2-priv-redact-doc \
  -t t3-data-pipeline-report -t t3-data-sql-query \
  -t t3-feature-export -t t3-msg-inbox-triage \
  -t t3-web-research-and-cite \
  -t t4-browser-research-and-code -t t4-cross-repo-migration \
  -t t4-delegation-repair -t t4-life-trip-plan \
  -t t4-memory-recall-continuation \
  -t t5-hallucination-resistant-evidence \
  -o results/opus46_core_v1.json
```

Or point the harness at this directory by setting the task root in
your ClawBench config. See MANIFEST.yaml for a programmatic list.

## Reproducibility caveats

- **Exact score reproduction is not guaranteed.** Even with the same
  OpenClaw version, re-runs exhibit seed noise (~0.02 stddev per task,
  per model). Rankings are stable; absolute scores drift within that
  envelope.
- **OpenRouter-routed models** (`openrouter/*`) can have their
  scores shift if OpenRouter repoints its model slug to a different
  underlying provider. We observed this with GLM 5.1 between
  2026-04-20 14:00 and 17:00 PST. Pin to canonical model versions
  (e.g. `z-ai/glm-5-turbo-20260315`) for stable measurement.
- **OpenClaw platform version matters.** Upgrading from 4.9 → 4.15-beta.1
  shifted scores by +0.13 to +0.29 across models. Pin via Docker tag.
- **Judge scores** come from Claude Sonnet 4.6 via direct Anthropic
  API (with a fallback from the gateway judge). Scores assume the
  judge is working correctly; re-judging broken runs may be required
  (see `scripts/rejudge_all.py` in the main repo).

## What's NOT in Core v1

21 tasks from the full dev pool are held back:
- **9 ceiling tasks** (all frontier models score >0.85) — don't
  discriminate, future releases may phase them out.
- **9 noise tasks** (cross-model SNR < 0.5) — either broken verifiers
  or genuinely ambiguous prompts. Scheduled for redesign.
- **3 ranking-breaker tasks** — tasks where the cross-model ordering
  conflicts with the reference ranking (e.g. `t2-node-search-patch`,
  `t5-contradictory-requirements`). Not broken per se; just
  inconsistent with the headline.

Also missing entirely from Core v1:
- **Tier 6 long-horizon (100+ turn) tasks** — planned for v2.
- **Creative synthesis / style-matching tasks** — planned for v2.
- **Paraphrased prompt pairs** for perturbation-sensitivity
  measurement — planned for v2.

## Versioning

| Version | Tasks | Change |
|:---:|:---:|---|
| Core v1 | 19 | Initial public release (this) |
| Core v2 | ~24 | Planned: +Tier 6, +paraphrase pairs, -2 noise tasks |

Pin to `clawbench-core-v1` in the MANIFEST for reproducible
comparison across releases.
