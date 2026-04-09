"""CLI entry point for ClawBench."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import click

from clawbench.client import GatewayConfig
from clawbench.harness import BenchmarkHarness

SCENARIO_CHOICES = [
    "file_system_ops",
    "web_info_ops",
    "calendar_reminders",
    "communication_messaging",
    "data_processing_analysis",
    "coding_dev_assist",
    "personal_life_assistant",
    "multi_step_compound",
    "context_continuation",
    "error_boundary_cases",
    "skill_calling",
    "system_capabilities",
]


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
def cli(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@cli.command()
@click.option("--model", "-m", required=True, help="Model to benchmark")
@click.option("--gateway-token", envvar="OPENCLAW_GATEWAY_TOKEN", default="", help="Gateway auth token")
@click.option(
    "--judge-model",
    envvar="CLAWBENCH_JUDGE_MODEL",
    default="",
    help="Optional advisory LLM judge model (does not affect official score)",
)
@click.option("--runs", "-n", default=5, help="Runs per task (reliability uses all runs)")
@click.option("--tier", type=click.Choice(["tier1", "tier2", "tier3", "tier4", "tier5"]), help="Filter tier")
@click.option("--scenario", type=click.Choice(SCENARIO_CHOICES), help="Filter query scenario")
@click.option("--artifact-type", type=click.Choice(["file", "information", "operation", "code", "external_action", "memory", "automation", "mixed"]), help="Filter expected artifact type")
@click.option("--prompt-variant", type=click.Choice(["clear", "ambiguous"]), default="clear", show_default=True, help="Prompt variant to run")
@click.option("--pool", type=click.Choice(["public_dev", "official_hidden"]), help="Filter task pool")
@click.option("--subset", multiple=True, type=click.Choice(["consensus", "hard"]), help="Filter task subset")
@click.option(
    "--capability",
    multiple=True,
    type=click.Choice(
        [
            "bugfix",
            "refactor",
            "test_authoring",
            "multifile_reasoning",
            "browser_debugging",
            "structured_output",
            "memory_continuation",
            "delegation",
            "tool_composition",
            "research_synthesis",
            "graceful_refusal",
            "spec_revision",
            "cross_repo_change",
            "automation",
        ]
    ),
    help="Filter by capability tag",
)
@click.option("--official-only", is_flag=True, help="Only run tasks marked official")
@click.option("--task", "-t", multiple=True, help="Specific task IDs to run")
@click.option("--output", "-o", type=click.Path(), help="Output JSON file path")
@click.option("--no-randomize", is_flag=True, help="Run tasks in definition order")
@click.option("--upload", is_flag=True, help="Upload results to HF Dataset")
def run(
    model: str,
    gateway_token: str,
    judge_model: str,
    runs: int,
    tier: str | None,
    scenario: str | None,
    artifact_type: str | None,
    prompt_variant: str,
    pool: str | None,
    subset: tuple[str, ...],
    capability: tuple[str, ...],
    official_only: bool,
    task: tuple[str, ...],
    output: str | None,
    no_randomize: bool,
    upload: bool,
) -> None:
    gateway_config = GatewayConfig(token=gateway_token)
    harness = BenchmarkHarness(
        gateway_config=gateway_config,
        model=model,
        judge_model=judge_model,
        runs_per_task=runs,
        tier=tier,
        scenario=scenario,
        artifact_type=artifact_type,
        prompt_variant=prompt_variant,
        pool=pool,
        subsets=list(subset),
        capabilities=list(capability),
        official_only=official_only,
        task_ids=list(task) if task else None,
        randomize_order=not no_randomize,
    )

    result = asyncio.run(harness.run())
    out_path = output or f"results/{result.submission_id}.json"
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(result.model_dump(), handle, indent=2)
    click.echo(f"\nResults saved to {out_path}")

    if upload:
        from clawbench.upload import upload_result

        asyncio.run(upload_result(result))


@cli.command()
@click.option("--tasks-dir", type=click.Path(exists=True), help="Custom tasks directory")
@click.option("--scenario", type=click.Choice(SCENARIO_CHOICES), help="Filter query scenario")
@click.option("--prompt-variant", type=click.Choice(["clear", "ambiguous"]), help="Filter prompt variant support")
@click.option("--pool", type=click.Choice(["public_dev", "official_hidden"]), help="Filter task pool")
@click.option("--subset", multiple=True, type=click.Choice(["consensus", "hard"]), help="Filter task subset")
def list_tasks(tasks_dir: str | None, scenario: str | None, prompt_variant: str | None, pool: str | None, subset: tuple[str, ...]) -> None:
    from clawbench.tasks import load_all_tasks

    tasks = load_all_tasks(
        tasks_dir=Path(tasks_dir) if tasks_dir else None,
        scenario=scenario,
        prompt_variant=prompt_variant,
        pool=pool,
        subsets=list(subset),
    )
    click.echo(f"\n{'ID':<34} {'Tier':<7} {'Scene':<24} {'Prompt':<10} {'Pool':<15} {'Family':<12}")
    click.echo("-" * 116)
    for task in tasks:
        click.echo(
            f"  {task.id:<32} {task.tier.value:<7} "
            f"{(task.scenario.value if task.scenario else '-'): <24} "
            f"{'/'.join(variant.value for variant in task.prompt_variants):<10} "
            f"{task.pool.value:<15} {task.family.value:<12}"
        )


@cli.command()
@click.argument("result_file", type=click.Path(exists=True))
def show(result_file: str) -> None:
    from rich.console import Console
    from clawbench.schemas import BenchmarkResult

    with open(result_file, encoding="utf-8") as handle:
        data = json.load(handle)
    result = BenchmarkResult(**data)

    console = Console()
    console.print(f"\n[bold]Model:[/] {result.model}")
    console.print(
        f"[bold]Score:[/] {result.overall_score:.3f} "
        f"(CI: {result.overall_ci_lower:.3f}-{result.overall_ci_upper:.3f})"
    )
    console.print(
        f"  [green]Completion: {result.overall_completion:.3f}[/]  "
        f"[blue]Trajectory: {result.overall_trajectory:.3f}[/]  "
        f"[yellow]Behavior: {result.overall_behavior:.3f}[/]  "
        f"[magenta]Reliability: {result.overall_reliability:.3f}[/]"
    )
    if result.judge_model:
        console.print(
            f"  [magenta]Judge: {result.overall_judge_score:.3f}[/]  "
            f"Confidence: {result.overall_judge_confidence:.3f}  "
            f"Pass rate: {result.overall_judge_pass_rate:.0%}  "
            f"Coverage: {result.judge_task_coverage:.0%}"
        )
    console.print(
        f"  Weighted query: {result.overall_weighted_query_score:.3f}  "
        f"Clear prompt: {result.clear_prompt_score:.3f}  "
        f"Ambiguous prompt: {result.ambiguous_prompt_score:.3f}"
    )
    console.print(
        f"  Latency p50={result.overall_median_latency_ms:.0f}ms "
        f"p95={result.overall_p95_latency_ms:.0f}ms  "
        f"Tokens/pass={result.overall_tokens_per_pass:.0f}  "
        f"Cost/pass=${result.overall_cost_per_pass:.4f}"
    )
    console.print(
        f"  Hard subset: {result.hard_subset_score:.3f}  "
        f"Consensus subset: {result.consensus_subset_score:.3f}"
    )
    console.print(f"  [bold]pass^k reliability: {result.overall_pass_hat_k:.0%}[/]\n")

    for task in result.task_results:
        color = "green" if task.mean_task_score >= 0.7 else "yellow" if task.mean_task_score >= 0.4 else "red"
        top_failure = max(task.failure_mode_counts.items(), key=lambda item: item[1])[0] if task.failure_mode_counts else "-"
        judge_value = f"{task.mean_judge_score:.2f}" if task.judged_runs > 0 else "-"
        console.print(
            f"  [{color}]{task.mean_task_score:.3f}[/]  {task.task_id}  "
            f"scene={task.scenario or '-'} prompt={task.prompt_variant} "
            f"run={task.mean_run_score:.2f} comp={task.mean_completion_score:.2f} "
            f"traj={task.mean_trajectory_score:.2f} beh={task.mean_behavior_score:.2f} "
            f"judge={judge_value} "
            f"rel={task.reliability_score:.2f} delivery={task.delivery_outcome_counts} "
            f"tok/pass={task.tokens_per_pass:.0f} p50={task.median_duration_ms:.0f}ms fail={top_failure}"
        )


def main() -> None:
    cli()
