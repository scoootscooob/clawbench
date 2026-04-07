"""Background evaluation worker that processes the job queue.

Runs inside the HF Space container alongside the gateway and Gradio frontend.
Polls for PENDING jobs, starts the gateway, runs the benchmark, stores results.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from pathlib import Path

from clawbench.client import GatewayConfig
from clawbench.harness import BenchmarkHarness
from clawbench.queue import JobQueue, JobStatus
from clawbench.scorer import JudgeConfig

logger = logging.getLogger(__name__)

RESULTS_DIR = Path("/data/results") if Path("/data").exists() else Path("data/results")
GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", "18789"))
GATEWAY_TOKEN = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")
POLL_INTERVAL = 10  # seconds


class EvalWorker:
    """Background worker that processes evaluation jobs."""

    def __init__(self, queue: JobQueue) -> None:
        self.queue = queue
        self._gateway_process: subprocess.Popen | None = None
        self._running = False

    async def start(self) -> None:
        """Start the worker loop."""
        self._running = True
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Worker started, polling every %ds", POLL_INTERVAL)

        while self._running:
            try:
                pending = await self.queue.list_pending()
                if pending:
                    job = pending[0]  # FIFO
                    await self._process_job(job)
                else:
                    await asyncio.sleep(POLL_INTERVAL)
            except Exception as e:
                logger.error("Worker loop error: %s", e)
                await asyncio.sleep(POLL_INTERVAL)

    async def stop(self) -> None:
        self._running = False
        self._stop_gateway()

    async def _process_job(self, job) -> None:
        """Evaluate a single job."""
        logger.info("Processing job %s: model=%s", job.job_id, job.request.model)
        await self.queue.mark_evaluating(job.job_id)

        try:
            # Ensure gateway is running
            await self._ensure_gateway()

            # Resolve API key from environment
            api_key = ""
            if job.request.api_key_env:
                api_key = os.environ.get(job.request.api_key_env, "")

            judge_config = JudgeConfig(
                api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            ) if os.environ.get("ANTHROPIC_API_KEY") else None

            harness = BenchmarkHarness(
                gateway_config=GatewayConfig(
                    url=f"ws://127.0.0.1:{GATEWAY_PORT}",
                    token=GATEWAY_TOKEN,
                ),
                model=job.request.model,
                provider=job.request.provider,
                runs_per_task=job.request.runs_per_task,
                judge_config=judge_config,
                category=job.request.category,
            )

            result = await harness.run()

            # Save results locally
            result_path = RESULTS_DIR / f"{result.submission_id}.json"
            result_path.write_text(json.dumps(result.model_dump(), indent=2))

            # Upload to HF Dataset
            try:
                from clawbench.upload import upload_result
                await upload_result(result)
            except Exception as e:
                logger.warning("Failed to upload results to Hub: %s", e)

            await self.queue.mark_finished(job.job_id, result.submission_id)
            logger.info("Job %s finished: composite=%.3f pass^k=%.0f%%",
                        job.job_id, result.overall_composite, result.overall_pass_hat_k * 100)

        except Exception as e:
            logger.error("Job %s failed: %s", job.job_id, e)
            await self.queue.mark_failed(job.job_id, str(e))

    async def _ensure_gateway(self) -> None:
        """Start the OpenClaw gateway if not already running."""
        if self._gateway_process and self._gateway_process.poll() is None:
            return  # Already running

        logger.info("Starting OpenClaw gateway on port %d", GATEWAY_PORT)

        # Look for gateway binary
        gateway_cmd = self._find_gateway_cmd()
        if not gateway_cmd:
            raise RuntimeError("OpenClaw gateway binary not found")

        self._gateway_process = subprocess.Popen(
            [*gateway_cmd, "gateway", "run",
             "--bind", "loopback",
             "--port", str(GATEWAY_PORT),
             "--force"],
            stdout=open("/tmp/gateway.log", "a"),
            stderr=subprocess.STDOUT,
        )

        # Wait for health
        import httpx
        for i in range(30):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"http://127.0.0.1:{GATEWAY_PORT}/health")
                    if resp.status_code == 200:
                        logger.info("Gateway healthy")
                        return
            except Exception:
                pass
            await asyncio.sleep(1)

        raise RuntimeError("Gateway failed to start within 30s")

    def _find_gateway_cmd(self) -> list[str] | None:
        """Find the openclaw binary."""
        import shutil
        # npm global install (primary path in Docker)
        if shutil.which("openclaw"):
            return ["openclaw"]
        # Try known node locations
        for path in [
            "/usr/lib/node_modules/openclaw/dist/cli.js",
            "/openclaw/dist/cli.js",
            "/home/user/openclaw/dist/cli.js",
        ]:
            if Path(path).exists():
                return ["node", path]
        return None

    def _stop_gateway(self) -> None:
        if self._gateway_process:
            self._gateway_process.terminate()
            try:
                self._gateway_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._gateway_process.kill()
            self._gateway_process = None
