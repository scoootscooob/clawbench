# ClawBench Baseline Sources

This document records the empirical sources that informed ClawBench's task
design. ClawBench's tier structure, task families, trajectory-length targets,
tool-family mix, scenario weights, and difficulty bands are **designed
referencing these sources**. None of them are loaded at runtime — they are
provenance artifacts for the design decisions baked into `tasks/` and
[`clawbench/query_catalog.py`](../clawbench/query_catalog.py).

Contents:

1. [Public Hugging Face agent-trace datasets](#1-public-hugging-face-agent-trace-datasets)
2. [Hermes agent reasoning traces (aggregate)](#2-hermes-agent-reasoning-traces-aggregate)
3. [Internal personal-agent use-case corpus](#3-internal-personal-agent-use-case-corpus)
4. [How the sources map onto ClawBench's design](#4-how-the-sources-map-onto-clawbenchs-design)

---

## 1. Public Hugging Face agent-trace datasets

The 24 datasets on Hugging Face tagged
[`format:agent-traces`](https://huggingface.co/datasets?format=format:agent-traces&sort=trending)
inform the task-family mix and the trajectory-shape targets (turn counts,
tool diversity, recovery patterns) used throughout the ClawBench task corpus.

| # | Dataset | Rows | Cluster | Notes |
|---:|---|---:|---|---|
| 1 | [`badlogicgames/pi-mono`](https://huggingface.co/datasets/badlogicgames/pi-mono) | 627 | Pi sessions (root) | Primary source; ~627 unique sessions |
| 2 | [`cfahlgren1/pi-mono-fresh`](https://huggingface.co/datasets/cfahlgren1/pi-mono-fresh) | 627 | Pi sessions (mirror) | Mirror of root |
| 3 | [`JohnBeanerson/pi-mono-test`](https://huggingface.co/datasets/JohnBeanerson/pi-mono-test) | 627 | Pi sessions (mirror) | Mirror of root |
| 4 | [`karkowww/pi-mono`](https://huggingface.co/datasets/karkowww/pi-mono) | 627 | Pi sessions (mirror) | Mirror of root |
| 5 | [`vinhnx90/vtcode-sessions`](https://huggingface.co/datasets/vinhnx90/vtcode-sessions) | 172 | Custom agent traces | Coding agent sessions |
| 6 | [`thomasmustier/pi-for-excel-sessions`](https://huggingface.co/datasets/thomasmustier/pi-for-excel-sessions) | 140 | Pi sessions (domain) | Excel-specific agent work |
| 7 | [`0xSero/pi-sessions`](https://huggingface.co/datasets/0xSero/pi-sessions) | 96 | Pi sessions (domain) | Mixed-domain sessions |
| 8 | [`championswimmer/pi-coding-sessions`](https://huggingface.co/datasets/championswimmer/pi-coding-sessions) | 27 | Pi sessions (domain) | Coding-focused subset |
| 9 | [`jedisct1/agent-traces-swival`](https://huggingface.co/datasets/jedisct1/agent-traces-swival) | 20 | Custom format | Experimental traces |
| 10 | [`LarsEckart/approvaltests-java-sessions`](https://huggingface.co/datasets/LarsEckart/approvaltests-java-sessions) | 15 | Custom agent traces | Java / approval-test workflows |
| 11 | [`cfahlgren1/agent-sessions-list`](https://huggingface.co/datasets/cfahlgren1/agent-sessions-list) | 12 | Index dataset | Metadata for other trace repos |
| 12 | [`thomasmustier/pi-nes-sessions`](https://huggingface.co/datasets/thomasmustier/pi-nes-sessions) | 12 | Pi sessions (domain) | NES-related sessions |
| 13 | [`moikapy/0xKobolds`](https://huggingface.co/datasets/moikapy/0xKobolds) | 11 | Custom agent traces | Kobold-specific traces |
| 14 | [`badlogicgames/pi-diff-review`](https://huggingface.co/datasets/badlogicgames/pi-diff-review) | 7 | Pi sessions (review) | Diff-review traces |
| 15 | [`cfahlgren1/pi-diff-review`](https://huggingface.co/datasets/cfahlgren1/pi-diff-review) | 6 | Pi sessions (review) | Mirror of #14 |
| 16 | [`lhoestq/agent-traces-example`](https://huggingface.co/datasets/lhoestq/agent-traces-example) | 4 | Demo / example | Canonical example format |
| 17 | [`DreamyDetective/trace-demo`](https://huggingface.co/datasets/DreamyDetective/trace-demo) | 3 | Demo / example | Schema demo |
| 18 | [`davanstrien/pi-trace-parser-sessions`](https://huggingface.co/datasets/davanstrien/pi-trace-parser-sessions) | 3 | Parser experiments | Parser validation |
| 19 | [`davanstrien/pi-traces`](https://huggingface.co/datasets/davanstrien/pi-traces) | 2 | Pi sessions (sample) | Small sample |
| 20 | [`dongxx1104/Baseline_featbeach`](https://huggingface.co/datasets/dongxx1104/Baseline_featbeach) | 2 | Custom | Project-specific |
| 21 | [`victor/claude-code-sessions`](https://huggingface.co/datasets/victor/claude-code-sessions) | 1 | Claude Code | Single reference session |
| 22 | [`JohnBeanerson/claude-code-sessions-test`](https://huggingface.co/datasets/JohnBeanerson/claude-code-sessions-test) | 1 | Claude Code | Test sample |
| 23 | [`lukawskikacper/openai-agent-traces`](https://huggingface.co/datasets/lukawskikacper/openai-agent-traces) | 1 | OpenAI agents | Single reference session |
| 24 | [`mishig/traces`](https://huggingface.co/datasets/mishig/traces) | 1 | Demo / example | Single-row demo |

**Aggregate**: ~3,049 rows across 24 repos. Deduplicated (removing the three
`pi-mono` mirrors that are exact copies of `badlogicgames/pi-mono`), the
unique-source count is roughly **~1,168 sessions** across ~15 distinct agent
workflows.

### Dataset clusters

| Cluster | Approx unique sessions | What it contributes to ClawBench design |
|---|---:|---|
| **Pi sessions** (`badlogicgames/pi-mono` + domain spinoffs) | ~920 | Dominant format. Drives the turn-count distribution (`t1-t4` trajectory length targets), tool diversity expectations, and the "multi-tool" and "repo" task family definitions. |
| **Custom agent traces** (`vtcode-sessions`, `approvaltests-java-sessions`, `0xKobolds`) | ~198 | Informs the tier-2/3 coding task design: cross-file reasoning, test-driven workflows, and language-specific failure modes (`t2-node-search-patch`, `t3-node-multifile-refactor`). |
| **Claude Code / OpenAI agents** (`victor/claude-code-sessions`, `lukawskikacper/openai-agent-traces`, `JohnBeanerson/claude-code-sessions-test`) | ~3 | Single-row reference sessions; validate trace-shape assumptions but too few for quantitative weighting. |
| **Index and demo** (`agent-sessions-list`, `agent-traces-example`, `trace-demo`, `mishig/traces`, `DreamyDetective/trace-demo`) | ~22 | Schema and format validation. Used to verify that ClawBench's internal `Transcript` shape can represent what the ecosystem is publishing. |

---

## 2. Hermes agent reasoning traces (aggregate)

Source: `lambda/hermes-agent-reasoning-traces`

Aggregate statistics from a separate trace corpus of **14,701 real agent
sessions**, used to calibrate the tier-to-family mapping and tier trajectory
targets:

```json
{
  "sessions_analyzed": 14701,
  "observed_complexity": {
    "avg_turns": 24.3,
    "avg_tool_calls": 13.9,
    "max_turns": 54,
    "tool_diversity_per_task": "3-6"
  }
}
```

### Observed category distribution

| Category | Session count | % of total | ClawBench family |
|---|---:|---:|---|
| `agent_tools` | 4,249 | 28.9% | `tools` |
| `terminal_coding` | 4,247 | 28.9% | `coding` |
| `repository_tasks` | 2,131 | 14.5% | `repo` |
| `browser_automation` | 1,687 | 11.5% | `browser` |
| `file_operations` | 891 | 6.1% | `tools` |
| `multi_tool` | 859 | 5.8% | `multi_tool` |
| `scheduling` | 308 | 2.1% | `tools` |
| `planning` | 293 | 2.0% | `tools` |
| `conversational` | 36 | 0.2% | — (excluded) |

### Tier-to-family mapping (derived)

The observed Hermes distribution directly informs the tier → family mapping
in [`clawbench/tasks.py`](../clawbench/tasks.py):

```
tier1 → coding, tools
tier2 → coding, repo, browser
tier3 → repo, multi_tool, tools
tier4 → repo, multi_tool, browser
tier5 → adversarial
```

### Design notes

- The benchmark keeps **only aggregate statistics** from this source for
  reproducibility; raw traces and large processed samples are intentionally
  excluded from the repo.
- Task design emphasizes **longer trajectories** (≥10 tool calls per task),
  **explicit recovery** after failed tool calls, and **multi-tool behavior**
  (≥3 distinct tool families per tier-3+ task) — all three properties are
  direct consequences of the Hermes trajectory-shape distribution.

---

## 3. Internal personal-agent use-case corpus

In addition to the public HF agent-trace datasets and the Hermes aggregate,
ClawBench sources a proprietary scenario corpus of **72 queries** across
**12 primary scenarios** and **139 atomic capabilities**. This corpus is not
a public dataset; we only reproduce the derived scenario weights and
difficulty bands here.

### Corpus summary

```
query_total              72
primary_scenarios        12
secondary_scenarios      55
atomic_capabilities      139

difficulty_distribution
  l1 (simple, single-tool)        22 queries  (30.6%)
  l2 (multi-step, typed tools)    39 queries  (54.2%)
  l3 (open-ended, recovery)       11 queries  (15.3%)
```

### Design principles

1. **MECE atomic capabilities** — each query exercises a non-overlapping
   subset of the 139-capability taxonomy.
2. **Parameterized case expansion** — each base query has clear and
   ambiguous prompt variants.
3. **Dual-channel delivery judging** — pass/partial/fail outcomes tracked
   separately from run-level scores.

### Scenario catalog (with ClawBench query weights)

These scenario names and weights are the source of truth for the
`SCENARIO_WEIGHT_DEFAULTS` table in
[`clawbench/query_catalog.py`](../clawbench/query_catalog.py):

| Scenario | Query count | Weight | Difficulty (l1 / l2 / l3) |
|---|---:|---:|---|
| `file_system_ops` | 8 | 0.13 | 4 / 4 / 0 |
| `multi_step_compound` | 7 | 0.12 | 0 / 0 / 7 |
| `data_processing_analysis` | 8 | 0.11 | 2 / 6 / 0 |
| `web_info_ops` | 6 | 0.10 | 2 / 3 / 1 |
| `coding_dev_assist` | 7 | 0.09 | 3 / 4 / 0 |
| `communication_messaging` | 5 | 0.09 | 0 / 5 / 0 |
| `calendar_reminders` | 5 | 0.08 | 3 / 2 / 0 |
| `skill_calling` | 4 | 0.07 | 0 / 4 / 0 |
| `personal_life_assistant` | 5 | 0.06 | 4 / 1 / 0 |
| `context_continuation` | 7 | 0.05 | 0 / 5 / 2 |
| `error_boundary_cases` | 6 | 0.05 | 3 / 2 / 1 |
| `system_capabilities` | 4 | 0.05 | 1 / 3 / 0 |

### v0.5 additions (beyond the internal corpus)

For v0.5, ClawBench adds eight additional high-frequency personal-agent
scenarios that are not in the original sourced corpus. These are defined
directly in `query_catalog.SCENARIO_WEIGHT_DEFAULTS`:

```
privacy_pii_handling                 0.04
personal_financial_hygiene           0.03
travel_logistics_under_uncertainty   0.03
social_coordination                  0.02
personal_knowledge_base              0.02
health_wellness_tracking             0.01
account_security_hygiene             0.01
multimodal_understanding             0.00   (placeholder, not yet in corpus)
```

---

## 4. How the sources map onto ClawBench's design

| Design decision | Driven by |
|---|---|
| **Tier 1 → 5 difficulty ladder** | Hermes avg/max turn distribution (24.3 avg, 54 max) and the internal corpus difficulty bands (l1/l2/l3) |
| **Task family mix** (coding / repo / browser / tools / multi_tool / adversarial) | Hermes category distribution (see §2 table) |
| **Minimum tool diversity per task** (3+ families for tier-3+) | Hermes `tool_diversity_per_task: 3-6` observation |
| **Multi-turn task design** (≥2 user turns for tier-2+) | Hermes `avg_turns: 24.3` (implies sustained multi-turn dialogue) |
| **Explicit recovery expectations** (trajectory axis rewards recovery) | Pi sessions show frequent failed-tool-call → retry patterns |
| **Browser task count** (2 tasks in the public suite) | Hermes `browser_automation` at 11.5% of all sessions |
| **`SCENARIO_WEIGHT_DEFAULTS`** (query weights in `query_catalog.py`) | Internal corpus §3 weights, verified against Hermes category frequencies |
| **Query difficulty tags** (`l1` / `l2` / `l3` on each task) | Internal corpus difficulty bands |
| **Clear vs ambiguous prompt variants** | Internal corpus §3 design principle: "parameterized case expansion" |
| **Adversarial tier-5 tasks** (contradictory requirements, hallucination resistance, graceful refusal) | Edge cases observed in Pi sessions + Hermes failure-mode patterns, not present in the internal corpus |

---

## Provenance and reproducibility notes

- **HF agent-trace datasets** are enumerated from the public
  [`format:agent-traces` filter](https://huggingface.co/datasets?format=format:agent-traces)
  as of 2026-04-10. The row counts above are a point-in-time snapshot; run
  the filter yourself for the current state.
- **Hermes aggregate statistics** are summary numbers only. Raw trace data
  is not redistributed in this repo.
- **Internal corpus** is not a public dataset. Only the derived scenario
  catalog, weights, and difficulty bands are reproduced, because those are
  what directly inform the ClawBench scoring layer.
- **No runtime code path** reads the files in this directory. Everything
  here is design rationale, not data dependency. Deleting this folder will
  not break the harness, scorer, or analyzer — it will only remove the
  audit trail for why the task suite looks the way it does.
