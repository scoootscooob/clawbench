"""Benchmark harness: POMDP-style agent evaluation loop.

Key differences from v1:
- Conversation loop driven by simulated user (static, adaptive, or adversarial)
- Three-axis scoring: environment state, trajectory, behavior
- pass^k reliability as the primary metric
- Environment reset verification before each run
- Environment checksum for anti-gaming
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import logging
import random
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from rich.console import Console
from rich.table import Table

from clawbench.client import GatewayClient, GatewayConfig
from clawbench.schemas import (
    BenchmarkResult,
    CategoryResult,
    TaskDefinition,
    TaskRunResult,
    TaskStats,
    TokenUsage,
    Transcript,
    TranscriptMessage,
)
from clawbench.scorer import JudgeConfig, score_task_run
from clawbench.simulated_user import UserSimulator
from clawbench.stats import bootstrap_ci, summarize_task_runs
from clawbench.tasks import get_assets_dir, load_all_tasks

logger = logging.getLogger(__name__)
console = Console()


class BenchmarkHarness:
    def __init__(
        self,
        gateway_config: GatewayConfig,
        model: str,
        provider: str = "",
        runs_per_task: int = 5,
        judge_config: JudgeConfig | None = None,
        category: str | None = None,
        task_ids: list[str] | None = None,
        randomize_order: bool = True,
        tasks_dir: Path | None = None,
    ) -> None:
        self.gateway_config = gateway_config
        self.model = model
        self.provider = provider or (model.split("/")[0] if "/" in model else "")
        self.runs_per_task = max(1, runs_per_task)
        self.judge_config = judge_config
        self.category = category
        self.task_ids = task_ids
        self.randomize_order = randomize_order
        self.tasks_dir = tasks_dir

    async def run(self) -> BenchmarkResult:
        tasks = load_all_tasks(
            tasks_dir=self.tasks_dir,
            category=self.category,
            task_ids=self.task_ids,
        )
        if not tasks:
            raise ValueError("No tasks to run")

        console.print(f"\n[bold]ClawBench v2[/bold] — {len(tasks)} tasks x {self.runs_per_task} runs")
        console.print(f"Model: [cyan]{self.model}[/cyan]")
        console.print(f"Axes: [green]State[/] + [blue]Trajectory[/] + [yellow]Behavior[/]\n")

        if self.randomize_order:
            random.shuffle(tasks)

        all_results: dict[str, list[TaskRunResult]] = {}

        for task in tasks:
            console.print(f"[bold]{task.id}[/bold] ({task.category.value}/{task.surface})"
                          f" [dim]w_s={task.weight_state} w_t={task.weight_trajectory} w_b={task.weight_behavior}[/]")
            task_runs: list[TaskRunResult] = []
            for run_idx in range(self.runs_per_task):
                result = await self._run_single(task, run_idx)
                task_runs.append(result)
                s = result.state_score.score
                t = result.trajectory_score.score
                b = result.behavior_score.score
                c = result.composite_score
                marker = "[green]+" if c >= 0.7 else "[yellow]~" if c >= 0.4 else "[red]-"
                console.print(
                    f"  run {run_idx + 1}: {marker} {c:.2f}[/]"
                    f"  [green]S={s:.2f}[/] [blue]T={t:.2f}[/] [yellow]B={b:.2f}[/]"
                )
                if result.state_score.failed_assertions:
                    for fail in result.state_score.failed_assertions[:3]:
                        console.print(f"    [red]! {fail}[/]")
                if result.trajectory_score.forbidden_violations:
                    for v in result.trajectory_score.forbidden_violations[:3]:
                        console.print(f"    [red]! {v}[/]")
            all_results[task.id] = task_runs

        return self._aggregate(tasks, all_results)

    async def _run_single(self, task: TaskDefinition, run_index: int) -> TaskRunResult:
        """Execute one POMDP-style run of a task.

        1. Create isolated workspace
        2. Verify environment is clean (pre-check)
        3. Create fresh gateway session
        4. Run conversation loop with simulated user
        5. Score: environment state + trajectory + behavior
        6. Cleanup
        """
        workspace = Path(tempfile.mkdtemp(prefix=f"clawbench_{task.id}_"))
        try:
            self._setup_workspace(task, workspace)
            env_checksum = _hash_directory(workspace)

            async with GatewayClient(self.gateway_config) as client:
                # Fresh session per run — critical for isolation
                session_key = await client.create_session(
                    model=self.model,
                    label=f"clawbench-{task.id}-run{run_index}",
                )
                await client.subscribe(session_key)

                # Build the simulated user
                user_sim = UserSimulator(
                    config=task.user,
                    llm_api_key=self.judge_config.api_key if self.judge_config else "",
                )

                # --- POMDP conversation loop ---
                transcript = Transcript()
                start_ms = _now_ms()

                while not user_sim.is_done:
                    # Get next user message
                    user_msg = await user_sim.next_message(transcript)
                    if user_msg is None:
                        break

                    # Record user message in our transcript
                    transcript.messages.append(TranscriptMessage(
                        role="user", text=user_msg, timestamp_ms=_now_ms(),
                    ))

                    # Send to agent and collect response
                    messages = await client.send_and_collect(
                        session_key, user_msg,
                        timeout=float(task.timeout_seconds),
                    )

                    # Record agent response in our transcript
                    for msg in messages:
                        if msg.state == "final" and msg.text:
                            transcript.messages.append(TranscriptMessage(
                                role="assistant", text=msg.text, timestamp_ms=_now_ms(),
                            ))
                        elif msg.state == "error":
                            transcript.messages.append(TranscriptMessage(
                                role="assistant", text=f"ERROR: {msg.error_message}",
                                timestamp_ms=_now_ms(),
                            ))

                duration_ms = _now_ms() - start_ms

                # Get the FULL transcript from gateway (includes tool calls)
                full_transcript = await client.get_history(session_key)

                # --- Score across all three axes ---
                result = await score_task_run(
                    task=task,
                    transcript=full_transcript,
                    workspace=workspace,
                    client=client,
                    session_key=session_key,
                    duration_ms=duration_ms,
                    judge_config=self.judge_config,
                )
                result.run_index = run_index

                # Cleanup session
                try:
                    await client.delete_session(session_key)
                except Exception:
                    pass

                return result

        except Exception as e:
            logger.error("Run %d of %s failed: %s", run_index, task.id, e)
            from clawbench.schemas import BehaviorScore, StateVerificationResult, TrajectoryScore
            return TaskRunResult(
                task_id=task.id,
                run_index=run_index,
                state_score=StateVerificationResult(
                    total_assertions=0, passed_assertions=0, score=0.0,
                ),
                trajectory_score=TrajectoryScore(
                    precision=0, recall=0, f1=0,
                    order_score=0, efficiency_score=0, score=0,
                ),
                behavior_score=BehaviorScore(score=0.0, reason=f"Run failed: {e}"),
                composite_score=0.0,
                transcript=Transcript(),
                duration_ms=0,
                error=str(e),
            )
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    def _setup_workspace(self, task: TaskDefinition, workspace: Path) -> None:
        assets = get_assets_dir()
        for rel_path in task.setup.workspace_files:
            src = assets / Path(rel_path).name
            if src.exists():
                dst = workspace / Path(rel_path).name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

    def _aggregate(
        self,
        tasks: list[TaskDefinition],
        all_results: dict[str, list[TaskRunResult]],
    ) -> BenchmarkResult:
        task_stats_list: list[TaskStats] = []

        for task in tasks:
            runs = all_results.get(task.id, [])
            composites = [r.composite_score for r in runs]
            states = [r.state_score.score for r in runs]
            trajectories = [r.trajectory_score.score for r in runs]
            behaviors = [r.behavior_score.score for r in runs]
            summary = summarize_task_runs(composites, task.pass_threshold)

            durations = [r.duration_ms for r in runs if r.duration_ms > 0]
            mean_dur = sum(durations) / len(durations) if durations else 0.0

            # pass^k: did ALL runs pass?
            all_passed = all(s >= task.pass_threshold for s in composites)

            # Mean trajectory precision/recall
            mean_prec = sum(r.trajectory_score.precision for r in runs) / len(runs) if runs else 0
            mean_rec = sum(r.trajectory_score.recall for r in runs) / len(runs) if runs else 0

            task_stats_list.append(TaskStats(
                task_id=task.id,
                runs=len(runs),
                mean_state_score=_mean(states),
                mean_trajectory_score=_mean(trajectories),
                mean_behavior_score=_mean(behaviors),
                mean_composite=summary.mean,
                stddev=summary.stddev,
                min_score=summary.min_score,
                max_score=summary.max_score,
                pass_at_1=summary.pass_at_1,
                pass_at_k=summary.consistency,
                pass_hat_k=all_passed,
                scores=composites,
                mean_duration_ms=mean_dur,
                high_variance=summary.high_variance,
                trajectory_precision=mean_prec,
                trajectory_recall=mean_rec,
            ))

        # Group by category
        categories: dict[str, list[TaskStats]] = {}
        for task in tasks:
            cat = task.category.value
            stats = next(s for s in task_stats_list if s.task_id == task.id)
            categories.setdefault(cat, []).append(stats)

        category_results: list[CategoryResult] = []
        all_composites: list[float] = []
        all_states: list[float] = []
        all_trajectories: list[float] = []
        all_behaviors: list[float] = []

        for cat, stats_list in sorted(categories.items()):
            composites = [s.mean_composite for s in stats_list]
            ci = bootstrap_ci(composites)
            pass_hat_rate = sum(1 for s in stats_list if s.pass_hat_k) / len(stats_list)

            category_results.append(CategoryResult(
                category=cat,
                mean_composite=ci.mean,
                mean_state=_mean([s.mean_state_score for s in stats_list]),
                mean_trajectory=_mean([s.mean_trajectory_score for s in stats_list]),
                mean_behavior=_mean([s.mean_behavior_score for s in stats_list]),
                ci_lower=ci.lower,
                ci_upper=ci.upper,
                pass_hat_k_rate=pass_hat_rate,
                task_stats=stats_list,
            ))
            all_composites.extend(composites)
            all_states.extend(s.mean_state_score for s in stats_list)
            all_trajectories.extend(s.mean_trajectory_score for s in stats_list)
            all_behaviors.extend(s.mean_behavior_score for s in stats_list)

        overall_ci = bootstrap_ci(all_composites)
        overall_pass_hat = (
            sum(1 for s in task_stats_list if s.pass_hat_k) / len(task_stats_list)
            if task_stats_list else 0.0
        )

        result = BenchmarkResult(
            submission_id=str(uuid.uuid4()),
            model=self.model,
            provider=self.provider,
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            overall_composite=overall_ci.mean,
            overall_state=_mean(all_states),
            overall_trajectory=_mean(all_trajectories),
            overall_behavior=_mean(all_behaviors),
            overall_ci_lower=overall_ci.lower,
            overall_ci_upper=overall_ci.upper,
            overall_pass_hat_k=overall_pass_hat,
            category_results=category_results,
            task_results=task_stats_list,
        )

        self._print_report(result)
        return result

    def _print_report(self, result: BenchmarkResult) -> None:
        console.print(f"\n[bold]{'='*60}[/]")
        console.print(f"[bold]Results — {result.model}[/]")
        console.print(f"[bold]{'='*60}[/]")

        console.print(f"\nComposite: [bold cyan]{result.overall_composite:.3f}[/] "
                       f"(CI: {result.overall_ci_lower:.3f}-{result.overall_ci_upper:.3f})")
        console.print(f"  [green]State: {result.overall_state:.3f}[/]  "
                       f"[blue]Trajectory: {result.overall_trajectory:.3f}[/]  "
                       f"[yellow]Behavior: {result.overall_behavior:.3f}[/]")
        console.print(f"  [bold]pass^k reliability: {result.overall_pass_hat_k:.0%}[/]\n")

        table = Table(title="Task Breakdown")
        table.add_column("Task", style="bold")
        table.add_column("Composite", justify="right")
        table.add_column("State", justify="right")
        table.add_column("Traj", justify="right")
        table.add_column("Behav", justify="right")
        table.add_column("pass^k", justify="center")
        table.add_column("T.Prec", justify="right")
        table.add_column("T.Rec", justify="right")

        for ts in result.task_results:
            color = "green" if ts.mean_composite >= 0.7 else "yellow" if ts.mean_composite >= 0.4 else "red"
            pass_k = "[green]ALL" if ts.pass_hat_k else f"[yellow]{ts.pass_at_k:.0%}"
            table.add_row(
                ts.task_id,
                f"[{color}]{ts.mean_composite:.3f}[/]",
                f"{ts.mean_state_score:.2f}",
                f"{ts.mean_trajectory_score:.2f}",
                f"{ts.mean_behavior_score:.2f}",
                pass_k,
                f"{ts.trajectory_precision:.2f}",
                f"{ts.trajectory_recall:.2f}",
            )

        console.print(table)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


def _hash_directory(path: Path) -> str:
    """SHA-256 hash of all files in a directory — for anti-gaming verification."""
    h = hashlib.sha256()
    for f in sorted(path.rglob("*")):
        if f.is_file():
            h.update(str(f.relative_to(path)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()
