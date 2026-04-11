import json
from pathlib import Path

from click.testing import CliRunner

from clawbench.cli import cli
from clawbench.task_factory import ingest_trace_file


def test_ingest_trace_file_derives_seed_and_template(tmp_path: Path):
    input_path = tmp_path / "traces.json"
    payload = [
        {
            "trace_id": "trace-001",
            "user_prompt": "Search is off somewhere in this Node app. Trace it through the files, fix it, and keep the tests green.",
            "transcript": {
                "messages": [
                    {"role": "user", "text": "Search is off somewhere in this Node app."},
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {"name": "read_file", "input": {"path": "src/search.js"}, "success": True},
                            {"name": "exec_command", "input": {"cmd": "npm test"}, "success": True},
                            {"name": "apply_patch", "input": {"path": "src/search.js"}, "success": True},
                        ],
                    },
                ]
            },
        }
    ]
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    traces, seeds, templates = ingest_trace_file(
        input_path=input_path,
        source_kind="hf_open_trace",
        privacy_tier="public",
        factory_root=tmp_path / "factory",
        emit_templates=True,
    )

    assert len(traces) == 1
    assert len(seeds) == 1
    assert len(templates) == 1
    assert seeds[0].family == "coding"
    assert seeds[0].scenario == "coding_dev_assist"
    assert "bugfix" in seeds[0].capabilities
    assert "tool_composition" in seeds[0].capabilities
    assert templates[0].verifier_hint == "Prefer execution checks with regression tests."
    assert "t1-bugfix-discount" in templates[0].recommended_source_task_ids
    assert (tmp_path / "factory" / "traces" / "trace-001.json").exists()
    assert (tmp_path / "factory" / "seeds" / f"{seeds[0].seed_id}.json").exists()
    assert (tmp_path / "factory" / "templates" / f"{templates[0].template_id}.json").exists()


def test_ingest_traces_cli_and_list_factory(tmp_path: Path):
    runner = CliRunner()
    input_path = tmp_path / "partner.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "trace_id": "trace-xyz",
                "user_prompt": "Set up a monitoring automation and verify it runs cleanly.",
                "transcript": {
                    "messages": [
                        {"role": "user", "text": "Set up a monitoring automation."},
                        {
                            "role": "assistant",
                            "tool_calls": [
                                {"name": "memory_search", "input": {"query": "monitoring"}, "success": True},
                                {"name": "exec_command", "input": {"cmd": "python monitor.py"}, "success": True},
                                {"name": "cron_create", "input": {"schedule": "0 * * * *"}, "success": True},
                            ],
                        },
                    ]
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    factory_root = tmp_path / "factory"

    result = runner.invoke(
        cli,
        [
            "ingest-traces",
            "--input",
            str(input_path),
            "--source-kind",
            "partner_trace",
            "--privacy-tier",
            "partner_restricted",
            "--partner-name",
            "acme",
            "--factory-root",
            str(factory_root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Ingested 1 trace(s) -> 1 seed(s) -> 1 template(s)" in result.output

    list_result = runner.invoke(
        cli,
        [
            "list-factory",
            "--kind",
            "templates",
            "--factory-root",
            str(factory_root),
        ],
    )
    assert list_result.exit_code == 0, list_result.output
    assert "templates: 1 file(s)" in list_result.output


def test_promote_templates_cli_builds_hidden_release(tmp_path: Path, monkeypatch):
    runner = CliRunner()
    input_path = tmp_path / "traces.json"
    input_path.write_text(
        json.dumps(
            [
                {
                    "trace_id": "trace-002",
                    "user_prompt": "Checkout math looks off. Patch the discount bug and make sure the tests are happy.",
                    "transcript": {
                        "messages": [
                            {"role": "user", "text": "Checkout math looks off."},
                            {
                                "role": "assistant",
                                "tool_calls": [
                                    {"name": "read_file", "input": {"path": "shop/cart.py"}, "success": True},
                                    {"name": "exec_command", "input": {"cmd": "pytest -q"}, "success": True},
                                ],
                            },
                        ]
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    factory_root = tmp_path / "factory"
    private_root = tmp_path / "private_tasks"
    active_release_path = tmp_path / "registry" / "active_release.json"
    monkeypatch.setenv("CLAWBENCH_ACTIVE_RELEASE_PATH", str(active_release_path))

    ingest_result = runner.invoke(
        cli,
        [
            "ingest-traces",
            "--input",
            str(input_path),
            "--source-kind",
            "hf_open_trace",
            "--privacy-tier",
            "public",
            "--factory-root",
            str(factory_root),
        ],
    )
    assert ingest_result.exit_code == 0, ingest_result.output

    promote_result = runner.invoke(
        cli,
        [
            "promote-templates",
            "--release-id",
            "rel-2026-04c",
            "--factory-root",
            str(factory_root),
            "--private-tasks-dir",
            str(private_root),
            "--active-release-path",
            str(active_release_path),
        ],
    )
    assert promote_result.exit_code == 0, promote_result.output
    assert "Promoted 1 template-derived task(s)" in promote_result.output

    promoted_files = sorted((private_root / "rel-2026-04c").glob("tier*/*.yaml"))
    assert len(promoted_files) == 1
    promoted_task = promoted_files[0]
    payload = json.loads(active_release_path.read_text(encoding="utf-8"))
    assert payload["hidden_release_id"] == "rel-2026-04c"
    assert payload["task_ids"] == [promoted_task.stem]
    hidden_yaml = promoted_task.read_text(encoding="utf-8")
    assert "pool: official_hidden" in hidden_yaml
    assert "template_id:" in hidden_yaml
    assert "There is an issue somewhere in this workspace." in hidden_yaml
