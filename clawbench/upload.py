"""Upload benchmark results to Hugging Face Dataset."""

from __future__ import annotations

import logging
import os

from clawbench.schemas import BenchmarkResult

logger = logging.getLogger(__name__)

HF_DATASET_REPO = "openclaw/clawbench-results"


async def upload_result(
    result: BenchmarkResult,
    dataset_repo: str = HF_DATASET_REPO,
    token: str | None = None,
) -> str:
    """Upload a benchmark result to the HF Dataset.

    Returns the URL of the uploaded dataset entry.
    """
    hf_token = token or os.environ.get("HF_TOKEN", "")
    if not hf_token:
        raise RuntimeError(
            "HF_TOKEN not set. Get a token at https://huggingface.co/settings/tokens"
        )

    try:
        from datasets import Dataset
        from huggingface_hub import HfApi
    except ImportError:
        raise RuntimeError("Install 'datasets' and 'huggingface_hub': pip install datasets huggingface_hub")

    # Flatten the result into a single row for the dataset
    row = {
        "submission_id": result.submission_id,
        "model": result.model,
        "provider": result.provider,
        "timestamp": result.timestamp,
        "openclaw_version": result.openclaw_version,
        "benchmark_version": result.benchmark_version,
        "overall_score": result.overall_score,
        "overall_ci_lower": result.overall_ci_lower,
        "overall_ci_upper": result.overall_ci_upper,
        "certified": result.certified,
        "environment": str(result.environment),
        # Per-category scores as JSON strings
        "category_scores": {
            cr.category: {
                "mean": cr.mean_score,
                "ci_lower": cr.ci_lower,
                "ci_upper": cr.ci_upper,
            }
            for cr in result.category_results
        },
        # Per-task summary
        "task_results": [
            {
                "task_id": ts.task_id,
                "mean_score": ts.mean_score,
                "stddev": ts.stddev,
                "consistency": ts.consistency,
                "pass_at_1": ts.pass_at_1,
                "runs": ts.runs,
            }
            for ts in result.task_results
        ],
    }

    # Create dataset with single row and push
    ds = Dataset.from_list([row])

    api = HfApi(token=hf_token)

    # Ensure repo exists
    try:
        api.repo_info(repo_id=dataset_repo, repo_type="dataset")
    except Exception:
        api.create_repo(repo_id=dataset_repo, repo_type="dataset", private=False)
        logger.info("Created dataset repo: %s", dataset_repo)

    # Push as a new split named by submission ID
    ds.push_to_hub(
        dataset_repo,
        split="submissions",
        token=hf_token,
    )

    url = f"https://huggingface.co/datasets/{dataset_repo}"
    logger.info("Results uploaded to %s", url)
    return url
