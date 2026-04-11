# ClawBench 100-Task Expansion Plan

## Goal

Expand ClawBench from 20 tasks to 100 tasks. Cover all 72 queries from the
基础使用场景测试集 sheet at least loosely. Add new high-frequency personal-agent
scenarios that the sheet does not capture. Make every task vague-prompted,
multi-step, and verifiable through deterministic execution checks.

## Core Authoring Rules (apply to every new task)

1. **Vague user prompt.** The user message should sound like a real human at
   the end of a long day, not a labeled rubric. No numbered steps. No
   parameter lists. No "do all of the following". The agent must discover
   structure from the workspace.
2. **Hidden requirements.** All structure (file names, output schemas, time
   windows, priority rules) lives in the workspace, not the prompt.
3. **Multi-stage.** Every new task is at minimum 4 distinct phases:
   discover → plan → act → verify. Tier 4 tasks add a recovery or
   reconciliation phase.
4. **Frontier separators.** Every task must have at least one design element
   that bunches weak agents and separates strong ones: dedupe, timezone math,
   corrupt input, mutually exclusive constraints, ambiguity that requires
   asking or grounding, or cross-stage state passing.
5. **Sandboxed.** No real external sends. Email/chat/calendar/cron live in
   workspace files or the OpenClaw test gateway.
6. **Verifiable.** Every task ships with execution_checks scripts that
   deterministically pass or fail. No LLM judges in the primary path.
7. **No fabrication tolerance.** Where the agent could hallucinate, the
   verifier explicitly checks grounding (e.g., summary cites real event_ids,
   prices match real source data, contacts resolved from real records).

## Task Distribution Across 100 Tasks

| Scenario | Tasks | Existing | New |
|---|---:|---:|---:|
| `file_system_ops` | 8 | 0 | 8 |
| `web_info_ops` | 7 | 2 | 5 |
| `calendar_reminders` | 6 | 0 | 6 |
| `communication_messaging` | 8 | 0 | 8 |
| `data_processing_analysis` | 9 | 2 | 7 |
| `coding_dev_assist` | 9 | 9 | 0 |
| `personal_life_assistant` | 7 | 0 | 7 |
| `multi_step_compound` | 8 | 3 | 5 |
| `context_continuation` | 7 | 1 | 6 |
| `error_boundary_cases` | 7 | 2 | 5 |
| `skill_calling` | 7 | 0 | 7 |
| `system_capabilities` | 5 | 1 | 4 |
| `privacy_pii_handling` (NEW) | 4 | 0 | 4 |
| `personal_financial_hygiene` (NEW) | 3 | 0 | 3 |
| `travel_logistics_under_uncertainty` (NEW) | 3 | 0 | 3 |
| `social_coordination` (NEW) | 2 | 0 | 2 |
| **Total** | **100** | **20** | **80** |

## Tier Distribution

| Tier | Existing | Target | Rationale |
|---|---:|---:|---|
| Tier 1 (single capability, easy) | 3 | 12 | Calibration floor |
| Tier 2 (intermediate, 2-3 capabilities) | 5 | 28 | Bulk of personal-agent surface |
| Tier 3 (multi-stage, 4+ capabilities) | 5 | 32 | Where most differentiation lives |
| Tier 4 (frontier, multi-phase, recovery) | 4 | 20 | Premium frontier signal |
| Tier 5 (adversarial, edge cases) | 3 | 8 | Safety and robustness |

## Why Add 4 New Scenarios Beyond the Test Sheet

The test sheet's 12 scenarios cover canonical personal-agent surface, but
omit four classes of high-frequency real-world tasks that production
personal agents must handle:

1. **`privacy_pii_handling`** — redacting personal info from documents
   before sharing, identifying sensitive data leakage in screenshots and
   uploads, sandboxing credentials. Personal agents touch PII constantly.

2. **`personal_financial_hygiene`** — budget tracking, expense categorization,
   subscription auditing, receipt parsing. Not investment advice (prohibited)
   but everyday personal-finance hygiene that agents are routinely asked
   to help with.

3. **`travel_logistics_under_uncertainty`** — flight delays, replanning
   under cancellations, multi-leg booking constraints, time-zone aware
   reminders. The "uncertainty" axis (things going wrong mid-trip) is
   missing from the test sheet's calendar/reminder coverage.

4. **`social_coordination`** — splitting bills, scheduling with multiple
   humans, RSVPing on behalf of user, group decisions. These require
   careful constraint-satisfaction and tactful drafting.

Each new scenario contributes a small but non-trivial weight (1–4%).

## The 100 Tasks (by scenario)

