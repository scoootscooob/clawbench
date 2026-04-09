# ClawBench v0.4 Spec

## Purpose

ClawBench v0.4 upgrades ClawBench from a strong OpenClaw-native coding benchmark into a more robust frontier-agent evaluation system.

The design goals are:

1. Keep deterministic outcome verification as the primary source of truth.
2. Increase model differentiation without rewarding style over substance.
3. Separate capability, reliability, efficiency, and semantic quality instead of collapsing them too early into one scalar.
4. Reduce overfitting pressure with public dev tasks, hidden official tasks, and rotating variants.
5. Prepare the benchmark for eventual cross-harness evaluation through a canonical task schema and adapter boundary.

## Non-Goals

- Replacing execution-based grading with LLM judging.
- Turning every task into an open-ended knowledge-work artifact task.
- Shipping a cross-harness benchmark in a single release.

## Principles

- Deterministic first: if a task can be verified by execution, hidden tests, trace checks, or structural comparison, do that.
- Judges only for irreducibly semantic residue.
- Public methodology, partially private tasks.
- Multiple score surfaces instead of one opaque leaderboard number.
- Reliability matters as much as one-shot brilliance.
- Failure modes are benchmark outputs, not just debugging metadata.

## Benchmark Structure

ClawBench v0.4 has three benchmark layers.

### Layer A: Core Deterministic Evaluation

This is the primary leaderboard layer.

- Binary task pass/fail from deterministic verification.
- Partial credit from deterministic sub-assertions only.
- Applies to coding, browser, cron, delegation, memory, and adversarial tasks.

### Layer B: Process and Robustness Evaluation

This measures whether the agent worked in a way we actually want.

- Read-before-write
- Verification-after-mutation
- Recovery after failures
- Tool-family fit
- Unsafe behavior penalties
- Failure taxonomy

This remains secondary to hard completion, but it is still first-class and reported separately.

### Layer C: Semantic Quality Evaluation

This is restricted to tasks where execution cannot fully capture quality.

Examples:

- Architecture briefs
- Incident summaries
- Evidence-backed research memos
- Code review writeups

Semantic quality never rescues failed completion.

## Task Pools

Tasks are split into four pools.

### `public_dev`

- Public
- Stable
- Used for local debugging, examples, and adapter bring-up
- Not used for official leaderboard ranking

### `official_hidden`

- Private task bodies and/or hidden variants
- Used for official leaderboard scoring
- Rotated periodically

### `consensus`

- Highly audited subset with extremely trustworthy verification
- Lower ambiguity, lower noise
- Used for regression tracking and judge calibration

### `hard`

- Frontier-separating subset
- Keeps headroom as models improve
- Preferred public-facing score for serious comparisons

## Task Taxonomy

Current tiering stays, but v0.4 adds explicit capability tags.

Each task will declare:

- `tier`
- `family`
- `surface`
- `capabilities`
- `pool`
- `variant_group`
- `official`
- `semantic_judge`

Recommended capability tags:

- `bugfix`
- `refactor`
- `test_authoring`
- `multifile_reasoning`
- `browser_debugging`
- `structured_output`
- `memory_continuation`
- `delegation`
- `tool_composition`
- `research_synthesis`
- `graceful_refusal`
- `spec_revision`
- `cross_repo_change`
- `automation`

## Official Run Policy

- Official scores require at least 3 runs per task.
- Report `pass@1`, pass rate, `pass^k`, variance, and worst-of-n reliability.
- Official runs must use fixed benchmark-owned time, tool, and token budgets.
- Public dev runs may be single-run and lower budget.

## Verification Policy

### Allowed Primary Verifiers

- Hidden unit and integration tests
- Deterministic verifier scripts
- Structured file assertions
- Exact JSON or normalized JSON comparison
- Expected stdout or structured output comparison
- DOM assertions
- Network-trace assertions
- Memory state assertions
- Cron state assertions
- Gateway state assertions

### Disallowed Primary Verifiers

