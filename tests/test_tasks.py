from pathlib import Path

from clawbench.client import GatewayConfig
from clawbench.harness import BenchmarkHarness
from clawbench.tasks import load_all_tasks


def test_load_all_tasks_returns_full_corpus():
    tasks = load_all_tasks()
    # v0.5 expanded the corpus from 20 to 40 tasks across tiers 1-5.
    assert len(tasks) >= 20
    assert {task.tier.value for task in tasks} == {"tier1", "tier2", "tier3", "tier4", "tier5"}
    assert any(task.capabilities for task in tasks)
    assert any(task.subsets for task in tasks)
    assert any(task.scenario is not None for task in tasks)
    assert any("ambiguous" in [variant.value for variant in task.prompt_variants] for task in tasks)
    assert sum(1 for task in tasks if task.judge is not None) >= 6


def test_load_all_tasks_supports_pool_subset_and_capability_filters():
    hard_tasks = load_all_tasks(subsets=["hard"])
    consensus_tasks = load_all_tasks(subsets=["consensus"])
    bugfix_tasks = load_all_tasks(capabilities=["bugfix"])
    coding_scene_tasks = load_all_tasks(scenario="coding_dev_assist")
    ambiguous_tasks = load_all_tasks(prompt_variant="ambiguous")

    assert hard_tasks
    assert consensus_tasks
    assert bugfix_tasks
    assert coding_scene_tasks
    assert ambiguous_tasks
    assert all("hard" in [subset.value for subset in task.subsets] for task in hard_tasks)
    assert all("consensus" in [subset.value for subset in task.subsets] for task in consensus_tasks)
    assert all("bugfix" in [capability.value for capability in task.capabilities] for task in bugfix_tasks)
    assert all(task.scenario and task.scenario.value == "coding_dev_assist" for task in coding_scene_tasks)
    assert all("ambiguous" in [variant.value for variant in task.prompt_variants] for task in ambiguous_tasks)


def test_workspace_setup_preserves_nested_asset_paths(tmp_path: Path):
    task = next(task for task in load_all_tasks() if task.id == "t1-architecture-brief")
    harness = BenchmarkHarness(gateway_config=GatewayConfig(), model="test-model", randomize_order=False)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    harness._setup_workspace(task, workspace)

    assert (workspace / "app.py").exists()
    assert (workspace / "shop" / "cart.py").exists()
    assert (workspace / "tests" / "test_smoke.py").exists()


def test_selected_tasks_include_judge_rubrics():
    tasks = {task.id: task for task in load_all_tasks()}

    assert tasks["t1-architecture-brief"].judge is not None
    assert tasks["t4-browser-research-and-code"].judge is not None
    assert tasks["t4-delegation-repair"].judge is not None
    assert tasks["t5-contradictory-requirements"].judge is not None
    assert tasks["t5-hallucination-resistant-evidence"].judge is not None
    assert tasks["t5-impossible-graceful-fail"].judge is not None