Naming convention: `{tier}-{scenario_short}-{descriptor}.yaml`.
"V" marks tasks already authored or in progress at time of writing.

### file_system_ops (8 tasks)

- t1-fs-quick-note         L1 — vague "jot down what I just said" with formatting inferred from context
- t2-fs-find-that-thing    L2 — fuzzy file recall ("the spreadsheet I worked on last month, with the budget stuff")
- t2-fs-cleanup-downloads  L2 — vague "tidy up my downloads" with hidden retention rules
- t2-fs-photo-rename       L2 — batch rename with EXIF date extraction and conflict handling
- t3-fs-incident-bundle    L3 — V — incident assembly with dedupe, DST, corrupt skip
- t3-fs-archive-rotation   L3 — vague "archive last quarter and free up space" with retention policy
- t4-fs-recovery-from-mess L4 — partial-failure recovery: previous agent left workspace half-organized
- t4-fs-cross-volume-sync  L4 — sync state across two simulated drives with conflict resolution

### web_info_ops (7 tasks)

- t2-web-quick-fact        L2 — V — Q-WEB-02 style "what's the weather and the dollar today"
- t2-web-research-note     L2 — V — t4 already covers research-and-code; this is research-only
- t2-web-table-extract     L2 — table extraction to CSV with header inference and unit normalization
- t3-web-price-compare     L3 — multi-source price comparison with seller reputation weighting
- t3-web-form-debug        L3 — V — t2-browser-form-fix
- t3-web-research-and-cite L3 — research with mandatory citation and grounding check
- t4-web-deep-dive         L4 — multi-hop research with contradicting sources reconciliation

### calendar_reminders (6 tasks)

- t1-cal-quick-reminder    L1 — vague "remind me later" with implicit time inference
- t2-cal-create-event      L2 — natural-language event creation with attendee resolution
- t2-cal-recurring-routine L2 — recurring rule from natural-language description
- t3-cal-conflict-resolver L3 — V — priority-based conflict resolution with DST and eviction trace
- t3-cal-reschedule-cascade L3 — one cancellation triggers reschedule cascade across linked events
- t4-cal-multi-tz-coord    L4 — multi-timezone meeting coordination with constraint solver

### communication_messaging (8 tasks)

- t2-msg-send-update       L2 — vague "let the team know I'm running late" with channel and contact resolution
- t2-msg-summarize-thread  L2 — summarize a long thread with action-item extraction
- t2-msg-write-email       L2 — formal email from sparse bullet points
- t3-msg-inbox-triage      L3 — classify, prioritize, draft replies for urgent items
- t3-msg-followup-loop     L3 — track unanswered messages and draft follow-ups with context
- t3-msg-newsletter-purge  L3 — bulk unsubscribe planner with allowlist exceptions
- t4-msg-multilingual-thread L4 — thread spanning EN/中文 with consistent tone preservation
- t4-msg-conflict-mediation L4 — drafting a tactful response to a tense thread

### data_processing_analysis (9 tasks)

- t2-data-monthly-aggregate L2 — Excel-style monthly rollup with structured output
- t2-data-format-convert    L2 — JSON↔CSV↔YAML with type preservation
- t2-data-clean-and-dedupe  L2 — clean dirty data with audit log of changes
- t3-data-pipeline-report   L3 — V — existing
- t3-data-multifile-merge   L3 — merge N CSVs with schema reconciliation
- t3-data-pivot-and-chart   L3 — pivot table generation and chart export
- t3-data-sql-query         L3 — natural-language to SQL with result verification
- t4-data-anomaly-investigate L4 — detect, explain, and remediate anomalies in time-series data
- t4-data-cross-source-recon L4 — reconcile discrepancies between two sources of truth

### coding_dev_assist (9 tasks — keep existing)

All existing t1/t2/t3 coding tasks remain. Reframing 1-2 of them to be more
user-facing (e.g. PNG→JPG batch script) is a future iteration.

### personal_life_assistant (7 tasks)

- t1-life-translate         L1 — translation with tone preservation
- t2-life-recipe-from-fridge L2 — constraint-based recipe selection (dietary, ingredients, time)
- t2-life-package-tracker   L2 — track multiple packages and produce a digest
- t2-life-unit-convert      L2 — multi-unit conversion with currency lookup
- t3-life-personal-shopper  L3 — shopping list build from sparse goals + budget
- t3-life-letter-draft      L3 — formal letter from emotional bullet points
- t4-life-trip-plan         L4 — multi-day trip plan with constraints and grounding

### multi_step_compound (8 tasks)