- File existence alone for coding tasks
- Transcript-only “seems done” checks
- Holistic LLM judging when deterministic verification is possible

### Verification Tiers

Each task verifier should be classified as one of:

- `exact`
- `normalized_structural`
- `state_transition`
- `execution`
- `trace_based`
- `semantic`

`semantic` should be the exception, not the default.

## Browser Verification

Browser tasks should move closer to WebArena-Verified style evaluation.

Required additions:

- Capture browser/network traces per run.
- Allow verifiers to assert requests, methods, status codes, routes, parameters, and final DOM state.
- Prefer network and state assertions over fragile text matching when possible.
- Preserve local deterministic services only; no live public sites in official runs.

## Failure Taxonomy

Every failed run should be assigned a primary failure mode.

Initial taxonomy:

- `graceful_refusal`
- `hallucinated_completion`
- `repeated_error_loop`
- `tool_misuse`
- `unsafe_mutation`
- `verification_skipped`
- `state_regression`
- `memory_miss`
- `delegation_failed`
- `browser_navigation_failure`
- `environment_unavailable`
- `timeout`
- `reward_hack_suspected`

This should be generated deterministically where possible, with a manual review path for suspicious runs.

## Efficiency Metrics

ClawBench v0.4 should report:

- `median_latency_ms`
- `p95_latency_ms`
- `input_tokens`
- `output_tokens`
- `reasoning_tokens` if available
- `total_tokens`
- `estimated_cost_usd`
- `cost_per_pass`
- `tokens_per_pass`

These should appear beside capability metrics, not buried in raw logs.

## Reliability Metrics

We keep run repetition but expand reporting.

Per task:

- `pass@1`
- `pass_rate`
- `pass^k`
- `worst_of_n`
- `stddev`
- `variance_score`

Per benchmark:

- mean over tasks for the above
- by-tier and by-capability breakdowns

Worst-of-n should be especially visible for adversarial and safety-sensitive tasks.

## Scoring Model

v0.4 should stop over-compressing everything into one number.

### Primary Surfaces

- `HardSuccess`
- `ProcessQuality`
- `Reliability`
- `Efficiency`
- `FailureProfile`
- `SemanticQuality` where applicable

### Suggested Presentation

Primary leaderboard columns:

- `HardSuccess`
- `Reliability`
- `Median Latency`
- `Cost per Pass`
- `Hard subset`
- `Consensus subset`

Secondary detail panels:

- Tier breakdown
- Capability breakdown
- Failure-mode histogram
- Process-quality metrics
- Semantic-quality metrics

### Single Composite Score

If a single score is required for ranking, use it as a display convenience only.

Recommended composite:

`official_score = 0.6 * hard_success + 0.2 * reliability + 0.1 * process_quality + 0.1 * efficiency_score`

Constraints:

- If deterministic completion fails, semantic quality does not contribute.
- If a run is flagged `unsafe_mutation` or `reward_hack_suspected`, the run score is zeroed or quarantined.
- Composite score should not be the only published output.

## Semantic Judge Policy

Semantic judges are allowed only for tasks with `semantic_judge.enabled = true`.

### Where To Use Judges

- architecture brief quality
- evidence memo quality
- incident report quality
- code review quality
- research synthesis quality

### Where Not To Use Judges

- bugfix correctness
- browser success
- cron state
- file generation correctness
- exact-output CLI tasks
- test-authoring correctness

### Judge Design

- Prefer 3 judges from different families.
- Blind to model and harness identity.
- Rubric-based scoring only.
- Score per criterion, not one global impression.
- Randomize candidate ordering.
- Log criterion-level decisions for auditability.
- Cap semantic contribution to a minority share of the task score.

### Judge Gating

Semantic judging only runs if:

- the deterministic completion floor is met, or
- the task family is explicitly semantic-first

## Anti-Gaming Design

ClawBench v0.4 should adopt:

