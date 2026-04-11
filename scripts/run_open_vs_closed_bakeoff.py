#!/usr/bin/env python3
"""Driver for the ClawBench open-source vs closed-source bake-off.

Runs four model profiles against the full 40-task suite with the judge
enabled, records each run through the v0.5 Configuration Diagnostic
pipeline, and publishes ecosystem insights at the end.

Usage:
    python scripts/run_open_vs_closed_bakeoff.py \
        [--runs 3] \
        [--concurrency 6] \
        [--judge-model anthropic/claude-sonnet-4-6] \
        [--gateway-token $OPENCLAW_GATEWAY_TOKEN] \
        [--dry-run]

The four profiles (bundled in profiles/):
    bakeoff_sonnet_4_6.yaml      anthropic/claude-sonnet-4-6    (closed)
    bakeoff_opus_4_6.yaml        anthropic/claude-opus-4-6      (closed)
    bakeoff_qwen3_32b.yaml       huggingface/Qwen/Qwen3-32B     (open)
    bakeoff_deepseek_v3.yaml     huggingface/deepseek-ai/DeepSeek-V3 (open)

All four profiles use an identical plugin stack so the base model is
the only structural variable. The v0.5 fingerprint will reflect this.

Each run invokes `clawbench run --profile` which:
  1. Runs the full 40-task suite at --runs per task
  2. Records the run in .clawbench/historical/profile_runs.json
  3. Publishes ecosystem insights to .clawbench/insights/
  4. Writes a Configuration Diagnostic Report per submission

After all four runs complete, this script writes a comparison table
to results/open_vs_closed_bakeoff_summary.md so you have a single file
to publish or post.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILES_DIR = REPO_ROOT / "profiles"
RESULTS_DIR = REPO_ROOT / "results"
HISTORICAL_DB = REPO_ROOT / ".clawbench" / "historical" / "profile_runs.json"


@dataclass
class BakeoffProfile:
    profile_path: Path
    model: str
    category: str  # "closed" or "open"
    display_name: str


BAKEOFF: list[BakeoffProfile] = [
    BakeoffProfile(
        profile_path=PROFILES_DIR / "frontier_opus_4_6.yaml",
        model="anthropic/claude-opus-4-6",
        category="closed",
        display_name="Claude Opus 4.6",
    ),
    BakeoffProfile(
        profile_path=PROFILES_DIR / "frontier_gpt_5_4.yaml",
        model="openai/gpt-5.4",
        category="closed",
        display_name="GPT-5.4",
    ),
    BakeoffProfile(
        profile_path=PROFILES_DIR / "frontier_gemini_3_pro.yaml",
        model="google/gemini-3.1-pro-preview",
        category="closed",
        display_name="Gemini 3.1 Pro",
    ),
    BakeoffProfile(
        profile_path=PROFILES_DIR / "frontier_glm_5_1.yaml",
        model="openrouter/z-ai/glm-5.1",
        category="open",
        display_name="GLM-5.1",
    ),
    BakeoffProfile(
        profile_path=PROFILES_DIR / "frontier_qwen_3_6.yaml",
        model="openrouter/qwen/qwen-3.6-plus",
        category="open",
        display_name="Qwen3.6-Plus",
    ),
    BakeoffProfile(
        profile_path=PROFILES_DIR / "frontier_minimax_m27.yaml",
        model="openrouter/minimax/minimax-m2.7",
        category="open",
        display_name="MiniMax M2.7",
    ),
    BakeoffProfile(
        profile_path=PROFILES_DIR / "frontier_kimi_k25.yaml",
        model="openrouter/moonshotai/kimi-k2.5",
        category="open",
        display_name="Kimi K2.5",
    ),
]


def run_one(
    profile: BakeoffProfile,
    *,
    runs: int,
    concurrency: int,
    judge_model: str,
    gateway_token: str,
    python_bin: str,
    dry_run: bool,
    tasks: list[str] | None = None,
) -> Path:
    """Invoke `clawbench run --profile` for one model.

    The clawbench package does not ship a `__main__.py`, so `python -m
    clawbench.cli` is a no-op (defines `main` but never calls it). We
    invoke the CLI via an inline `-c` that drives the Click group
    directly — this is the same path `pyproject.toml` uses for the
    installed `clawbench` script entry point.
    """
    output = RESULTS_DIR / f"{profile.profile_path.stem}.json"
    args = [
        "run",
        "--model",
        profile.model,
        "--runs",
        str(runs),
        "--concurrency",
        str(concurrency),
        "--browser-concurrency",
        "1",
        "--judge-model",
        judge_model,
        "--gateway-token",
        gateway_token,
        "--profile",
        str(profile.profile_path),
        "--output",
        str(output),
    ]
    for task_id in (tasks or []):
        args.extend(["--task", task_id])
    cmd = [
        python_bin,
        "-c",
        f"from clawbench.cli import cli; cli({args!r}, standalone_mode=False)",
    ]
    print(
        f"\n{'━' * 70}\n  [{profile.category.upper():6}] "
        f"{profile.display_name}  ({profile.model})\n{'━' * 70}"
    )
    print("  →", " ".join(cmd))
    if dry_run:
        print("  (dry run — not executing)")
        return output

    env = os.environ.copy()
    if gateway_token:
        env["OPENCLAW_GATEWAY_TOKEN"] = gateway_token

    proc = subprocess.run(cmd, cwd=REPO_ROOT, env=env)
    if proc.returncode != 0:
        print(
            f"  ! run for {profile.display_name} exited with code "
            f"{proc.returncode}",
            file=sys.stderr,
        )
    return output


def extract_summary(result_path: Path) -> dict:
    """Pull the headline fields we need for the comparison table."""
    if not result_path.exists():
        return {"error": "result file missing", "path": str(result_path)}
    try:
        data = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": f"parse error: {exc}", "path": str(result_path)}
    return {
        "model": data.get("model", ""),
        "overall_score": data.get("overall_score"),
        "overall_completion": data.get("overall_completion"),
        "overall_trajectory": data.get("overall_trajectory"),
        "overall_behavior": data.get("overall_behavior"),
        "overall_reliability": data.get("overall_reliability"),
        "overall_pass_hat_k": data.get("overall_pass_hat_k"),
        "overall_judge_score": data.get("overall_judge_score"),
        "judge_task_coverage": data.get("judge_task_coverage"),
        "overall_median_latency_ms": data.get("overall_median_latency_ms"),
        "overall_tokens_per_pass": data.get("overall_tokens_per_pass"),
        "overall_cost_per_pass": data.get("overall_cost_per_pass"),
        "hard_subset_score": data.get("hard_subset_score"),
        "consensus_subset_score": data.get("consensus_subset_score"),
        "n_tasks": len(data.get("task_results", [])),
    }


def fmt(v, digits: int = 3) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.{digits}f}"
    except (TypeError, ValueError):
        return str(v)


def fmt_pct(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return str(v)


def fmt_dollar(v) -> str:
    if v is None:
        return "—"
    try:
        return f"${float(v):.4f}"
    except (TypeError, ValueError):
        return str(v)


def fmt_int(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{int(round(float(v))):,}"
    except (TypeError, ValueError):
        return str(v)


def write_comparison_table(
    profiles: Iterable[BakeoffProfile],
    summaries: dict[str, dict],
    output_path: Path,
) -> None:
    """Render the four-model open-vs-closed comparison as a markdown file."""
    profiles = list(profiles)
    lines: list[str] = []
    lines.append("# ClawBench Open-Source vs Closed-Source Bake-off")
    lines.append("")
    lines.append(
        "All four profiles share an **identical plugin stack** "
        "(`anthropic` + `memory-lancedb` + `browser-playwright`) "
        "so the base model is the only structural variable."
    )
    lines.append("")
    lines.append("## Headline")
    lines.append("")
    header = (
        "| Metric | "
        + " | ".join(f"{p.display_name}<br/>*{p.category}*" for p in profiles)
        + " |"
    )
    lines.append(header)
    lines.append("|---" + "|---:" * len(profiles) + "|")

    rows = [
        ("Overall score", "overall_score", fmt),
        ("Completion (deterministic)", "overall_completion", fmt),
        ("Trajectory (deterministic)", "overall_trajectory", fmt),
        ("Behavior (deterministic)", "overall_behavior", fmt),
        ("Reliability", "overall_reliability", fmt),
        ("pass^k", "overall_pass_hat_k", fmt_pct),
        ("Judge score", "overall_judge_score", fmt),
        ("Judge coverage", "judge_task_coverage", fmt_pct),
        ("Hard subset", "hard_subset_score", fmt),
        ("Consensus subset", "consensus_subset_score", fmt),
        ("Median latency (ms)", "overall_median_latency_ms", fmt_int),
        ("Tokens / pass", "overall_tokens_per_pass", fmt_int),
        ("Cost / pass", "overall_cost_per_pass", fmt_dollar),
    ]
    for label, key, formatter in rows:
        values = [formatter(summaries[p.display_name].get(key)) for p in profiles]
        lines.append(f"| {label} | " + " | ".join(values) + " |")

    lines.append("")
    lines.append("## Category aggregates")
    lines.append("")
    closed = [
        s for p in profiles if p.category == "closed"
        for s in [summaries[p.display_name]]
        if s.get("overall_score") is not None
    ]
    open_ = [
        s for p in profiles if p.category == "open"
        for s in [summaries[p.display_name]]
        if s.get("overall_score") is not None
    ]

    def mean(seq, key):
        vals = [s[key] for s in seq if s.get(key) is not None]
        return sum(vals) / len(vals) if vals else None

    lines.append("| | Closed (mean) | Open (mean) | Gap (closed − open) |")
    lines.append("|---|---:|---:|---:|")
    for label, key, formatter in [
        ("Overall score", "overall_score", fmt),
        ("Completion", "overall_completion", fmt),
        ("Reliability", "overall_reliability", fmt),
        ("Cost / pass", "overall_cost_per_pass", fmt_dollar),
    ]:
        c = mean(closed, key)
        o = mean(open_, key)
        gap = (c - o) if (c is not None and o is not None) else None
        lines.append(
            f"| {label} | {formatter(c)} | {formatter(o)} | "
            f"{('+' + formatter(gap)) if gap is not None and gap >= 0 else formatter(gap)} |"
        )

    lines.append("")
    lines.append("## Sources")
    lines.append("")
    for p in profiles:
        result_path = RESULTS_DIR / f"bakeoff_{p.profile_path.stem}.json"
        lines.append(
            f"- **{p.display_name}** ({p.category}): `{result_path.relative_to(REPO_ROOT)}`"
        )
    lines.append("")
    lines.append("## v0.5 Diagnostic")
    lines.append("")
    lines.append(
        "Each run was recorded through the v0.5 Configuration Diagnostic "
        "pipeline. See `.clawbench/historical/profile_runs.json` for the "
        "fingerprint database and `.clawbench/insights/` for the "
        "ecosystem-level plugin leaderboard, factor importance, and "
        "calibration metrics refreshed after every submission."
    )
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✓ wrote comparison table → {output_path.relative_to(REPO_ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ClawBench open-source vs closed-source bake-off driver"
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Runs per task. v0.4 spec §'Official Run Policy' mandates ≥3.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=6,
        help="Parallel (task, run) workers against the gateway.",
    )
    parser.add_argument(
        "--judge-model",
        default="anthropic/claude-sonnet-4-6",
        help="LLM judge model (same for all four runs so the judge side is held constant).",
    )
    parser.add_argument(
        "--gateway-token",
        default=os.environ.get("OPENCLAW_GATEWAY_TOKEN", ""),
        help="Gateway auth token (defaults to $OPENCLAW_GATEWAY_TOKEN).",
    )
    parser.add_argument(
        "--python-bin",
        default=str(REPO_ROOT / ".venv" / "bin" / "python"),
        help="Python interpreter used to invoke clawbench.cli.",
    )
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        help="Display name of a profile to skip (e.g. 'Opus 4.6'). May be repeated.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Run only the named profile(s). May be repeated.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the command for each run but do not execute.",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Skip running; re-read existing result files and regenerate the comparison table.",
    )
    parser.add_argument(
        "--task",
        action="append",
        default=[],
        help="Run only these task IDs (may be repeated). Defaults to the full suite.",
    )
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    selected: list[BakeoffProfile] = []
    for p in BAKEOFF:
        if args.only and p.display_name not in args.only:
            continue
        if p.display_name in args.skip:
            continue
        selected.append(p)

    if not selected:
        print("no profiles selected; nothing to do", file=sys.stderr)
        sys.exit(1)

    print(
        f"\nClawBench open-vs-closed bake-off\n"
        f"  runs/task:     {args.runs}\n"
        f"  concurrency:   {args.concurrency}\n"
        f"  judge:         {args.judge_model}\n"
        f"  profiles:      {len(selected)} "
        f"({sum(1 for p in selected if p.category == 'closed')} closed, "
        f"{sum(1 for p in selected if p.category == 'open')} open)\n"
    )

    result_paths: dict[str, Path] = {}
    if args.summary_only:
        for p in selected:
            result_paths[p.display_name] = (
                RESULTS_DIR / f"bakeoff_{p.profile_path.stem}.json"
            )
    else:
        for p in selected:
            result_paths[p.display_name] = run_one(
                p,
                runs=args.runs,
                concurrency=args.concurrency,
                judge_model=args.judge_model,
                gateway_token=args.gateway_token,
                python_bin=args.python_bin,
                dry_run=args.dry_run,
                tasks=args.task or None,
            )

    if args.dry_run:
        print(
            "\ndry run complete. Re-run without --dry-run to execute.\n"
            "Budget estimate (3 runs × 40 tasks × 4 models × $0.05 avg/pass ≈ $24 + gateway time)."
        )
        return

    summaries = {
        p.display_name: extract_summary(result_paths[p.display_name])
        for p in selected
    }
    summary_path = RESULTS_DIR / "open_vs_closed_bakeoff_summary.md"
    write_comparison_table(selected, summaries, summary_path)

    print(
        "\nAll runs complete. Ecosystem insights refreshed in "
        f"{(REPO_ROOT / '.clawbench' / 'insights').relative_to(REPO_ROOT)}/."
    )


if __name__ == "__main__":
    main()