- t3-multi-research-to-md   L3 — research → structured markdown report
- t3-multi-scrape-analyze   L3 — scrape → analyze → chart pipeline
- t3-multi-email-cal-reply  L3 — read inbox → create calendar entry → reply
- t3-multi-download-summarize L3 — download → summarize → forward
- t3-feature-export         L3 — V — existing
- t3-data-pipeline-report   L3 — V — existing
- t3-monitoring-automation  L3 — V — existing
- t4-multi-conditional-branch L4 — task with conditional branches based on file existence

### context_continuation (7 tasks)

- t2-ctx-pronoun-resolve    L2 — multi-turn with pronouns and ellipsis
- t2-ctx-preference-recall  L2 — recall stated preferences in later turn
- t3-ctx-task-resume        L3 — resume yesterday's half-finished work from memory
- t3-ctx-correction-chain   L3 — multi-turn corrections to a single output
- t3-ctx-multitask-switch   L3 — interrupt current task, do another, return
- t4-ctx-long-recall        L4 — recall fact from 20 turns earlier
- t4-memory-recall-continuation L4 — V — existing

### error_boundary_cases (7 tasks)

- t1-err-resource-missing   L1 — graceful handling of missing file/URL
- t2-err-permission-denied  L2 — graceful refusal on protected paths
- t2-err-instruction-ambig  L2 — ask vs guess on ambiguous request
- t3-err-tool-failure       L3 — primary tool fails, agent must use fallback
- t3-err-mid-task-interrupt L3 — recover from simulated interruption
- t5-impossible-graceful-fail L5 — V — existing
- t5-hallucination-resistant-evidence L5 — V — existing

### skill_calling (7 tasks)

- t2-skill-excel-rollup     L2 — Excel skill: read sheet, compute, write new sheet
- t2-skill-pdf-merge        L2 — PDF skill: merge, extract pages, page count
- t2-skill-word-memo        L2 — Word skill: structured memo with formatting
- t3-skill-ppt-from-md      L3 — PPT skill: generate deck from markdown brief
- t3-skill-pdf-extract-table L3 — PDF skill: extract tabular data into CSV
- t4-skill-quarterly-bundle L4 — orchestrate Excel + PPT + PDF + Word for one report
- t4-skill-cross-format     L4 — convert between formats with structure preservation

### system_capabilities (5 tasks)

- t2-sys-memory-roundtrip   L2 — write to memory, recall in next session
- t2-sys-image-generate     L2 — image generation with constraint adherence
- t3-sys-html-preview       L3 — generate HTML dashboard, preview, verify rendering
- t3-sys-automation-set     L3 — create cron + verify execution
- t4-sys-multi-skill-orchestrate L4 — orchestrate memory + image + automation

### privacy_pii_handling (NEW — 4 tasks)

- t2-priv-redact-doc        L2 — redact PII from a document before sharing
- t3-priv-screenshot-scan   L3 — scan screenshots for sensitive info, produce report
- t3-priv-credential-isolate L3 — detect and isolate credentials accidentally pasted in notes
- t4-priv-leakage-audit     L4 — audit a workspace for PII exposure across many files

### personal_financial_hygiene (NEW — 3 tasks)

- t2-fin-receipt-parse      L2 — parse receipts from photos/PDFs into expense log
- t3-fin-subscription-audit L3 — find unused subscriptions in transaction history
- t3-fin-budget-monthly     L3 — compute monthly budget vs actual with category drill-down

### travel_logistics_under_uncertainty (NEW — 3 tasks)

- t3-travel-replan-delay    L3 — replan an itinerary after a flight delay
- t3-travel-multi-leg       L3 — multi-leg trip with timezone-aware reminders
- t4-travel-recovery        L4 — full recovery from a major cancellation event

### social_coordination (NEW — 2 tasks)

- t3-social-bill-split      L3 — bill split with itemized contributions and edge cases
- t4-social-group-meet      L4 — coordinate a meeting time across N people with constraints

## Implementation Phasing

### Phase 1 (current PR): Foundation
- Add new scenario domains to schema (DONE)
- Update scenario weights (DONE)
- Author this plan (DONE)
- Author 20 high-quality YAML files spanning all new scenarios

### Phase 2: Asset packs
- Build asset packs for the 20 Phase 1 tasks
- Build verifier scripts for each task

### Phase 3: Bulk authoring
- Author the remaining 60 task YAML files following the templates
- Build remaining asset packs and verifiers
- Update query_catalog.py with metadata for all 100 tasks

### Phase 4: Calibration
- Run 5 frontier models against the 100-task suite
- Identify tasks with zero discrimination (all models pass or all fail) and rewrite
- Tune scenario weights based on observed score variance

### Phase 5: Lock and rotate
- Move 30% of tasks to `official_hidden` pool
- Set up rotation schedule for hidden variants
