"""CLI entry point for ClawBench."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import click

from clawbench.client import GatewayConfig
from clawbench.harness import BenchmarkHarness
from clawbench.scorer import JudgeConfig


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
def cli(verbose: bool) -> None:
    """ClawBench: Rigorous benchmark for AI models as OpenClaw agents."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@cli.command()
@click.option("--model", "-m", required=True, help="Model to benchmark")
@click.option("--gateway-url", default="ws://127.0.0.1:18789", help="Gateway WebSocket URL")
@click.option("--gateway-token", envvar="OPENCLAW_GATEWAY_TOKEN", default="", help="Gateway auth token")
@click.option("--runs", "-n", default=5, help="Runs per task (pass^k uses all runs)")
@click.option("--category", "-c", type=click.Choice(["general", "openclaw", "adversarial"]), help="Filter category")
@click.option("--task", "-t", multiple=True, help="Specific task IDs to run")
@click.option("--judge-api-key", envvar="ANTHROPIC_API_KEY", default="", help="API key for LLM judge + adaptive user")
@click.option("--judge-model", default="claude-sonnet-4-6-20250514", help="Model for LLM judge")
@click.option("--output", "-o", type=click.Path(), help="Output JSON file path")
@click.option("--no-randomize", is_flag=True, help="Run tasks in definition order")
@click.option("--upload", is_flag=True, help="Upload results to HF Dataset")
def run(
    model: str,
    gateway_url: str,
    gateway_token: str,
    runs: int,
    category: str | None,
    task: tuple[str, ...],
    judge_api_key: str,
    judge_model: str,
    output: str | None,
    no_randomize: bool,
    upload: bool,
) -> None:
    """Run the benchmark against a model."""
    gateway_config = GatewayConfig(url=gateway_url, token=gateway_token)
    judge_config = JudgeConfig(model=judge_model, api_key=judge_api_key) if judge_api_key else None

    harness = BenchmarkHarness(
        gateway_config=gateway_config,
        model=model,
        runs_per_task=runs,
        judge_config=judge_config,
        category=category,
        task_ids=list(task) if task else None,
        randomize_order=not no_randomize,
    )

    result = asyncio.run(harness.run())

    out_path = output or f"results/{result.submission_id}.json"
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result.model_dump(), f, indent=2)
    click.echo(f"\nResults saved to {out_path}")

    if upload:
        from clawbench.upload import upload_result
        asyncio.run(upload_result(result))


@cli.command()
@click.option("--tasks-dir", type=click.Path(exists=True), help="Custom tasks directory")
def list_tasks(tasks_dir: str | None) -> None:
    """List available benchmark tasks."""
    from clawbench.tasks import load_all_tasks

    tasks = load_all_tasks(tasks_dir=Path(tasks_dir) if tasks_dir else None)
    click.echo(f"\n{'ID':<35} {'Cat':<12} {'Diff':<8} {'User':<10} {'W(S/T/B)'}")
    click.echo("-" * 85)
    for t in tasks:
        click.echo(
            f"  {t.id:<33} {t.category.value:<12} {t.difficulty.value:<8} "
            f"{t.user.mode:<10} {t.weight_state:.1f}/{t.weight_trajectory:.1f}/{t.weight_behavior:.1f}"
        )


@cli.command()
@click.argument("result_file", type=click.Path(exists=True))
def show(result_file: str) -> None:
    """Display results from a previous run."""
    from rich.console import Console
    from clawbench.schemas import BenchmarkResult

    with open(result_file) as f:
        data = json.load(f)
    result = BenchmarkResult(**data)

    c = Console()
    c.print(f"\n[bold]Model:[/] {result.model}")
    c.print(f"[bold]Composite:[/] {result.overall_composite:.3f} "
            f"(CI: {result.overall_ci_lower:.3f}-{result.overall_ci_upper:.3f})")
    c.print(f"  [green]State: {result.overall_state:.3f}[/]  "
            f"[blue]Trajectory: {result.overall_trajectory:.3f}[/]  "
            f"[yellow]Behavior: {result.overall_behavior:.3f}[/]")
    c.print(f"  [bold]pass^k reliability: {result.overall_pass_hat_k:.0%}[/]\n")

    for ts in result.task_results:
        color = "green" if ts.mean_composite >= 0.7 else "yellow" if ts.mean_composite >= 0.4 else "red"
        pk = "ALL" if ts.pass_hat_k else f"{ts.pass_at_k:.0%}"
        c.print(f"  [{color}]{ts.mean_composite:.3f}[/]  {ts.task_id}  "
                f"S={ts.mean_state_score:.2f} T={ts.mean_trajectory_score:.2f} B={ts.mean_behavior_score:.2f}  "
                f"pass^k={pk}")


def main() -> None:
    cli()
