from pathlib import Path

from click.testing import CliRunner

from clawbench.cli import cli
from clawbench.releases import build_hidden_release
from clawbench.tasks import load_all_tasks


def test_load_all_tasks_reads_active_hidden_release(monkeypatch, tmp_path: Path):
    source_task = next(task for task in load_all_tasks() if task.id == "t1-bugfix-discount")
    active_release_path = tmp_path / "registry" / "active_release.json"
    private_root = tmp_path / "private_tasks"
    monkeypatch.setenv("CLAWBENCH_ACTIVE_RELEASE_PATH", str(active_release_path))

    build_hidden_release(
        tasks=[source_task],
        release_id="rel-2026-04a",
        private_tasks_root=private_root,
        active_release_path=active_release_path,
        activate=True,
    )

    public_tasks = load_all_tasks()
    hidden_tasks = load_all_tasks(pool="official_hidden")

    assert all(task.pool.value == "public_dev" for task in public_tasks)
    assert [task.id for task in hidden_tasks] == ["t1-bugfix-discount"]
    assert hidden_tasks[0].pool.value == "official_hidden"
    assert hidden_tasks[0].release_id == "rel-2026-04a"
    assert hidden_tasks[0].variant_id == "rel-2026-04a"
    assert hidden_tasks[0].official is True


def test_build_release_cli_materializes_hidden_snapshot(monkeypatch, tmp_path: Path):
    runner = CliRunner()
    active_release_path = tmp_path / "registry" / "active_release.json"
    private_root = tmp_path / "private_tasks"
    monkeypatch.setenv("CLAWBENCH_ACTIVE_RELEASE_PATH", str(active_release_path))

    result = runner.invoke(
        cli,
        [
            "build-release",
            "--release-id",
            "rel-2026-04b",
            "-t",
            "t1-bugfix-discount",
            "--private-tasks-dir",
            str(private_root),
            "--active-release-path",
            str(active_release_path),
        ],
    )

    assert result.exit_code == 0, result.output
    release_task = private_root / "rel-2026-04b" / "tier1" / "t1-bugfix-discount.yaml"
    assert release_task.exists()
    assert active_release_path.exists()

    hidden_tasks = load_all_tasks(pool="official_hidden")
    assert [task.id for task in hidden_tasks] == ["t1-bugfix-discount"]
    assert hidden_tasks[0].release_id == "rel-2026-04b"