- public dev set + hidden official set
- hidden variants within task families
- periodic rotation
- canary strings in private tasks
- verifier hardening reviews
- suspicious-run review pipeline

For private tasks, do not expose exact hidden assertions in public result payloads.

## Canonical Task Schema

v0.4 should start separating canonical task intent from OpenClaw execution details.

### Canonical Layer

- task metadata
- goal
- assets
- verifier contract
- budgets
- interaction policy
- expected deliverable types

### OpenClaw Adapter Layer

- user turn generation
- tool-family normalization
- session and workspace lifecycle
- browser connection details
- memory and cron integration

This lets ClawBench remain OpenClaw-first now while making future cross-harness support feasible.

## Codebase Changes

### `clawbench/schemas.py`

Add:

- `TaskPool`
- `CapabilityTag`
- `VerifierKind`
- `FailureMode`
- `EfficiencyResult`
- `SemanticJudgeConfig`
- `TaskVariant`

Extend `TaskDefinition` with:

- `capabilities`
- `pool`
- `variant_group`
- `official`
- `semantic_judge`

### `clawbench/environment.py`

Add:

- verifier classification metadata
- trace-based verifier support
- normalized JSON / structured diff helpers
- failure-mode hints from verifier outcomes

### `clawbench/trajectory.py`

Add:

- explicit verification-gap detection
- reward-hack suspicion heuristics
- richer browser trace scoring hooks
- deterministic failure-mode inference from traces

### `clawbench/scorer.py`

Refactor to output:

- `hard_success`
- `process_quality`
- `semantic_quality`
- `efficiency_score`
- `failure_mode`

Completion remains the primary gate.

### `clawbench/stats.py`

Add aggregation for:

- worst-of-n
- cost and token efficiency
- per-capability breakdowns
- public-dev vs official-hidden splits
- consensus vs hard subset reporting

### `clawbench/harness.py`

Add:

- public/hidden pool selection
- hidden variant resolution
- token/cost logging
- trace capture support
- suspicious-run quarantine hooks

### `clawbench/client.py`

Add:

- normalized usage extraction if the gateway exposes token and cost data
- browser trace export hooks where supported

### `clawbench/tasks.py`

Add:

- pool filtering
- capability filtering
- variant expansion
- hidden-manifest loading

### `app.py` and `clawbench/render.py`

Update UI to show:

- hard success
- reliability
- efficiency
- failure profile
- consensus / hard subset

## Task Roadmap

### Keep and Harden

- browser repair
- memory continuation
- delegation repair
- contradictory requirements
- hallucination-resistant evidence

### Add in v0.4

- hidden regression bugfix families
- browser tasks with network-trace verification
- tool-composition tasks with no obvious single-tool route
- ambiguity-resolution tasks with structured intermediate evidence
- semantic tasks with deterministic floor + judge overlay

### Remove or Rewrite

Rewrite any task whose success is still dominated by:

- brittle substring checks
- transcript cosmetics
- public fixture memorization
- one obvious happy-path implementation

## Phased Implementation

### Phase 1

- Add pools, variants, capabilities, failure taxonomy, and efficiency logging.
- Add consensus and hard subsets.
- Keep deterministic-only official scoring.

### Phase 2

- Add trace-based browser verification.
- Add worst-of-n reliability reporting.
- Add suspicious-run audit pipeline.

### Phase 3

- Add semantic judge support for a small semantic subset.
- Calibrate judges against human labels on consensus tasks.

### Phase 4

- Introduce canonical task format and OpenClaw adapter boundary.
- Prepare for cross-harness evaluation.

## Success Criteria for v0.4

ClawBench v0.4 is successful if:

1. Frontier models separate more clearly on hard and reliability metrics than in v0.3.
2. Shared failures are attributable to capability gaps more often than verifier brittleness.
3. Official benchmark results remain reproducible across reruns.
4. Judge-based scores, where used, correlate well with human labels on calibration tasks.
5. Overfitting pressure is reduced by hidden variants and rotation.
