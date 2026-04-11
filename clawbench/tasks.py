"""Task loading helpers for the ClawBench task corpus."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from clawbench.query_catalog import apply_query_metadata_overrides
from clawbench.schemas import TaskDefinition


def _resolve_tasks_dir() -> Path:
    """Resolve the tasks directory at import time.

    When ClawBench is run from a source checkout, `tasks/` is a sibling of
    the `clawbench/` package directory. When the package is pip-installed
    (e.g. inside the HF Space Docker image), that sibling relationship no
    longer holds — pip copies only `clawbench/` into site-packages, and
    `tasks/` lives at the Docker WORKDIR instead. This resolver tries a
    series of candidates in order and falls back to the sibling-of-source
    path so source runs stay unaffected.
    """
    # 1. Explicit override via environment variable.
    env_dir = os.environ.get("CLAWBENCH_TASKS_DIR", "").strip()
    if env_dir:
        candidate = Path(env_dir).expanduser().resolve()
        if (candidate / "tier1").is_dir() or candidate.glob("tier*"):
            return candidate

    # 2. Sibling of the package source (works for source checkouts).
    sibling = Path(__file__).parent.parent / "tasks"
    if (sibling / "tier1").is_dir():
        return sibling

    # 3. Current working directory (works when the user runs clawbench from
    #    a repo root that has tasks/ in it — matches the Dockerfile WORKDIR
    #    layout `/home/node/app/tasks`).
    cwd_dir = Path.cwd() / "tasks"
    if (cwd_dir / "tier1").is_dir():
        return cwd_dir

    # 4. Known Docker/HF Space layout.
    for container_candidate in (
        Path("/home/node/app/tasks"),
        Path("/home/user/app/tasks"),
        Path("/app/tasks"),
    ):
        if (container_candidate / "tier1").is_dir():
            return container_candidate

    # 5. Give up and return the sibling path anyway — task loading will
    #    fail loudly instead of silently returning an empty task list.
    return sibling


TASKS_DIR = _resolve_tasks_dir()


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
