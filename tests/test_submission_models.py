from clawbench.submission_models import (
    CUSTOM_PRESET_LABEL,
    PRESET_AUDIENCE_BUDGET,
    PRESET_AUDIENCE_CLAW,
    infer_provider,
    preset_labels_for_audience,
    resolve_model_selection,
)


def test_budget_audience_keeps_budget_friendly_presets():
    labels = preset_labels_for_audience(PRESET_AUDIENCE_BUDGET)

    assert "GPT-OSS 20B (Ollama)" in labels
    assert "Qwen 3.5 27B (Ollama)" in labels
    assert "Claude Opus 4.6" not in labels


def test_claw_audience_keeps_full_catalog():
    labels = preset_labels_for_audience(PRESET_AUDIENCE_CLAW)

    assert "GPT-OSS 20B (Ollama)" in labels
    assert "Claude Opus 4.6" in labels


def test_resolve_model_selection_prefers_preset_provider():
    model_id, provider = resolve_model_selection("", "GPT-OSS 20B (Ollama)")

    assert model_id == "ollama/gpt-oss:20b"
    assert provider == "ollama"


def test_resolve_model_selection_infers_custom_provider():
    model_id, provider = resolve_model_selection(
        "huggingface/Qwen/Qwen3-32B",
        CUSTOM_PRESET_LABEL,
    )

    assert model_id == "huggingface/Qwen/Qwen3-32B"
    assert provider == "huggingface"


def test_infer_provider_requires_provider_prefix():
    assert infer_provider("qwen3.5:27b") == ""