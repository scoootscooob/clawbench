"""Task loading from YAML files."""

from __future__ import annotations

from pathlib import Path

import yaml

from clawbench.schemas import TaskDefinition

TASKS_DIR = Path(__file__).parent.parent / "tasks"


def load_task(path: Path) -> TaskDefinition:
    """Load a single task from a YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return TaskDefinition(**data)


def load_all_tasks(
    tasks_dir: Path | None = None,
    category: str | None = None,
    task_ids: list[str] | None = None,
) -> list[TaskDefinition]:
    """Load all tasks from the tasks directory, optionally filtered."""
    root = tasks_dir or TASKS_DIR
    tasks: list[TaskDefinition] = []

    for yaml_path in sorted(root.rglob("*.yaml")):
        # Skip template files
        if yaml_path.name.startswith("_"):
            continue
        try:
            task = load_task(yaml_path)
        except Exception as e:
            raise ValueError(f"Failed to load {yaml_path}: {e}") from e

        if category and task.category.value != category:
            continue
        if task_ids and task.id not in task_ids:
            continue
        tasks.append(task)

    return tasks


def get_assets_dir() -> Path:
    """Return the path to the task assets directory."""
    return TASKS_DIR / "assets"
