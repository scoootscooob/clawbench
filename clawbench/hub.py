"""Helpers for Hugging Face dataset persistence."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DATASET_SUFFIX = "clawbench-results"
LEGACY_DATASET_REPO = "openclaw/clawbench-results"
SPACE_REPO_ENV_KEYS = ("SPACE_ID", "HF_SPACE_ID", "SPACE_REPO_ID")
SPACE_OWNER_ENV_KEYS = ("SPACE_AUTHOR_NAME",)
_WHOAMI_CACHE: dict[str, str | None] = {}
DATASET_README = """---
pretty_name: ClawBench Results
---

# ClawBench Results

Persistent queue state and benchmark submissions for the ClawBench HF Space.
"""


def resolve_dataset_repo(token: str | None = None) -> str:
    explicit = os.environ.get("CLAWBENCH_QUEUE_DATASET", "").strip()
    if explicit:
        return explicit

    owner = _resolve_owner(token)
    if owner:
        return f"{owner}/{DEFAULT_DATASET_SUFFIX}"
    return LEGACY_DATASET_REPO


def ensure_dataset_repo(api, repo_id: str) -> None:
    files: set[str] = set()
    created = False
    try:
        api.repo_info(repo_id=repo_id, repo_type="dataset")
        files = dataset_repo_files(api, repo_id)
    except Exception:
        api.create_repo(repo_id=repo_id, repo_type="dataset", private=False, exist_ok=True)
        created = True
        logger.info("Created dataset repo: %s", repo_id)

    if created or "README.md" not in files:
        api.upload_file(
            path_or_fileobj=DATASET_README.encode("utf-8"),
            path_in_repo="README.md",
            repo_id=repo_id,
            repo_type="dataset",
        )


def dataset_repo_files(api, repo_id: str) -> set[str]:
    return set(api.list_repo_files(repo_id=repo_id, repo_type="dataset"))


def dataset_has_submission_results(api, repo_id: str) -> bool:
    return any(path.endswith(".parquet") for path in dataset_repo_files(api, repo_id))


def submission_parquet_files(api, repo_id: str) -> list[str]:
    """Return submission parquet shards in stable sorted order.

    Restricting to the known `data/submissions*.parquet` layout lets the
    Space load leaderboard rows directly from Hub files without asking the
    datasets-server for dataset metadata, which can intermittently 500.
    """
    files = dataset_repo_files(api, repo_id)
    return sorted(path for path in files if path.startswith("data/submissions") and path.endswith(".parquet"))


def load_submission_rows_from_parquet(
    repo_id: str,
    *,
    token: str | None = None,
    api=None,
    downloader=None,
    pandas_module=None,
) -> list[dict[str, Any]]:
    """Load leaderboard rows directly from parquet shards on the Hub.

    This avoids `datasets.load_dataset(...)`, which triggers datasets-server
    metadata lookups (`/info`, `dataset_infos.json`, etc.) and can emit noisy
    500s even when the parquet data itself is healthy.
    """
    if api is None:
        from huggingface_hub import HfApi

        api = HfApi(token=token or None)
    if downloader is None:
        from huggingface_hub import hf_hub_download

        downloader = hf_hub_download
    if pandas_module is None:
        import pandas as pd

        pandas_module = pd

    rows: list[dict[str, Any]] = []
    for path_in_repo in submission_parquet_files(api, repo_id):
        local_path = downloader(
            repo_id=repo_id,
            repo_type="dataset",
            filename=path_in_repo,
            token=token or None,
        )
        frame = pandas_module.read_parquet(Path(local_path))
        rows.extend(frame.to_dict(orient="records"))
    return rows


def _resolve_owner(token: str | None) -> str | None:
    for key in SPACE_REPO_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if "/" in value:
            owner, _space = value.split("/", 1)
            owner = owner.strip()
            if owner:
                return owner

    for key in SPACE_OWNER_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            return value

    trimmed_token = (token or "").strip()
    if not trimmed_token:
        return None

    if trimmed_token in _WHOAMI_CACHE:
        return _WHOAMI_CACHE[trimmed_token]

    owner: str | None = None
    try:
        from huggingface_hub import HfApi

        info = HfApi(token=trimmed_token).whoami(token=trimmed_token, cache=True)
        name = info.get("name")
        owner = str(name).strip() if name else None
    except Exception as exc:
        logger.warning("Failed to resolve HF namespace from token: %s", exc)

    _WHOAMI_CACHE[trimmed_token] = owner
    return owner
