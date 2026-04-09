import pytest

from clawbench.hub import dataset_has_submission_results, ensure_dataset_repo, resolve_dataset_repo
from clawbench.queue import Job, JobQueue, JobStatus, SubmissionRequest


def test_submission_request_defaults_to_single_parallel_lane():
    request = SubmissionRequest(model="openai-codex/gpt-5.4")

    assert request.max_parallel_lanes == 1


def test_resolve_dataset_repo_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv("CLAWBENCH_QUEUE_DATASET", "custom-owner/custom-results")
    monkeypatch.setenv("SPACE_ID", "ScoootScooob/clawbench")

    assert resolve_dataset_repo() == "custom-owner/custom-results"


def test_resolve_dataset_repo_derives_owner_from_space_id(monkeypatch):
    monkeypatch.delenv("CLAWBENCH_QUEUE_DATASET", raising=False)
    monkeypatch.setenv("SPACE_ID", "ScoootScooob/clawbench")

    assert resolve_dataset_repo() == "ScoootScooob/clawbench-results"


def test_ensure_dataset_repo_creates_missing_repo_and_bootstrap_readme():
    class FakeApi:
        def __init__(self) -> None:
            self.created: list[tuple[str, str, bool, bool]] = []
            self.uploaded: list[tuple[str, str, str]] = []

        def repo_info(self, repo_id: str, repo_type: str) -> None:
            raise RuntimeError("missing")

        def create_repo(self, repo_id: str, repo_type: str, private: bool, exist_ok: bool) -> None:
            self.created.append((repo_id, repo_type, private, exist_ok))

        def upload_file(
            self,
            *,
            path_or_fileobj: bytes,
            path_in_repo: str,
            repo_id: str,
            repo_type: str,
        ) -> None:
            assert b"ClawBench Results" in path_or_fileobj
            self.uploaded.append((path_in_repo, repo_id, repo_type))

    api = FakeApi()

    ensure_dataset_repo(api, "ScoootScooob/clawbench-results")

    assert api.created == [("ScoootScooob/clawbench-results", "dataset", False, True)]
    assert api.uploaded == [("README.md", "ScoootScooob/clawbench-results", "dataset")]


def test_dataset_has_submission_results_ignores_queue_only_files():
    class FakeApi:
        def list_repo_files(self, repo_id: str, repo_type: str) -> list[str]:
            assert repo_id == "ScoootScooob/clawbench-results"
            assert repo_type == "dataset"
            return ["README.md", "queue/jobs.json"]

    assert not dataset_has_submission_results(FakeApi(), "ScoootScooob/clawbench-results")


def test_dataset_has_submission_results_detects_uploaded_parquet():
    class FakeApi:
        def list_repo_files(self, repo_id: str, repo_type: str) -> list[str]:
            assert repo_id == "ScoootScooob/clawbench-results"
            assert repo_type == "dataset"
            return ["README.md", "data/submissions-00000-of-00001.parquet"]

    assert dataset_has_submission_results(FakeApi(), "ScoootScooob/clawbench-results")


@pytest.mark.asyncio
async def test_mark_evaluating_syncs_to_hub(monkeypatch):
    queue = JobQueue()
    queue._jobs = {
        "job-1": Job(
            job_id="job-1",
            status=JobStatus.PENDING,
            request=SubmissionRequest(model="anthropic/claude-sonnet-4-6"),
        )
    }
    save_calls: list[str] = []
    sync_calls: list[str] = []

    def fake_save_local() -> None:
        save_calls.append("saved")

    async def fake_sync() -> None:
        sync_calls.append("synced")

    monkeypatch.setattr(queue, "_save_local", fake_save_local)
    monkeypatch.setattr(queue, "_sync_to_hub", fake_sync)

    await queue.mark_evaluating("job-1")

    assert queue._jobs["job-1"].status == JobStatus.EVALUATING
    assert queue._jobs["job-1"].started_at is not None
    assert save_calls == ["saved"]
    assert sync_calls == ["synced"]


@pytest.mark.asyncio
async def test_claim_pending_marks_multiple_jobs_evaluating(monkeypatch):
    queue = JobQueue()
    queue._jobs = {
        "job-1": Job(
            job_id="job-1",
            status=JobStatus.PENDING,
            submitted_at="2026-04-09T00:00:01+00:00",
            request=SubmissionRequest(model="anthropic/claude-sonnet-4-6"),
        ),
        "job-2": Job(
            job_id="job-2",
            status=JobStatus.PENDING,
            submitted_at="2026-04-09T00:00:02+00:00",
            request=SubmissionRequest(model="huggingface/Qwen/Qwen3-32B"),
        ),
        "job-3": Job(
            job_id="job-3",
            status=JobStatus.FINISHED,
            submitted_at="2026-04-09T00:00:03+00:00",
            request=SubmissionRequest(model="huggingface/zai-org/GLM-5"),
        ),
    }
    save_calls: list[str] = []
    sync_calls: list[str] = []

    def fake_save_local() -> None:
        save_calls.append("saved")

    async def fake_sync() -> None:
        sync_calls.append("synced")

    monkeypatch.setattr(queue, "_save_local", fake_save_local)
    monkeypatch.setattr(queue, "_sync_to_hub", fake_sync)

    claimed = await queue.claim_pending(limit=2)

    assert [job.job_id for job in claimed] == ["job-1", "job-2"]
    assert queue._jobs["job-1"].status == JobStatus.EVALUATING
    assert queue._jobs["job-2"].status == JobStatus.EVALUATING
    assert queue._jobs["job-3"].status == JobStatus.FINISHED
    assert queue._jobs["job-1"].started_at is not None
    assert queue._jobs["job-2"].started_at is not None
    assert save_calls == ["saved"]
    assert sync_calls == ["synced"]
