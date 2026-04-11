"""Dataset-backed query benchmark metadata for the current task suite."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DATASET_SOURCE = "basic_usage_query_suite_v1"

SCENARIO_WEIGHT_DEFAULTS: dict[str, float] = {
    # Original 12 scenarios from the basic-usage query test sheet
    "file_system_ops": 0.10,
    "web_info_ops": 0.08,
    "calendar_reminders": 0.06,
    "communication_messaging": 0.08,
    "data_processing_analysis": 0.09,
    "coding_dev_assist": 0.07,
    "personal_life_assistant": 0.06,
    "multi_step_compound": 0.10,
    "context_continuation": 0.05,
    "error_boundary_cases": 0.05,
    "skill_calling": 0.06,
    "system_capabilities": 0.04,
    # v0.5 additions: high-frequency personal-agent scenarios beyond the sheet
    "privacy_pii_handling": 0.04,
    "personal_financial_hygiene": 0.03,
    "travel_logistics_under_uncertainty": 0.03,
    "social_coordination": 0.02,
    "personal_knowledge_base": 0.02,
    "health_wellness_tracking": 0.01,
    "account_security_hygiene": 0.01,
    "multimodal_understanding": 0.00,
}


TASK_QUERY_OVERRIDES: dict[str, dict[str, Any]] = {
    "t1-architecture-brief": {
        "scenario": "coding_dev_assist",
        "subscenario": "codebase_summarization",
        "atomic_capabilities": ["read_project_files", "extract_repo_facts", "write_structured_artifact"],
        "query_difficulty": "l1",
        "artifact_type": "file",
        "preconditions": ["workspace_available"],
        "turn_variants": {
            "main": {
                0: {
                    "ambiguous": "Can you get me the architecture JSON this little shop repo expects? Take a quick pass through it and do not break anything."
                }
            }
        },
    },
    "t1-bugfix-discount": {
        "scenario": "coding_dev_assist",
        "subscenario": "bug_fixing",
        "atomic_capabilities": ["inspect_code", "patch_logic", "run_regression_tests"],
        "query_difficulty": "l2",
        "artifact_type": "code",
        "preconditions": ["workspace_available", "pytest_available"],
        "turn_variants": {
            "main": {
                0: {
                    "ambiguous": "Checkout math looks off. Patch the discount bug and make sure the tests are happy."
                }
            }
        },
    },
    "t1-refactor-csv-loader": {
        "scenario": "coding_dev_assist",
        "subscenario": "refactor_without_regression",
        "atomic_capabilities": ["read_existing_logic", "deduplicate_code", "verify_behavior"],
        "query_difficulty": "l2",
        "artifact_type": "code",
        "preconditions": ["workspace_available", "pytest_available"],
        "turn_variants": {
            "main": {
                0: {
                    "ambiguous": "The CSV loading path is duplicated. Clean it up, but behavior cannot drift."
                }
            }
        },
    },
    "t2-add-tests-normalizer": {
        "scenario": "coding_dev_assist",
        "subscenario": "test_authoring",
        "atomic_capabilities": ["read_module_behavior", "author_missing_tests", "verify_coverage_targets"],
        "query_difficulty": "l2",
        "artifact_type": "code",
        "preconditions": ["workspace_available", "pytest_available"],
        "turn_variants": {
            "main": {
                0: {
                    "ambiguous": "There are barely any trustworthy tests around this normalizer. Add the important ones and prove they hold."
                }
            }
        },
    },
    "t2-log-analyzer-cli": {
        "scenario": "data_processing_analysis",
        "subscenario": "structured_log_summarization",
        "atomic_capabilities": ["parse_logs", "aggregate_metrics", "emit_exact_json"],
        "query_difficulty": "l2",
        "artifact_type": "code",
        "preconditions": ["workspace_available"],
        "turn_variants": {
            "main": {
                0: {
                    "ambiguous": "Need a small CLI here that turns the sample logs into the exact JSON summary we want."
                }
            }
        },
    },
    "t2-config-loader": {
        "scenario": "coding_dev_assist",
        "subscenario": "config_precedence",
        "atomic_capabilities": ["merge_defaults_file_env", "validate_inputs", "run_tests"],
        "query_difficulty": "l2",
        "artifact_type": "code",
        "preconditions": ["workspace_available", "pytest_available"],
        "turn_variants": {
            "main": {
                0: {
                    "ambiguous": "Config precedence is messy right now. Make defaults, file values, and env overrides behave properly and validate it."
                }
            }
        },
    },
    "t2-node-search-patch": {
        "scenario": "coding_dev_assist",
        "subscenario": "node_bug_fixing",
        "atomic_capabilities": ["trace_multifile_bug", "patch_node_logic", "run_node_tests"],
        "query_difficulty": "l2",
        "artifact_type": "code",
        "preconditions": ["workspace_available", "node_test_runner_available"],
        "turn_variants": {
            "main": {
                0: {
                    "ambiguous": "Search is off somewhere in this Node app. Trace it through the files, fix it, and keep the tests green."
                }
            }
        },
    },
    "t2-browser-form-fix": {
        "scenario": "web_info_ops",
        "subscenario": "form_completion_and_debugging",
        "atomic_capabilities": ["inspect_local_page", "diagnose_submission_failure", "verify_form_success"],
        "query_difficulty": "l3",
        "artifact_type": "external_action",
        "preconditions": ["local_browser_service_available", "task_http_service_available"],
        "turn_variants": {
            "main": {
                0: {
                    "ambiguous": "The local demo form is busted. Use the browser, figure out why it will not submit, fix it, and confirm it works."
                }
            }
        },
    },
    "t3-feature-export": {
        "scenario": "coding_dev_assist",
        "subscenario": "feature_implementation",
        "atomic_capabilities": ["thread_feature_across_files", "extend_cli_surface", "verify_regressions"],
        "query_difficulty": "l2",
        "artifact_type": "code",
        "preconditions": ["workspace_available", "pytest_available"],
        "turn_variants": {
            "main": {
                0: {
                    "ambiguous": "Need CSV export wired into this issue tracker. Thread it through and make sure the suite and CLI still behave."
                }
            }
        },
    },
    "t3-node-multifile-refactor": {
        "scenario": "coding_dev_assist",
        "subscenario": "shared_logic_centralization",
        "atomic_capabilities": ["identify_shared_logic", "refactor_modules", "verify_node_tests"],
        "query_difficulty": "l2",
        "artifact_type": "code",
        "preconditions": ["workspace_available", "node_test_runner_available"],
        "turn_variants": {
            "main": {
                0: {
                    "ambiguous": "There is shared parsing, auth, and date logic scattered around. Centralize it without breaking the Node app."
                }
            }
        },
    },
    "t3-debug-timezone-regression": {
        "scenario": "coding_dev_assist",
        "subscenario": "regression_debugging",
        "atomic_capabilities": ["reproduce_failure", "isolate_time_or_cache_issue", "verify_suite"],
        "query_difficulty": "l3",
        "artifact_type": "code",
        "preconditions": ["workspace_available", "pytest_available"],
        "turn_variants": {
            "main": {
                0: {
                    "ambiguous": "Something around timezone or caching regressed. Hunt it down and get the Python tests happy again."
                }
            }
        },
    },
    "t3-data-pipeline-report": {
        "scenario": "data_processing_analysis",
        "subscenario": "etl_report_pipeline",
        "atomic_capabilities": ["ingest_structured_inputs", "run_transform_steps", "produce_expected_report"],
        "query_difficulty": "l3",
        "artifact_type": "mixed",
        "preconditions": ["workspace_available"],
        "turn_variants": {
            "main": {
                0: {
                    "ambiguous": "Build the pipeline so these input files roll up into the exact report output we are expecting."
                }
            }
        },
    },
    "t3-monitoring-automation": {
        "scenario": "system_capabilities",
        "subscenario": "automation_setup",
        "atomic_capabilities": ["implement_health_check", "register_cron_job", "verify_runtime_state"],
        "query_difficulty": "l2",
        "artifact_type": "automation",
        "preconditions": ["workspace_available", "cron_tool_available"],
        "turn_variants": {
            "main": {
                0: {
                    "ambiguous": "Set up the health-check script and schedule it through cron so the monitoring flow is actually in place."
                }
            }
        },
    },
    "t4-delegation-repair": {
        "scenario": "multi_step_compound",
        "subscenario": "parallel_repairs",
        "atomic_capabilities": ["split_work", "delegate_repairs", "merge_and_verify"],
        "query_difficulty": "l3",
        "artifact_type": "code",
        "preconditions": ["workspace_available", "delegate_tool_available"],
        "turn_variants": {
            "main": {
                0: {
                    "ambiguous": "This repair naturally splits in two. Use delegation, land both fixes, and make sure the final suite passes."
                }
            }
        },
    },
    "t4-cross-repo-migration": {
        "scenario": "multi_step_compound",
        "subscenario": "cross_repo_contract_change",
        "atomic_capabilities": ["inspect_two_repos", "migrate_contract", "verify_both_suites"],
        "query_difficulty": "l3",
        "artifact_type": "code",
        "preconditions": ["workspace_available"],
        "turn_variants": {
            "main": {
                0: {
                    "ambiguous": "There is a renamed contract spanning two local repos. Migrate both sides so they agree again."
                }
            }
        },
    },
    "t4-memory-recall-continuation": {
        "scenario": "context_continuation",
        "subscenario": "memory_handoff",
        "atomic_capabilities": ["store_relevant_memory", "leave_handoff_artifact", "resume_with_missing_context"],
        "query_difficulty": "l3",
        "artifact_type": "memory",
        "preconditions": ["workspace_available", "memory_tool_available"],
        "turn_variants": {
            "prep": {
                0: {
                    "ambiguous": "Read the rollout notes, stash the important beta details somewhere you can use later, and leave a handoff note. Do not touch flags yet."
                }
            },
            "implementation": {
                0: {
                    "ambiguous": "Pick this back up from your earlier notes and fix flags.py. I am not repeating the rollout details."
                }
            },
        },
    },
    "t4-browser-research-and-code": {
        "scenario": "multi_step_compound",
        "subscenario": "research_then_implement",
        "atomic_capabilities": ["browse_local_docs", "infer_api_change", "patch_code_and_verify"],
        "query_difficulty": "l3",
        "artifact_type": "code",
        "preconditions": ["local_browser_service_available", "workspace_available"],
        "turn_variants": {
            "main": {
                0: {
                    "ambiguous": "Browse the local docs, work out what changed in the API, then patch the codebase to match."
                }
            }
        },
    },
    "t5-impossible-graceful-fail": {
        "scenario": "error_boundary_cases",
        "subscenario": "impossible_request_handling",
        "atomic_capabilities": ["detect_missing_capability", "avoid_harmful_mutation", "communicate_clean_blocker"],
        "query_difficulty": "l2",
        "artifact_type": "information",
        "preconditions": ["workspace_available"],
        "turn_variants": {
            "main": {
                0: {
                    "ambiguous": "See if you can do this with what you have, but if you cannot, handle it cleanly and do not make a mess."
                }
            }
        },
    },
    "t5-contradictory-requirements": {
        "scenario": "error_boundary_cases",
        "subscenario": "instruction_revision",
        "atomic_capabilities": ["track_latest_requirement", "remove_stale_output", "verify_final_state"],
        "query_difficulty": "l3",
        "artifact_type": "mixed",
        "preconditions": ["workspace_available"],
        "turn_variants": {
            "main": {
                0: {
                    "ambiguous": "Requirements may shift under you. End up with the latest thing I asked for and clean out any stale output."
                }
            }
        },
    },
    "t5-hallucination-resistant-evidence": {
        "scenario": "web_info_ops",
        "subscenario": "evidence_grounded_answering",
        "atomic_capabilities": ["read_local_sources", "avoid_unsupported_claims", "produce_evidence_artifact"],
        "query_difficulty": "l3",
        "artifact_type": "mixed",
        "preconditions": ["workspace_available", "local_browser_service_available"],
        "turn_variants": {
            "main": {
                0: {
                    "ambiguous": "Answer only from the local material and leave behind a precise evidence artifact."
                }
            }
        },
    },
}


def apply_query_metadata_overrides(data: dict[str, Any]) -> dict[str, Any]:
    task_id = str(data.get("id", ""))
    override = TASK_QUERY_OVERRIDES.get(task_id)
    if not override:
        return data

    merged = deepcopy(data)
    turn_variants = override.get("turn_variants", {})
    for key, value in override.items():
        if key == "turn_variants":
            continue
        merged.setdefault(key, value)

    if merged.get("scenario") and "query_weight" not in merged:
        merged["query_weight"] = SCENARIO_WEIGHT_DEFAULTS.get(str(merged["scenario"]), 1.0)
    merged.setdefault("source_dataset", DATASET_SOURCE)

    if turn_variants:
        prompt_variants = list(merged.get("prompt_variants") or ["clear"])
        if "ambiguous" not in prompt_variants:
            prompt_variants.append("ambiguous")
        merged["prompt_variants"] = prompt_variants
        if merged.get("phases"):
            for phase in merged["phases"]:
                phase_name = str(phase.get("name", "main"))
                _apply_turn_overrides(phase.get("user"), turn_variants.get(phase_name, {}))
        else:
            _apply_turn_overrides(merged.get("user"), turn_variants.get("main", {}))

    return merged


def _apply_turn_overrides(user_block: dict[str, Any] | None, turn_overrides: dict[int, dict[str, str]]) -> None:
    if not user_block or not turn_overrides:
        return
    turns = user_block.get("turns")
    if not isinstance(turns, list):
        return
    for index, variant_messages in turn_overrides.items():
        if not isinstance(index, int) or index >= len(turns):
            continue
        turn = turns[index]
        existing = dict(turn.get("variant_messages") or {})
        existing.update(variant_messages)
        turn["variant_messages"] = existing
