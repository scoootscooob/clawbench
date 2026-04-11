"""Trace ingestion and normalization for rolling benchmark task generation."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from clawbench.releases import HiddenReleaseManifest, build_hidden_release
from clawbench.schemas import CapabilityTag, ScenarioDomain, TaskDefinition, TaskFamily, Transcript
from clawbench.tasks import load_all_tasks


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_task_factory_root() -> Path:
    raw = os.environ.get("CLAWBENCH_TASK_FACTORY_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(".clawbench/task_factory").resolve()


def ensure_task_factory_dirs(root: Path | None = None) -> dict[str, Path]:
    base = (root or get_task_factory_root()).resolve()
    paths = {
        "root": base,
        "traces": base / "traces",
        "seeds": base / "seeds",
        "templates": base / "templates",
        "audits": base / "audits",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


class TraceRecord(BaseModel):
    trace_id: str = ""
    source_kind: str
    privacy_tier: str = "public"
    partner_name: str = ""
    created_at: str = ""
    user_prompt: str = ""
    transcript: Transcript = Field(default_factory=Transcript)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        source_kind: str,
        privacy_tier: str,
        partner_name: str = "",
    ) -> "TraceRecord":
        transcript = payload.get("transcript", {})
        user_prompt = payload.get("user_prompt", "")
        if not user_prompt and isinstance(transcript, dict):
            messages = transcript.get("messages", [])
            for message in messages:
                if message.get("role") == "user" and message.get("text"):
                    user_prompt = str(message["text"])
                    break
        record = cls(
            trace_id=str(payload.get("trace_id", "")),
            source_kind=source_kind,
            privacy_tier=privacy_tier,
            partner_name=partner_name or str(payload.get("partner_name", "")),
            created_at=str(payload.get("created_at", "")),
            user_prompt=user_prompt,
            transcript=Transcript(**transcript) if transcript else Transcript(),
            metadata={k: v for k, v in payload.items() if k not in {"trace_id", "transcript", "user_prompt", "created_at", "partner_name"}},
        )
        if not record.trace_id:
            record.trace_id = stable_id("trace", [record.source_kind, record.user_prompt, record.transcript.assistant_text])
        if not record.created_at:
            record.created_at = now_utc_iso()
        return record


class TaskSeedRecord(BaseModel):
    seed_id: str
    trace_id: str
    source_kind: str
    privacy_tier: str
    partner_name: str = ""
    created_at: str
    user_prompt: str
    family: str
    scenario: str = ""
    capabilities: list[str] = Field(default_factory=list)
    tool_families: list[str] = Field(default_factory=list)
    deliverable_hint: str = ""
    ambiguity_signals: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskTemplateRecord(BaseModel):
    template_id: str
    seed_id: str
    source_kind: str
    privacy_tier: str
    created_at: str
    family: str
    scenario: str = ""
    capabilities: list[str] = Field(default_factory=list)
    tool_families: list[str] = Field(default_factory=list)
    prompt_skeleton: str
    verifier_hint: str = ""
    recommended_source_task_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SimilarityFinding(BaseModel):
    left_id: str
    left_kind: str
    right_id: str
    right_kind: str
    score: float
    shared_family: bool = False
    shared_scenario: bool = False
    shared_capabilities: list[str] = Field(default_factory=list)
    overlap_tokens: list[str] = Field(default_factory=list)


class ContaminationAuditReport(BaseModel):
    created_at: str
    threshold: float
    template_count: int = 0
    public_task_count: int = 0
    hidden_task_count: int = 0
    findings: list[SimilarityFinding] = Field(default_factory=list)
    report_path: str = ""


def stable_id(prefix: str, parts: list[str]) -> str:
    payload = "||".join(part.strip() for part in parts if part.strip())
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def load_trace_payloads(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    if raw[0] == "[":
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("Trace input JSON must be a list of objects.")
        return [item for item in data if isinstance(item, dict)]
    records: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        if isinstance(item, dict):
            records.append(item)
    return records


def ingest_trace_file(
    *,
    input_path: Path,
    source_kind: str,
    privacy_tier: str,
    partner_name: str = "",
    factory_root: Path | None = None,
    emit_templates: bool = True,
) -> tuple[list[TraceRecord], list[TaskSeedRecord], list[TaskTemplateRecord]]:
    dirs = ensure_task_factory_dirs(factory_root)
    payloads = load_trace_payloads(input_path)
    source_tasks = load_all_tasks(pool="public_dev")
    traces: list[TraceRecord] = []
    seeds: list[TaskSeedRecord] = []
    templates: list[TaskTemplateRecord] = []
    for payload in payloads:
        trace = TraceRecord.from_payload(
            payload,
            source_kind=source_kind,
            privacy_tier=privacy_tier,
            partner_name=partner_name,
        )
        seed = derive_seed_from_trace(trace)
        traces.append(trace)
        seeds.append(seed)
        write_json(dirs["traces"] / f"{trace.trace_id}.json", trace.model_dump(mode="json"))
        write_json(dirs["seeds"] / f"{seed.seed_id}.json", seed.model_dump(mode="json"))
        if emit_templates:
            template = derive_template_from_seed(seed, source_tasks=source_tasks)
            templates.append(template)
            write_json(dirs["templates"] / f"{template.template_id}.json", template.model_dump(mode="json"))
    return traces, seeds, templates


def derive_seed_from_trace(trace: TraceRecord) -> TaskSeedRecord:
    tool_names = [call.name for call in trace.transcript.tool_call_sequence]
    tool_families = sorted({infer_tool_family(name) for name in tool_names if infer_tool_family(name)})
    family = infer_task_family(trace.user_prompt, tool_families)
    scenario = infer_scenario(trace.user_prompt, family, tool_families)
    capabilities = infer_capabilities(trace.user_prompt, tool_families)
    deliverable_hint = infer_deliverable_hint(trace.user_prompt)
    ambiguity_signals = detect_ambiguity_signals(trace.user_prompt)
    seed_id = stable_id(
        "seed",
        [trace.trace_id, trace.user_prompt, family, scenario, ",".join(capabilities), ",".join(tool_families)],
    )
    return TaskSeedRecord(
        seed_id=seed_id,
        trace_id=trace.trace_id,
        source_kind=trace.source_kind,
        privacy_tier=trace.privacy_tier,
        partner_name=trace.partner_name,
        created_at=trace.created_at,
        user_prompt=trace.user_prompt,
        family=family,
        scenario=scenario,
        capabilities=capabilities,
        tool_families=tool_families,
        deliverable_hint=deliverable_hint,
        ambiguity_signals=ambiguity_signals,
        metadata=trace.metadata,
    )


def derive_template_from_seed(seed: TaskSeedRecord, *, source_tasks: list[TaskDefinition] | None = None) -> TaskTemplateRecord:
    notes: list[str] = []
    if seed.privacy_tier != "public":
        notes.append("Derived from restricted/private trace material; publish only rewritten variants.")
    if seed.ambiguity_signals:
        notes.append(f"Preserve ambiguity pattern: {', '.join(seed.ambiguity_signals)}")
    recommended_source_task_ids = (
        [task.id for task in rank_source_tasks_for_seed(seed, source_tasks or [])[:3]]
        if source_tasks
        else []
    )
    return TaskTemplateRecord(
        template_id=stable_id("tmpl", [seed.seed_id, seed.family, seed.scenario, ",".join(seed.capabilities)]),
        seed_id=seed.seed_id,
        source_kind=seed.source_kind,
        privacy_tier=seed.privacy_tier,
        created_at=now_utc_iso(),
        family=seed.family,
        scenario=seed.scenario,
        capabilities=seed.capabilities,
        tool_families=seed.tool_families,
        prompt_skeleton=build_prompt_skeleton(seed),
        verifier_hint=infer_verifier_hint(seed),
        recommended_source_task_ids=recommended_source_task_ids,
        notes=notes,
    )


def load_template_records(factory_root: Path | None = None) -> list[TaskTemplateRecord]:
    dirs = ensure_task_factory_dirs(factory_root)
    templates: list[TaskTemplateRecord] = []
    for path in sorted(dirs["templates"].glob("*.json")):
        templates.append(TaskTemplateRecord(**json.loads(path.read_text(encoding="utf-8"))))
    return templates


def audit_contamination(
    *,
    threshold: float = 0.72,
    factory_root: Path | None = None,
    include_public_tasks: bool = True,
    include_hidden_tasks: bool = True,
) -> ContaminationAuditReport:
    dirs = ensure_task_factory_dirs(factory_root)
    templates = load_template_records(factory_root)
    public_tasks = load_all_tasks(pool="public_dev") if include_public_tasks else []
    hidden_tasks = load_all_tasks(pool="official_hidden") if include_hidden_tasks else []

    findings: list[SimilarityFinding] = []

    for index, left in enumerate(templates):
        for right in templates[index + 1 :]:
            finding = compare_template_like(left, right, left_kind="template", right_kind="template")
            if finding.score >= threshold:
                findings.append(finding)
        for task in public_tasks:
            finding = compare_template_to_task(left, task, right_kind="public_task")
            if finding.score >= threshold:
                findings.append(finding)
        for task in hidden_tasks:
            finding = compare_template_to_task(left, task, right_kind="hidden_task")
            if finding.score >= threshold:
                findings.append(finding)

    findings.sort(key=lambda item: item.score, reverse=True)
    report = ContaminationAuditReport(
        created_at=now_utc_iso(),
        threshold=threshold,
        template_count=len(templates),
        public_task_count=len(public_tasks),
        hidden_task_count=len(hidden_tasks),
        findings=findings,
    )
    report_path = dirs["audits"] / f"audit_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    report.report_path = str(report_path)
    write_json(report_path, report.model_dump(mode="json"))
    return report


def build_hidden_release_from_templates(
    *,
    release_id: str,
    template_ids: list[str] | None = None,
    max_templates: int = 0,
    factory_root: Path | None = None,
    private_tasks_root: Path | None = None,
    active_release_path: Path | None = None,
    activate: bool = True,
) -> tuple[HiddenReleaseManifest, list[TaskDefinition]]:
    templates = load_template_records(factory_root)
    if template_ids:
        requested = set(template_ids)
        templates = [template for template in templates if template.template_id in requested]
    if max_templates > 0:
        templates = templates[:max_templates]
    if not templates:
        raise ValueError("No templates matched the requested selection.")

    public_tasks = {task.id: task for task in load_all_tasks(pool="public_dev")}
    derived_tasks: list[TaskDefinition] = []
    for template in templates:
        base_task = choose_base_task_for_template(template, public_tasks)
        derived_tasks.append(rewrite_task_from_template(base_task, template, release_id=release_id))

    manifest = build_hidden_release(
        tasks=derived_tasks,
        release_id=release_id,
        private_tasks_root=private_tasks_root,
        activate=activate,
        active_release_path=active_release_path,
    )
    return manifest, derived_tasks


def build_prompt_skeleton(seed: TaskSeedRecord) -> str:
    prompt = seed.user_prompt.strip() or "Complete the requested task using the workspace and available tools."
    prompt = re.sub(r"\s+", " ", prompt)
    if len(prompt) > 220:
        prompt = prompt[:217].rstrip() + "..."
    return prompt


def infer_verifier_hint(seed: TaskSeedRecord) -> str:
    if "browser" in seed.tool_families:
        return "Prefer DOM or trace-based checks."
    if "memory" in seed.tool_families or "automation" in seed.capabilities:
        return "Prefer state-transition verification."
    if seed.family in {TaskFamily.CODING.value, TaskFamily.REPO.value}:
        return "Prefer execution checks with regression tests."
    return "Prefer deterministic file or execution checks."


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def compare_template_like(
    left: TaskTemplateRecord,
    right: TaskTemplateRecord,
    *,
    left_kind: str,
    right_kind: str,
) -> SimilarityFinding:
    left_tokens = tokenize_text(left.prompt_skeleton)
    right_tokens = tokenize_text(right.prompt_skeleton)
    shared_capabilities = sorted(set(left.capabilities).intersection(right.capabilities))
    token_overlap = sorted(left_tokens.intersection(right_tokens))
    score = similarity_score(
        shared_family=left.family == right.family,
        shared_scenario=left.scenario == right.scenario,
        shared_capabilities=shared_capabilities,
        overlap_tokens=token_overlap,
        left_cap_count=len(left.capabilities),
        right_cap_count=len(right.capabilities),
        left_tokens=left_tokens,
        right_tokens=right_tokens,
    )
    return SimilarityFinding(
        left_id=left.template_id,
        left_kind=left_kind,
        right_id=right.template_id,
        right_kind=right_kind,
        score=score,
        shared_family=left.family == right.family,
        shared_scenario=left.scenario == right.scenario,
        shared_capabilities=shared_capabilities,
        overlap_tokens=token_overlap[:12],
    )


def compare_template_to_task(
    template: TaskTemplateRecord,
    task: TaskDefinition,
    *,
    right_kind: str,
) -> SimilarityFinding:
    template_tokens = tokenize_text(template.prompt_skeleton)
    task_prompt = first_task_prompt(task)
    task_tokens = tokenize_text(task_prompt)
    task_capabilities = [capability.value for capability in task.capabilities]
    shared_capabilities = sorted(set(template.capabilities).intersection(task_capabilities))
    token_overlap = sorted(template_tokens.intersection(task_tokens))
    score = similarity_score(
        shared_family=template.family == task.family.value,
        shared_scenario=bool(task.scenario and template.scenario == task.scenario.value),
        shared_capabilities=shared_capabilities,
        overlap_tokens=token_overlap,
        left_cap_count=len(template.capabilities),
        right_cap_count=len(task_capabilities),
        left_tokens=template_tokens,
        right_tokens=task_tokens,
    )
    return SimilarityFinding(
        left_id=template.template_id,
        left_kind="template",
        right_id=task.id,
        right_kind=right_kind,
        score=score,
        shared_family=template.family == task.family.value,
        shared_scenario=bool(task.scenario and template.scenario == task.scenario.value),
        shared_capabilities=shared_capabilities,
        overlap_tokens=token_overlap[:12],
    )


def similarity_score(
    *,
    shared_family: bool,
    shared_scenario: bool,
    shared_capabilities: list[str],
    overlap_tokens: list[str],
    left_cap_count: int,
    right_cap_count: int,
    left_tokens: set[str],
    right_tokens: set[str],
) -> float:
    capability_union = max(1, len(set(shared_capabilities)) + (left_cap_count - len(shared_capabilities)) + (right_cap_count - len(shared_capabilities)))
    capability_score = len(shared_capabilities) / capability_union
    token_union = max(1, len(left_tokens.union(right_tokens)))
    token_score = len(overlap_tokens) / token_union
    score = (
        (0.30 if shared_family else 0.0)
        + (0.25 if shared_scenario else 0.0)
        + 0.25 * capability_score
        + 0.20 * token_score
    )
    return round(min(score, 1.0), 4)


def tokenize_text(text: str) -> set[str]:
    lowered = text.lower()
    tokens = re.findall(r"[a-z0-9_]{4,}", lowered)
    stop = {
        "there",
        "issue",
        "workspace",
        "using",
        "available",
        "tools",
        "local",
        "verify",
        "result",
        "make",
        "needed",
        "changes",
        "project",
        "passes",
        "through",
    }
    return {token for token in tokens if token not in stop}


def first_task_prompt(task: TaskDefinition) -> str:
    if task.user and task.user.turns:
        return task.user.turns[0].message
    if task.phases and task.phases[0].user.turns:
        return task.phases[0].user.turns[0].message
    return task.name


def rank_source_tasks_for_seed(seed: TaskSeedRecord, source_tasks: list[TaskDefinition]) -> list[TaskDefinition]:
    def score(task: TaskDefinition) -> tuple[float, int, int]:
        value = 0.0
        if task.family.value == seed.family:
            value += 3.0
        if task.scenario and task.scenario.value == seed.scenario:
            value += 3.0
        overlap = len(set(seed.capabilities).intersection(capability.value for capability in task.capabilities))
        value += 2.0 * overlap
        if "hard" in {subset.value for subset in task.subsets}:
            value += 0.5
        tier_rank = int(task.tier.value.replace("tier", ""))
        return value, tier_rank, overlap

    ranked = sorted(source_tasks, key=score, reverse=True)
    return [task for task in ranked if score(task)[0] > 0]


def choose_base_task_for_template(template: TaskTemplateRecord, public_tasks: dict[str, TaskDefinition]) -> TaskDefinition:
    for task_id in template.recommended_source_task_ids:
        if task_id in public_tasks:
            return public_tasks[task_id]
    fallback = next(iter(public_tasks.values()), None)
    if fallback is None:
        raise ValueError("No public tasks available to use as template bases.")
    return fallback


def rewrite_task_from_template(
    base_task: TaskDefinition,
    template: TaskTemplateRecord,
    *,
    release_id: str,
) -> TaskDefinition:
    task = base_task.model_copy(deep=True)
    task.template_id = template.template_id
    task.release_id = release_id
    task.source_kind = template.source_kind
    task.privacy_tier = template.privacy_tier
    task.freshness_epoch = release_id
    task.contamination_risk = infer_contamination_risk(template.source_kind, template.privacy_tier)
    task.provenance_ids = [template.seed_id, template.template_id, base_task.id]
    task.similarity_hash = stable_id("sim", [template.template_id, base_task.id, template.prompt_skeleton])
    task.first_used_at = now_utc_iso()
    task.variant_group = base_task.id
    task.variant_id = f"{release_id}-{template.template_id[-6:]}"
    task.source_dataset = f"trace_template::{template.source_kind}"
    apply_hidden_prompt(task, generate_hidden_prompt(template, base_task))
    return task


def apply_hidden_prompt(task: TaskDefinition, prompt: str) -> None:
    if task.user and task.user.turns:
        task.user.turns[0].message = prompt
        return
    if task.phases and task.phases[0].user.turns:
        task.phases[0].user.turns[0].message = prompt


def generate_hidden_prompt(template: TaskTemplateRecord, base_task: TaskDefinition) -> str:
    if template.family in {TaskFamily.CODING.value, TaskFamily.REPO.value}:
        return "There is an issue somewhere in this workspace. Inspect the relevant files, make the needed changes, and verify the project checks pass."
    if template.family == TaskFamily.BROWSER.value:
        return "A local browser workflow is failing in this workspace. Use the browser to diagnose the issue, fix it, and verify the flow succeeds."
    if template.scenario == ScenarioDomain.DATA_ANALYSIS.value:
        return "Use the workspace inputs to produce the expected analysis artifact and verify the result matches the required output."
    if template.scenario == ScenarioDomain.COMMUNICATION.value:
        return "Work through the local message data, produce the needed communication outcome, and make sure the final result is usable without cleanup."
    if "automation" in template.capabilities:
        return "Set up the requested automation in the local environment and verify that the scheduled or stateful behavior is configured correctly."
    return (
        "Complete the requested workspace task using the available files and tools, then verify the result before you finish."
    )


def infer_contamination_risk(source_kind: str, privacy_tier: str) -> str:
    if source_kind == "hf_open_trace":
        return "high"
    if privacy_tier == "partner_restricted":
        return "low"
    if source_kind == "partner_trace":
        return "low"
    return "medium"


def infer_tool_family(tool_name: str) -> str:
    lowered = tool_name.lower()
    if any(token in lowered for token in ("browser", "playwright", "dom")):
        return "browser"
    if any(token in lowered for token in ("memory", "recall")):
        return "memory"
    if any(token in lowered for token in ("search", "grep", "rg", "find")):
        return "search"
    if any(token in lowered for token in ("exec", "bash", "pytest", "node")):
        return "execute"
    if any(token in lowered for token in ("write", "edit", "patch")):
        return "edit"
    if any(token in lowered for token in ("read", "open", "cat")):
        return "read"
    if any(token in lowered for token in ("cron", "automation")):
        return "automation"
    if any(token in lowered for token in ("delegate", "agent")):
        return "delegate"
    return ""


def infer_task_family(prompt: str, tool_families: list[str]) -> str:
    lowered = prompt.lower()
    if "browser" in tool_families:
        return TaskFamily.BROWSER.value
    if any(token in lowered for token in ("bug", "refactor", "test", "repo", "module", "function", "code")):
        return TaskFamily.CODING.value
    if any(token in lowered for token in ("research", "cite", "find out", "look up", "search")):
        return TaskFamily.TOOLS.value
    if len(tool_families) >= 3:
        return TaskFamily.MULTI_TOOL.value
    return TaskFamily.TOOLS.value


def infer_scenario(prompt: str, family: str, tool_families: list[str]) -> str:
    lowered = prompt.lower()
    if "browser" in tool_families:
        return ScenarioDomain.WEB_INFO_OPS.value
    if any(token in lowered for token in ("calendar", "remind", "schedule")):
        return ScenarioDomain.CALENDAR_REMINDERS.value
    if any(token in lowered for token in ("inbox", "email", "thread", "draft")):
        return ScenarioDomain.COMMUNICATION.value
    if any(token in lowered for token in ("budget", "sql", "report", "csv", "spreadsheet", "analyze")):
        return ScenarioDomain.DATA_ANALYSIS.value
    if family in {TaskFamily.CODING.value, TaskFamily.REPO.value}:
        return ScenarioDomain.CODING_DEV.value
    return ScenarioDomain.MULTI_STEP.value


def infer_capabilities(prompt: str, tool_families: list[str]) -> list[str]:
    lowered = prompt.lower()
    capabilities: list[str] = []
    if any(token in lowered for token in ("bug", "fix", "regression")):
        capabilities.append(CapabilityTag.BUGFIX.value)
    if "refactor" in lowered:
        capabilities.append(CapabilityTag.REFACTOR.value)
    if "test" in lowered:
        capabilities.append(CapabilityTag.TEST_AUTHORING.value)
    if any(token in lowered for token in ("across files", "multifile", "through the files", "repo")):
        capabilities.append(CapabilityTag.MULTIFILE_REASONING.value)
    if "browser" in tool_families:
        capabilities.append(CapabilityTag.BROWSER_DEBUGGING.value)
    if any(token in lowered for token in ("report", "json", "csv", "summary")):
        capabilities.append(CapabilityTag.STRUCTURED_OUTPUT.value)
    if "memory" in tool_families:
        capabilities.append(CapabilityTag.MEMORY_CONTINUATION.value)
    if "delegate" in tool_families:
        capabilities.append(CapabilityTag.DELEGATION.value)
    if len(tool_families) >= 3:
        capabilities.append(CapabilityTag.TOOL_COMPOSITION.value)
    if any(token in lowered for token in ("research", "cite", "source")):
        capabilities.append(CapabilityTag.RESEARCH_SYNTHESIS.value)
    if any(token in lowered for token in ("graceful", "cannot", "impossible", "refuse")):
        capabilities.append(CapabilityTag.GRACEFUL_REFUSAL.value)
    if any(token in lowered for token in ("revise", "contradict", "change requirement")):
        capabilities.append(CapabilityTag.SPEC_REVISION.value)
    if any(token in lowered for token in ("cross-repo", "migration")):
        capabilities.append(CapabilityTag.CROSS_REPO_CHANGE.value)
    if any(token in lowered for token in ("cron", "automation", "monitoring")):
        capabilities.append(CapabilityTag.AUTOMATION.value)
    deduped: list[str] = []
    for capability in capabilities:
        if capability not in deduped:
            deduped.append(capability)
    return deduped


def infer_deliverable_hint(prompt: str) -> str:
    lowered = prompt.lower()
    if any(token in lowered for token in ("json", "csv", "report", "summary", "brief")):
        return "structured_artifact"
    if any(token in lowered for token in ("fix", "patch", "refactor", "test")):
        return "code_change"
    if any(token in lowered for token in ("schedule", "reminder", "automation")):
        return "state_change"
    return "mixed"


def detect_ambiguity_signals(prompt: str) -> list[str]:
    lowered = prompt.lower()
    signals: list[str] = []
    for phrase in (
        "something is off",
        "looks wrong",
        "figure out why",
        "trace it through",
        "somewhere in",
        "messy",
        "do not break",
        "keep the tests green",
    ):
        if phrase in lowered:
            signals.append(phrase)
    return signals
