"""Task loading helpers for the ClawBench task corpus."""

from __future__ import annotations

from pathlib import Path

import yaml

from clawbench.query_catalog import apply_query_metadata_overrides
from clawbench.schemas import TaskDefinition

TASKS_DIR = Path(__file__).parent.parent / "tasks"


def load_task(path: Path) -> TaskDefinition:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    data = apply_query_metadata_overrides(data)
    return TaskDefinition(**data)


def load_all_tasks(
    *,
    tasks_dir: Path | None = None,
    tier: str | None = None,
    task_ids: list[str] | None = None,
    scenario: str | None = None,
    artifact_type: str | None = None,
    prompt_variant: str | None = None,
    pool: str | None = None,
    subsets: list[str] | None = None,
    capabilities: list[str] | None = None,
    official_only: bool = False,
) -> list[TaskDefinition]:
    root = tasks_dir or TASKS_DIR
    tasks: list[TaskDefinition] = []
    requested_subsets = {item.lower() for item in (subsets or [])}
    requested_capabilities = {item.lower() for item in (capabilities or [])}
    tier_roots = sorted(path for path in root.glob("tier*") if path.is_dir())
    search_roots = tier_roots or [root]
    for search_root in search_roots:
        for yaml_path in sorted(search_root.rglob("*.yaml")):
            if yaml_path.name.startswith("_"):
                continue
            task = load_task(yaml_path)
            if tier and task.tier.value != tier:
                continue
            if task_ids and task.id not in task_ids:
                continue
            if scenario and (task.scenario is None or task.scenario.value != scenario):
                continue
            if artifact_type and (task.artifact_type is None or task.artifact_type.value != artifact_type):
                continue
            if prompt_variant and prompt_variant not in {variant.value for variant in task.prompt_variants}:
                continue
            if pool and task.pool.value != pool:
                continue
            if official_only and not task.official:
                continue
            if requested_subsets and not requested_subsets.intersection(subset.value for subset in task.subsets):
                continue
            if requested_capabilities and not requested_capabilities.intersection(
                capability.value for capability in task.capabilities
            ):
                continue
            tasks.append(task)
    return tasks


def get_assets_dir() -> Path:
    return TASKS_DIR / "assets"
