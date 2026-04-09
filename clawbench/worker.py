"""Background evaluation worker for ClawBench."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from clawbench.client import GatewayClient, GatewayConfig
from clawbench.harness import BenchmarkHarness
from clawbench.queue import JobQueue
from clawbench.schemas import TaskDefinition
from clawbench.tasks import load_all_tasks

logger = logging.getLogger(__name__)

RESULTS_DIR = Path("/data/results") if Path("/data").exists() else Path("data/results")
GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", "18789"))
GATEWAY_TOKEN = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "clawbench-internal-token")
GATEWAY_WS_URL = f"ws://localhost:{GATEWAY_PORT}"
GATEWAY_PORT_SPACING = max(20, int(os.environ.get("CLAWBENCH_GATEWAY_PORT_SPACING", "20")))
PARALLEL_LANE_ROOT = Path(os.environ.get("CLAWBENCH_PARALLEL_LANE_ROOT", "/tmp/clawbench-lanes"))
POLL_INTERVAL = 10


@dataclass
class ParallelLane:
    index: int
    tasks: list[TaskDefinition] = field(default_factory=list)
    estimated_weight: float = 0.0
    browser_lane: bool = False
    port: int = 0
    state_dir: Path | None = None
    log_path: Path | None = None

    @property
    def ws_url(self) -> str:
        return f"ws://localhost:{self.port}"

    @property
    def gateway_config(self) -> GatewayConfig:
        return GatewayConfig(url=self.ws_url, token=GATEWAY_TOKEN)


class EvalWorker:
    def __init__(self, queue: JobQueue) -> None:
        self.queue = queue
        self._gateway_process: subprocess.Popen | None = None
        self._parallel_gateway_processes: dict[int, subprocess.Popen] = {}
        self._running = False
        self._active_model = ""

    async def start(self) -> None:
        self._running = True
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Worker started, polling every %ss", POLL_INTERVAL)
        while self._running:
            try:
                pending = await self.queue.list_pending()
                if pending:
                    await self._process_job(pending[0])
                else:
                    await asyncio.sleep(POLL_INTERVAL)
            except Exception as exc:
                logger.error("Worker loop error: %s", exc)
                await asyncio.sleep(POLL_INTERVAL)

    async def stop(self) -> None:
        self._running = False
        self._stop_gateway()
        self._stop_parallel_gateways()

    async def _process_job(self, job) -> None:
        logger.info("Processing job %s: model=%s", job.job_id, job.request.model)
        await self.queue.mark_evaluating(job.job_id)
        try:
            self.set_active_model(job.request.model)
            requested_parallel_lanes = max(1, int(getattr(job.request, "max_parallel_lanes", 1) or 1))
            if requested_parallel_lanes > 1:
                result = await self._run_parallel_benchmark(job, requested_parallel_lanes)
            else:
                result = await self._run_serial_benchmark(job)

            result_path = RESULTS_DIR / f"{result.submission_id}.json"
            result_path.write_text(json.dumps(result.model_dump(), indent=2), encoding="utf-8")

            try:
                from clawbench.upload import upload_result

                await upload_result(result)
            except Exception as exc:
                logger.warning("Failed to upload results to Hub: %s", exc)

            await self.queue.mark_finished(job.job_id, result.submission_id)
            logger.info(
                "Job %s finished: score=%.3f pass^k=%.0f%%",
                job.job_id,
                result.overall_score,
                result.overall_pass_hat_k * 100,
            )
        except Exception as exc:
            logger.error("Job %s failed: %s", job.job_id, exc)
            await self.queue.mark_failed(job.job_id, str(exc))
        finally:
            # Tear the gateway down after every job so submissions never inherit
            # process state from earlier evaluations.
            self._stop_gateway()
            self._stop_parallel_gateways()
            self._active_model = ""

    async def _run_serial_benchmark(self, job) -> object:
        self._stop_gateway()
        await self._ensure_gateway()
        await self._preflight_browser_support(
            job.request.tier,
            scenario=job.request.scenario,
            prompt_variant=job.request.prompt_variant,
        )

        harness = BenchmarkHarness(
            gateway_config=GatewayConfig(
                url=GATEWAY_WS_URL,
                token=GATEWAY_TOKEN,
            ),
            model=job.request.model,
            provider=job.request.provider,
            judge_model=job.request.judge_model or os.environ.get("CLAWBENCH_JUDGE_MODEL", ""),
            runs_per_task=job.request.runs_per_task,
            tier=job.request.tier,
            scenario=job.request.scenario,
            prompt_variant=job.request.prompt_variant,
            prepare_run=self._prepare_benchmark_run,
        )
        return await harness.run()

    async def _run_parallel_benchmark(self, job, requested_parallel_lanes: int):
        tasks = self._load_job_tasks(job)
        if not tasks:
            raise ValueError("No tasks to run")

        lanes = self._plan_parallel_lanes(tasks, requested_parallel_lanes)
        if len(lanes) <= 1:
            logger.info(
                "Parallel request for job %s collapsed to %d effective lane; running serially",
                job.job_id,
                len(lanes),
            )
            return await self._run_serial_benchmark(job)

        logger.info(
            "Running job %s across %d isolated lanes (requested=%d)",
            job.job_id,
            len(lanes),
            requested_parallel_lanes,
        )
        job_root = PARALLEL_LANE_ROOT / job.job_id
        shutil.rmtree(job_root, ignore_errors=True)
        job_root.mkdir(parents=True, exist_ok=True)

        try:
            for lane in lanes:
                self._materialize_lane_runtime(lane, job_root)
                logger.info(
                    "Lane %d -> port=%d browser=%s tasks=%s",
                    lane.index + 1,
                    lane.port,
                    lane.browser_lane,
                    ", ".join(task.id for task in lane.tasks),
                )

            lane_results = await asyncio.gather(
                *(self._run_parallel_lane(job, lane) for lane in lanes),
                return_exceptions=True,
            )
            combined_stats = []
            for lane, lane_result in zip(lanes, lane_results, strict=False):
                if isinstance(lane_result, Exception):
                    raise RuntimeError(
                        f"Parallel lane {lane.index + 1} failed for tasks {[task.id for task in lane.tasks]}: {lane_result}"
                    ) from lane_result
                combined_stats.extend(lane_result.task_results)

            ordered_stats = self._order_task_stats(tasks, combined_stats)
            summary_harness = BenchmarkHarness(
                gateway_config=GatewayConfig(url=GATEWAY_WS_URL, token=GATEWAY_TOKEN),
                model=job.request.model,
                provider=job.request.provider,
                judge_model=job.request.judge_model or os.environ.get("CLAWBENCH_JUDGE_MODEL", ""),
                runs_per_task=job.request.runs_per_task,
                tier=job.request.tier,
                scenario=job.request.scenario,
                prompt_variant=job.request.prompt_variant,
            )
            return summary_harness.compose_result_from_task_stats(
                ordered_stats,
                tasks=tasks,
                environment_extra={
                    "parallel_lanes": len(lanes),
                    "requested_parallel_lanes": requested_parallel_lanes,
                    "browser_tasks_serialized": any(lane.browser_lane for lane in lanes),
                    "lane_task_counts": [len(lane.tasks) for lane in lanes],
                },
            )
        finally:
            self._stop_parallel_gateways()
            shutil.rmtree(job_root, ignore_errors=True)

    async def _run_parallel_lane(self, job, lane: ParallelLane):
        gateway_cmd = self._find_gateway_cmd()
        if not gateway_cmd:
            raise RuntimeError("OpenClaw gateway binary not found")

        await self._ensure_parallel_gateway(lane, gateway_cmd)
        await self._preflight_browser_support_for_tasks(lane.tasks, gateway_config=lane.gateway_config)

        async def prepare_run(task: TaskDefinition, run_index: int) -> None:
            logger.info(
                "Resetting lane %d gateway before %s run %d",
                lane.index + 1,
                task.id,
                run_index + 1,
            )
            self._stop_parallel_gateway(lane)
            await self._ensure_parallel_gateway(lane, gateway_cmd)

        harness = BenchmarkHarness(
            gateway_config=lane.gateway_config,
            model=job.request.model,
            provider=job.request.provider,
            judge_model=job.request.judge_model or os.environ.get("CLAWBENCH_JUDGE_MODEL", ""),
            runs_per_task=job.request.runs_per_task,
            task_ids=[task.id for task in lane.tasks],
            scenario=job.request.scenario,
            prompt_variant=job.request.prompt_variant,
            randomize_order=False,
            prepare_run=prepare_run,
            print_report=False,
            quiet=True,
        )
        result = await harness.run()
        logger.info(
            "Lane %d finished with %d task stats",
            lane.index + 1,
            len(result.task_results),
        )
        return result

    def _load_job_tasks(self, job) -> list[TaskDefinition]:
        return load_all_tasks(
            tier=job.request.tier,
            scenario=job.request.scenario,
            prompt_variant=job.request.prompt_variant,
        )

    def _plan_parallel_lanes(
        self,
        tasks: list[TaskDefinition],
        requested_parallel_lanes: int,
    ) -> list[ParallelLane]:
        effective_lanes = max(1, min(requested_parallel_lanes, len(tasks)))
        browser_tasks = [task for task in tasks if task.family.value == "browser"]
        other_tasks = [task for task in tasks if task.family.value != "browser"]
        dedicate_browser_lane = bool(browser_tasks) and effective_lanes > 1

        worker_lane_count = max(1, effective_lanes - (1 if dedicate_browser_lane else 0))
        lanes = [ParallelLane(index=index) for index in range(worker_lane_count)]

        if dedicate_browser_lane:
            lanes.append(ParallelLane(index=len(lanes), browser_lane=True))

        target_lanes = lanes[:-1] if dedicate_browser_lane else lanes
        for task in sorted(other_tasks, key=self._task_weight, reverse=True):
            lane = min(target_lanes, key=lambda item: (item.estimated_weight, len(item.tasks), item.index))
            lane.tasks.append(task)
            lane.estimated_weight += self._task_weight(task)

        if dedicate_browser_lane:
            browser_lane = lanes[-1]
            browser_lane.tasks.extend(browser_tasks)
            browser_lane.estimated_weight = sum(self._task_weight(task) for task in browser_tasks)
        else:
            for task in sorted(browser_tasks, key=self._task_weight, reverse=True):
                lane = min(lanes, key=lambda item: (item.estimated_weight, len(item.tasks), item.index))
                lane.tasks.append(task)
                lane.estimated_weight += self._task_weight(task)

        planned = [lane for lane in lanes if lane.tasks]
        for index, lane in enumerate(planned):
            lane.index = index
        return planned

    def _task_weight(self, task: TaskDefinition) -> float:
        tier_weight = 1.0
        if task.tier.value.startswith("tier"):
            try:
                tier_weight = float(int(task.tier.value.removeprefix("tier")))
            except ValueError:
                tier_weight = 1.0
        family_bonus = 0.0
        if task.family.value in {"multi_tool", "browser", "adversarial"}:
            family_bonus += 0.75
        elif task.family.value in {"repo", "tools"}:
            family_bonus += 0.35
        if len(task.normalized_phases()) > 1:
            family_bonus += 0.5
        return tier_weight + family_bonus

    def _materialize_lane_runtime(self, lane: ParallelLane, job_root: Path) -> None:
        lane_root = job_root / f"lane-{lane.index}"
        lane.state_dir = lane_root / "state"
        lane.log_path = lane_root / "gateway.log"
        lane.port = GATEWAY_PORT + (lane.index * GATEWAY_PORT_SPACING)
        self._seed_lane_state_dir(lane.state_dir)

    def _seed_lane_state_dir(self, target_state_dir: Path) -> None:
        source_state_dir = Path(os.environ.get("OPENCLAW_STATE_DIR", os.path.expanduser("~/.openclaw")))
        shutil.rmtree(target_state_dir, ignore_errors=True)
        target_state_dir.mkdir(parents=True, exist_ok=True)
        if not source_state_dir.exists():
            return

        # Copy only the auth/config surfaces the gateway needs. Workspaces,
        # sessions, and other runtime outputs stay lane-local.
        for name in ["openclaw.json", "credentials", "identity", "agents", "plugins"]:
            source = source_state_dir / name
            target = target_state_dir / name
            if not source.exists():
                continue
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

    def _order_task_stats(self, tasks: list[TaskDefinition], combined_stats: list) -> list:
        stats_by_id = {}
        for stat in combined_stats:
            if stat.task_id in stats_by_id:
                raise RuntimeError(f"Duplicate task stats encountered for {stat.task_id}")
            stats_by_id[stat.task_id] = stat
        missing = [task.id for task in tasks if task.id not in stats_by_id]
        if missing:
            raise RuntimeError(f"Missing aggregated task stats for: {', '.join(missing)}")
        return [stats_by_id[task.id] for task in tasks]

    async def _preflight_browser_support(
        self,
        tier: str | None,
        *,
        scenario: str | None = None,
        prompt_variant: str | None = None,
    ) -> None:
        tasks = load_all_tasks(tier=tier, scenario=scenario, prompt_variant=prompt_variant)
        await self._preflight_browser_support_for_tasks(
            tasks,
            gateway_config=GatewayConfig(url=GATEWAY_WS_URL, token=GATEWAY_TOKEN),
        )

    async def _preflight_browser_support_for_tasks(
        self,
        tasks: list[TaskDefinition],
        *,
        gateway_config: GatewayConfig,
    ) -> None:
        if not any(task.family.value == "browser" for task in tasks):
            return

        async with GatewayClient(gateway_config) as client:
            session_key = await client.create_session(label="clawbench-browser-preflight")
            try:
                payload = await client.get_effective_tools(session_key)
            finally:
                await client.delete_session(session_key)

        tool_ids = {
            str(tool.get("id", ""))
            for group in payload.get("groups", [])
            for tool in group.get("tools", [])
        }
        if "browser" not in tool_ids:
            raise RuntimeError(
                "Browser-tier tasks were selected, but the gateway does not expose the browser tool."
            )

    async def _ensure_gateway(self) -> None:
        if self._gateway_process and self._gateway_process.poll() is None:
            return

        logger.info("Starting OpenClaw gateway on port %d", GATEWAY_PORT)
        gateway_cmd = self._find_gateway_cmd()
        if not gateway_cmd:
            raise RuntimeError("OpenClaw gateway binary not found")

        gateway_token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "clawbench-internal-token")
        gateway_env = {
            **os.environ,
            "OPENCLAW_HOME": os.environ.get("OPENCLAW_HOME", os.path.expanduser("~")),
            "OPENCLAW_STATE_DIR": os.environ.get("OPENCLAW_STATE_DIR", os.path.expanduser("~/.openclaw")),
            "OPENCLAW_SKIP_GMAIL_WATCHER": "1",
            "OPENCLAW_SKIP_CANVAS_HOST": "1",
            "OPENCLAW_NO_RESPAWN": "1",
        }
        self._configure_browser_runtime(gateway_cmd, gateway_env)
        try:
            Path("/tmp/gateway.log").write_text("", encoding="utf-8")
        except Exception:
            pass

        self._gateway_process = subprocess.Popen(
            [
                *gateway_cmd,
                "gateway",
                "run",
                "--allow-unconfigured",
                "--dev",
                "--bind",
                "loopback",
                "--port",
                str(GATEWAY_PORT),
                "--auth",
                "token",
                "--token",
                gateway_token,
            ],
            stdout=open("/tmp/gateway.log", "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            env=gateway_env,
        )

        import httpx

        for _ in range(60):
            if self._gateway_process.poll() is not None:
                log_tail = self._read_gateway_log()
                raise RuntimeError(
                    f"Gateway exited with code {self._gateway_process.returncode}. Log:\n{log_tail}"
                )
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"http://127.0.0.1:{GATEWAY_PORT}/health")
                if response.status_code == 200:
                    await self._assert_gateway_control_plane(
                        GatewayConfig(url=GATEWAY_WS_URL, token=GATEWAY_TOKEN)
                    )
                    logger.info("Gateway healthy")
                    return
            except Exception:
                pass
            await asyncio.sleep(1)

        raise RuntimeError(f"Gateway failed to start within 60s. Log:\n{self._read_gateway_log()}")

    async def _ensure_parallel_gateway(self, lane: ParallelLane, gateway_cmd: list[str]) -> None:
        process = self._parallel_gateway_processes.get(lane.index)
        if process and process.poll() is None:
            return
        if lane.state_dir is None or lane.log_path is None:
            raise RuntimeError(f"Lane {lane.index + 1} runtime was not materialized before gateway startup")

        logger.info("Starting lane %d gateway on port %d", lane.index + 1, lane.port)
        gateway_token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "clawbench-internal-token")
        gateway_env = {
            **os.environ,
            "OPENCLAW_HOME": os.environ.get("OPENCLAW_HOME", os.path.expanduser("~")),
            "OPENCLAW_STATE_DIR": str(lane.state_dir),
            "OPENCLAW_SKIP_GMAIL_WATCHER": "1",
            "OPENCLAW_SKIP_CANVAS_HOST": "1",
            "OPENCLAW_NO_RESPAWN": "1",
        }
        self._configure_browser_runtime(gateway_cmd, gateway_env)
        lane.log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = lane.log_path.open("a", encoding="utf-8")
        try:
            process = subprocess.Popen(
                [
                    *gateway_cmd,
                    "gateway",
                    "run",
                    "--allow-unconfigured",
                    "--dev",
                    "--bind",
                    "loopback",
                    "--port",
                    str(lane.port),
                    "--auth",
                    "token",
                    "--token",
                    gateway_token,
                ],
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=gateway_env,
            )
        finally:
            log_handle.close()
        self._parallel_gateway_processes[lane.index] = process

        import httpx

        for _ in range(60):
            if process.poll() is not None:
                log_tail = self._read_parallel_gateway_log(lane)
                raise RuntimeError(
                    f"Lane {lane.index + 1} gateway exited with code {process.returncode}. Log:\n{log_tail}"
                )
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"http://127.0.0.1:{lane.port}/health")
                if response.status_code == 200:
                    await self._assert_gateway_control_plane(lane.gateway_config)
                    logger.info("Lane %d gateway healthy", lane.index + 1)
                    return
            except Exception:
                pass
            await asyncio.sleep(1)

        raise RuntimeError(
            f"Lane {lane.index + 1} gateway failed to start within 60s. Log:\n{self._read_parallel_gateway_log(lane)}"
        )

    async def _prepare_benchmark_run(self, task, run_index: int) -> None:
        logger.info("Resetting gateway before %s run %d", task.id, run_index + 1)
        self._stop_gateway()
        await self._ensure_gateway()

    def set_active_model(self, model: str) -> None:
        self._active_model = model.strip()

    def _configure_browser_runtime(self, gateway_cmd: list[str], gateway_env: dict[str, str]) -> None:
        # Container browser tasks need headless + no-sandbox for reliable Chromium startup.
        config_pairs = [
            ("agents.defaults.skipBootstrap", "true"),
            ("browser.headless", "true"),
            ("browser.noSandbox", "true"),
        ]
        if self._active_model:
            # Keep sub-agent tasks on the benchmark model under test so
            # delegation is scored on behavior rather than ambient gateway
            # defaults or provider-specific auth drift.
            config_pairs.extend(
                [
                    ("agents.defaults.model.primary", self._active_model),
                    ("agents.defaults.subagents.model.primary", self._active_model),
                ]
            )
        for key, value in config_pairs:
            try:
                subprocess.run(
                    [*gateway_cmd, "config", "set", key, value],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=gateway_env,
                    timeout=30,
                )
            except Exception as exc:
                logger.warning("Failed to set %s=%s before gateway startup: %s", key, value, exc)

    def _find_gateway_cmd(self) -> list[str] | None:
        import shutil

        for path in [
            "/openclaw/dist/cli.js",
            "/openclaw/dist/index.js",
            "/home/user/openclaw/dist/cli.js",
            "/usr/lib/node_modules/openclaw/dist/cli.js",
        ]:
            if Path(path).exists():
                return ["node", path]
        if shutil.which("openclaw"):
            return ["openclaw"]
        return None

    async def _assert_gateway_control_plane(self, gateway_config: GatewayConfig) -> None:
        async with GatewayClient(gateway_config) as client:
            session_key = await client.create_session(label="clawbench-startup-probe")
            await client.delete_session(session_key)

    def _read_gateway_log(self) -> str:
        try:
            return Path("/tmp/gateway.log").read_text(encoding="utf-8", errors="replace")[-4_000:]
        except Exception:
            return "(no gateway log)"

    def _read_parallel_gateway_log(self, lane: ParallelLane) -> str:
        if lane.log_path is None:
            return "(no gateway log)"
        try:
            return lane.log_path.read_text(encoding="utf-8", errors="replace")[-4_000:]
        except Exception:
            return "(no gateway log)"

    def _stop_gateway(self) -> None:
        if not self._gateway_process:
            return
        self._gateway_process.terminate()
        try:
            self._gateway_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._gateway_process.kill()
        self._gateway_process = None

    def _stop_parallel_gateway(self, lane: ParallelLane) -> None:
        process = self._parallel_gateway_processes.pop(lane.index, None)
        if not process:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    def _stop_parallel_gateways(self) -> None:
        for lane_index, process in list(self._parallel_gateway_processes.items()):
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            finally:
                self._parallel_gateway_processes.pop(lane_index, None)
