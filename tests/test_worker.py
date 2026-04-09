from pathlib import Path
from types import SimpleNamespace

import pytest

from clawbench.queue import JobQueue
from clawbench.worker import GATEWAY_PORT, GATEWAY_PORT_SPACING, EvalWorker, ParallelLane


class DummyTask:
    def __init__(
        self,
        task_id: str,
        tier: str,
        family: str,
        phases: int = 1,
        capabilities: list[str] | None = None,
    ) -> None:
        self.id = task_id
        self.tier = SimpleNamespace(value=tier)
        self.family = SimpleNamespace(value=family)
        self._phases = phases
        self.capabilities = [SimpleNamespace(value=value) for value in (capabilities or [])]

    def normalized_phases(self):
        return [object()] * self._phases


def test_configure_browser_runtime_sets_benchmark_safe_openclaw_config(monkeypatch):
    worker = EvalWorker(JobQueue())
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    worker._configure_browser_runtime(["node", "/openclaw/dist/cli.js"], {"HOME": "/tmp/home"})

    assert calls == [
        ["node", "/openclaw/dist/cli.js", "config", "set", "agents.defaults.skipBootstrap", "true"],
        ["node", "/openclaw/dist/cli.js", "config", "set", "browser.headless", "true"],
        ["node", "/openclaw/dist/cli.js", "config", "set", "browser.noSandbox", "true"],
    ]


def test_configure_browser_runtime_pins_subagents_to_active_model(monkeypatch):
    worker = EvalWorker(JobQueue())
    worker.set_active_model("openai-codex/gpt-5.4")
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    worker._configure_browser_runtime(["node", "/openclaw/dist/cli.js"], {"HOME": "/tmp/home"})

    assert calls == [
        ["node", "/openclaw/dist/cli.js", "config", "set", "agents.defaults.skipBootstrap", "true"],
        ["node", "/openclaw/dist/cli.js", "config", "set", "browser.headless", "true"],
        ["node", "/openclaw/dist/cli.js", "config", "set", "browser.noSandbox", "true"],
        ["node", "/openclaw/dist/cli.js", "config", "set", "agents.defaults.model.primary", "openai-codex/gpt-5.4"],
        ["node", "/openclaw/dist/cli.js", "config", "set", "agents.defaults.subagents.model.primary", "openai-codex/gpt-5.4"],
    ]


@pytest.mark.asyncio
async def test_prepare_benchmark_run_restarts_gateway_on_task_boundary(monkeypatch):
    worker = EvalWorker(JobQueue())
    calls: list[str] = []

    def fake_stop_gateway() -> None:
        calls.append("stop")

    async def fake_ensure_gateway() -> None:
        calls.append("ensure")

    monkeypatch.setattr(worker, "_stop_gateway", fake_stop_gateway)
    monkeypatch.setattr(worker, "_ensure_gateway", fake_ensure_gateway)

    task = DummyTask("t1-bugfix-discount", "tier1", "coding")

    await worker._prepare_benchmark_run(task, 0)
    await worker._prepare_benchmark_run(task, 1)
    await worker._prepare_benchmark_run(DummyTask("t1-refactor-csv-loader", "tier1", "coding"), 0)

    assert calls == ["stop", "ensure"]


@pytest.mark.asyncio
async def test_prepare_benchmark_run_restarts_each_run_for_automation(monkeypatch):
    worker = EvalWorker(JobQueue())
    calls: list[str] = []

    def fake_stop_gateway() -> None:
        calls.append("stop")

    async def fake_ensure_gateway() -> None:
        calls.append("ensure")

    monkeypatch.setattr(worker, "_stop_gateway", fake_stop_gateway)
    monkeypatch.setattr(worker, "_ensure_gateway", fake_ensure_gateway)

    task = DummyTask(
        "t3-monitoring-automation",
        "tier3",
        "tools",
        capabilities=["automation"],
    )

    await worker._prepare_benchmark_run(task, 0)
    await worker._prepare_benchmark_run(task, 1)

    assert calls == ["stop", "ensure"]


def test_plan_parallel_lanes_serializes_browser_tasks():
    worker = EvalWorker(JobQueue())
    tasks = [
        DummyTask("t1", "tier1", "coding"),
        DummyTask("t2", "tier4", "browser"),
        DummyTask("t3", "tier3", "repo"),
        DummyTask("t4", "tier2", "browser"),
        DummyTask("t5", "tier5", "multi_tool", phases=2),
    ]

    lanes = worker._plan_parallel_lanes(tasks, requested_parallel_lanes=3)

    assert len(lanes) == 3
    browser_lanes = [lane for lane in lanes if lane.browser_lane]
    assert len(browser_lanes) == 1
    assert [task.id for task in browser_lanes[0].tasks] == ["t2", "t4"]
    assert all(
        task.family.value != "browser"
        for lane in lanes
        if not lane.browser_lane
        for task in lane.tasks
    )


def test_materialize_lane_runtime_spaces_ports_and_copies_auth(tmp_path: Path, monkeypatch):
    source_state = tmp_path / "source-state"
    auth_path = source_state / "agents" / "main" / "agent"
    auth_path.mkdir(parents=True, exist_ok=True)
    (auth_path / "auth-profiles.json").write_text('{"default": "ok"}', encoding="utf-8")
    (source_state / "openclaw.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OPENCLAW_STATE_DIR", str(source_state))

    worker = EvalWorker(JobQueue())
    lane0 = ParallelLane(index=0, tasks=[DummyTask("t1", "tier1", "coding")])
    lane1 = ParallelLane(index=1, tasks=[DummyTask("t2", "tier2", "browser")], browser_lane=True)

    job_root = tmp_path / "job-root"
    worker._materialize_lane_runtime(lane0, job_root)
    worker._materialize_lane_runtime(lane1, job_root)

    assert lane0.port == GATEWAY_PORT
    assert lane1.port == GATEWAY_PORT + GATEWAY_PORT_SPACING
    assert lane1.state_dir is not None
    assert (lane1.state_dir / "agents" / "main" / "agent" / "auth-profiles.json").exists()
