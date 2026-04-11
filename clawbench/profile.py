"""ClawBench v0.5 — Plugin Profile and Manifest Feature extraction.

This module implements the structural side of the configuration-space
benchmarking framework defined in CLAWBENCH_V0_4_SPEC.md (v0.5 Direction).

A Plugin Profile describes the full agent configuration that ClawBench
evaluates: base model + enabled plugins + slot fills + tool allowlist.

A Manifest Feature Vector is computed mechanically from a plugin's
openclaw.plugin.json manifest plus its registration trace. The feature
vector has the same shape for every plugin — bundled, ClawHub-installed,
or custom — so the framework generalizes to plugins it has never seen.

A Profile Fingerprint aggregates all plugin feature vectors in a profile
into a structural summary used for similarity search, prediction, and
factor importance analysis.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Hook surface — must mirror OpenClaw's plugin hook contract.
# Source: openclaw/src/plugins/types.ts (PluginHookName).
# Listed explicitly so feature extraction never silently drops a hook.
# ---------------------------------------------------------------------------

KNOWN_HOOKS: tuple[str, ...] = (
    "before_model_resolve",
    "before_prompt_build",
    "before_agent_start",
    "before_agent_reply",
    "agent_end",
    "session_start",
    "session_end",
    "gateway_start",
    "gateway_stop",
    "llm_input",
    "llm_output",
    "before_tool_call",
    "after_tool_call",
    "before_compaction",
    "after_compaction",
    "inbound_claim",
    "message_received",
    "message_sending",
    "message_sent",
    "before_message_write",
    "before_dispatch",
    "reply_dispatch",
    "before_reset",
    "subagent_spawning",
    "subagent_delivery_target",
    "subagent_spawned",
    "subagent_ended",
    "before_install",
)

# Tool families used by ClawBench's trajectory classifier — same vocabulary
# as clawbench/trajectory.py:classify_tool_call so the fingerprint speaks
# the same language as the run trajectory analysis.
TOOL_FAMILIES: tuple[str, ...] = (
    "read",
    "edit",
    "search",
    "execute",
    "browser",
    "memory",
    "delegate",
    "cron",
    "plan",
    "unknown",
)

# Manifest contract types — mirror PluginManifestContracts from
# openclaw/src/plugins/types.ts.
CONTRACT_KEYS: tuple[str, ...] = (
    "tools",
    "memoryEmbeddingProviders",
    "speechProviders",
    "realtimeTranscriptionProviders",
    "realtimeVoiceProviders",
    "mediaUnderstandingProviders",
    "imageGenerationProviders",
    "videoGenerationProviders",
    "musicGenerationProviders",
    "webFetchProviders",
    "webSearchProviders",
)


# ---------------------------------------------------------------------------
# Plugin Manifest model
# ---------------------------------------------------------------------------


@dataclass
class PluginManifest:
    """Subset of openclaw.plugin.json fields that the fingerprint needs."""

    id: str
    kind: list[str] = field(default_factory=list)
    contracts: dict[str, list[str]] = field(default_factory=dict)
    channels: list[str] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    capability_tags: list[str] = field(default_factory=list)
    clawhub_channel: str = "bundled"
    clawhub_is_official: bool = False
    version: str = ""

    @classmethod
    def from_file(cls, path: Path) -> PluginManifest:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginManifest:
        kind_raw = data.get("kind", [])
        if isinstance(kind_raw, str):
            kind = [kind_raw]
        elif isinstance(kind_raw, list):
            kind = list(kind_raw)
        else:
            kind = []

        contracts_raw = data.get("contracts", {}) or {}
        contracts: dict[str, list[str]] = {}
        for key in CONTRACT_KEYS:
            value = contracts_raw.get(key)
            if isinstance(value, list):
                contracts[key] = [str(v) for v in value]
            else:
                contracts[key] = []

        return cls(
            id=str(data.get("id", "")),
            kind=kind,
            contracts=contracts,
            channels=list(data.get("channels", []) or []),
            providers=list(data.get("providers", []) or []),
            skills=list(data.get("skills", []) or []),
            capability_tags=list(data.get("capabilityTags", []) or []),
            clawhub_channel=str(data.get("clawhub_channel", "bundled")),
            clawhub_is_official=bool(data.get("clawhub_is_official", False)),
            version=str(data.get("version", "")),
        )


# ---------------------------------------------------------------------------
# Registration Trace — what a plugin actually registered at runtime.
# Captured from the gateway's plugin registry after the plugin loads.
# ---------------------------------------------------------------------------


@dataclass
class RegistrationTrace:
    """Records what a plugin registered when its register() was called."""

    plugin_id: str
    tools: list[str] = field(default_factory=list)  # tool names
    tool_families_seen: list[str] = field(default_factory=list)  # classified
    hooks: list[str] = field(default_factory=list)  # hook event names
    gateway_methods: list[str] = field(default_factory=list)
    http_routes: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    cli_commands: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Plugin Feature Vector — computed for ANY plugin, seen or unseen.
# This is the heart of why the framework generalizes: every plugin yields
# the same shape vector regardless of implementation.
# ---------------------------------------------------------------------------


def plugin_feature_vector(
    manifest: PluginManifest,
    trace: RegistrationTrace | None = None,
) -> dict[str, Any]:
    """Build the typed feature vector for one plugin.

    Parameters
    ----------
    manifest : PluginManifest
        The plugin's manifest, parsed from openclaw.plugin.json.
    trace : RegistrationTrace | None
        Optional registration trace observed at runtime. If None, the
        feature vector is built purely from the manifest (cheap path,
        usable before the plugin loads).

    Returns
    -------
    dict[str, Any]
        A feature dict with the same keys for every plugin.
    """
    trace = trace or RegistrationTrace(plugin_id=manifest.id)

    features: dict[str, Any] = {
        "plugin_id": manifest.id,
        "version": manifest.version,
        "clawhub_channel": manifest.clawhub_channel,
        "clawhub_is_official": manifest.clawhub_is_official,
    }

    # Contract presence (boolean per contract type)
    for key in CONTRACT_KEYS:
        features[f"provides_{_snake(key)}"] = bool(manifest.contracts.get(key))
    # Tool count from contracts
    features["provides_tools_count"] = len(manifest.contracts.get("tools", []))

    # Kind flags
    features["provides_memory"] = "memory" in manifest.kind
    features["provides_context_engine"] = "context-engine" in manifest.kind

    # Counts of higher-level capabilities
    features["n_channels"] = len(manifest.channels)
    features["n_providers"] = len(manifest.providers)
    features["n_skills"] = len(manifest.skills)
    features["n_capability_tags"] = len(manifest.capability_tags)
    features["capability_tags"] = sorted(manifest.capability_tags)

    # Hook footprint (one column per known hook)
    trace_hooks = set(trace.hooks)
    for hook in KNOWN_HOOKS:
        features[f"hooks_{hook}"] = hook in trace_hooks
    features["n_hooks"] = sum(1 for h in KNOWN_HOOKS if h in trace_hooks)

    # Tool family surface
    trace_families = set(trace.tool_families_seen)
    for family in TOOL_FAMILIES:
        features[f"tool_family_{family}"] = family in trace_families
    features["n_tool_families"] = len(trace_families)

    # Surface area
    features["n_tools_registered"] = len(trace.tools)
    features["registers_gateway_methods"] = bool(trace.gateway_methods)
    features["registers_http_routes"] = bool(trace.http_routes)
    features["registers_services"] = bool(trace.services)
    features["registers_cli_commands"] = bool(trace.cli_commands)

    return features


def _snake(camel: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", camel).lower()


# ---------------------------------------------------------------------------
# Plugin Profile — what a benchmark submission looks like.
# ---------------------------------------------------------------------------


@dataclass
class PluginProfileEntry:
    id: str
    source: str = "bundled"  # "bundled" | "clawhub" | "local"
    config: dict[str, Any] = field(default_factory=dict)
    version: str = ""


@dataclass
class PluginProfile:
    name: str
    base_model: str
    plugins: list[PluginProfileEntry] = field(default_factory=list)
    slots: dict[str, str] = field(default_factory=dict)
    tools_allow: list[str] = field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_yaml_file(cls, path: Path) -> PluginProfile:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginProfile:
        if "profile" in data:
            data = data["profile"]

        plugins_raw = data.get("plugins", {})
        if isinstance(plugins_raw, dict):
            entries_raw = plugins_raw.get("enabled", [])
            slots = plugins_raw.get("slots", {}) or {}
            tools_allow = plugins_raw.get("tools_allow", []) or []
        else:
            entries_raw = plugins_raw or []
            slots = {}
            tools_allow = []

        entries: list[PluginProfileEntry] = []
        for raw in entries_raw:
            if isinstance(raw, str):
                entries.append(_entry_from_id(raw))
            elif isinstance(raw, dict):
                pid = str(raw.get("id", ""))
                if not pid:
                    continue
                entry = _entry_from_id(pid)
                if "config" in raw and isinstance(raw["config"], dict):
                    entry.config = dict(raw["config"])
                if "version" in raw:
                    entry.version = str(raw["version"])
                entries.append(entry)

        return cls(
            name=str(data.get("name", "unnamed-profile")),
            base_model=str(data.get("base_model", "")),
            plugins=entries,
            slots=dict(slots),
            tools_allow=list(tools_allow),
            notes=str(data.get("notes", "")),
        )


def _entry_from_id(raw_id: str) -> PluginProfileEntry:
    """Parse `bundled-id`, `clawhub:pkg@1.2`, or `local:./path` notations."""
    if raw_id.startswith("clawhub:"):
        rest = raw_id[len("clawhub:"):]
        if "@" in rest:
            pid, version = rest.split("@", 1)
        else:
            pid, version = rest, ""
        return PluginProfileEntry(id=pid, source="clawhub", version=version)
    if raw_id.startswith("local:"):
        return PluginProfileEntry(id=raw_id[len("local:"):], source="local")
    return PluginProfileEntry(id=raw_id, source="bundled")


# ---------------------------------------------------------------------------
# Profile Fingerprint — aggregated structural summary of a profile.
# Two profiles with the same fingerprint should score similarly.
# ---------------------------------------------------------------------------


@dataclass
class ProfileFingerprint:
    """Structural summary of a Plugin Profile.

    The fingerprint is computed by aggregating per-plugin feature vectors
    plus profile-level features (base model, slot fills, tool allowlist).
    """

    profile_name: str
    base_model: str
    capability_coverage: list[str]  # union of contract types present
    hook_footprint: list[str]  # union of hooks intercepted
    tool_family_surface: list[str]  # union of tool families
    capability_tags_union: list[str]  # union of clawhub tags
    memory_slot: str
    context_engine_slot: str
    n_plugins: int
    n_clawhub_plugins: int
    n_custom_plugins: int
    n_official_plugins: int
    n_tools_total: int
    n_hooks_total: int
    plugin_ids: list[str]
    tools_allow: list[str]
    fingerprint_hash: str  # stable content hash for indexing

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_profile(
        cls,
        profile: PluginProfile,
        manifests: dict[str, PluginManifest],
        traces: dict[str, RegistrationTrace] | None = None,
    ) -> ProfileFingerprint:
        traces = traces or {}
        feature_vectors = []
        for entry in profile.plugins:
            manifest = manifests.get(entry.id)
            if manifest is None:
                # Cold start for an unknown plugin: synthesize a minimal
                # manifest so the plugin still contributes to the fingerprint.
                manifest = PluginManifest(id=entry.id, clawhub_channel=entry.source)
            trace = traces.get(entry.id)
            feature_vectors.append(plugin_feature_vector(manifest, trace))

        capability_coverage = sorted({
            _snake(key)
            for fv in feature_vectors
            for key in CONTRACT_KEYS
            if fv.get(f"provides_{_snake(key)}")
        })
        hook_footprint = sorted({
            hook for fv in feature_vectors
            for hook in KNOWN_HOOKS
            if fv.get(f"hooks_{hook}")
        })
        tool_family_surface = sorted({
            family for fv in feature_vectors
            for family in TOOL_FAMILIES
            if fv.get(f"tool_family_{family}")
        })
        capability_tags_union = sorted({
            tag for fv in feature_vectors
            for tag in fv.get("capability_tags", [])
        })

        n_clawhub = sum(1 for e in profile.plugins if e.source == "clawhub")
        n_custom = sum(1 for e in profile.plugins if e.source == "local")
        n_official = sum(
            1 for fv in feature_vectors if fv.get("clawhub_is_official")
        )
        n_tools = sum(int(fv.get("n_tools_registered", 0)) for fv in feature_vectors)
        n_hooks = sum(int(fv.get("n_hooks", 0)) for fv in feature_vectors)

        # Stable hash over the structural content
        h_payload = {
            "base_model": profile.base_model,
            "capabilities": capability_coverage,
            "hooks": hook_footprint,
            "families": tool_family_surface,
            "tags": capability_tags_union,
            "memory_slot": profile.slots.get("memory", ""),
            "context_engine_slot": profile.slots.get("contextEngine", ""),
            "plugin_ids": sorted(e.id for e in profile.plugins),
            "tools_allow": sorted(profile.tools_allow),
        }
        fingerprint_hash = hashlib.sha256(
            json.dumps(h_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]

        return cls(
            profile_name=profile.name,
            base_model=profile.base_model,
            capability_coverage=capability_coverage,
            hook_footprint=hook_footprint,
            tool_family_surface=tool_family_surface,
            capability_tags_union=capability_tags_union,
            memory_slot=profile.slots.get("memory", ""),
            context_engine_slot=profile.slots.get("contextEngine", ""),
            n_plugins=len(profile.plugins),
            n_clawhub_plugins=n_clawhub,
            n_custom_plugins=n_custom,
            n_official_plugins=n_official,
            n_tools_total=n_tools,
            n_hooks_total=n_hooks,
            plugin_ids=sorted(e.id for e in profile.plugins),
            tools_allow=sorted(profile.tools_allow),
            fingerprint_hash=fingerprint_hash,
        )


# ---------------------------------------------------------------------------
# Similarity metric for k-NN prediction.
# ---------------------------------------------------------------------------


def fingerprint_similarity(a: ProfileFingerprint, b: ProfileFingerprint) -> float:
    """Composite similarity in [0, 1].

    Combines:
      - Jaccard over capability coverage  (weight 0.30)
      - Jaccard over hook footprint       (weight 0.25)
      - Jaccard over tool family surface  (weight 0.20)
      - Jaccard over capability tags      (weight 0.10)
      - Slot match (memory, contextEngine) (weight 0.10)
      - Same base model                   (weight 0.05)
    """

    def jaccard(s1: Iterable[str], s2: Iterable[str]) -> float:
        ss1, ss2 = set(s1), set(s2)
        if not ss1 and not ss2:
            return 1.0
        union = ss1 | ss2
        if not union:
            return 1.0
        return len(ss1 & ss2) / len(union)

    cap = jaccard(a.capability_coverage, b.capability_coverage)
    hooks = jaccard(a.hook_footprint, b.hook_footprint)
    fams = jaccard(a.tool_family_surface, b.tool_family_surface)
    tags = jaccard(a.capability_tags_union, b.capability_tags_union)
    slot_match = 0.0
    if a.memory_slot == b.memory_slot:
        slot_match += 0.5
    if a.context_engine_slot == b.context_engine_slot:
        slot_match += 0.5
    model_match = 1.0 if a.base_model == b.base_model else 0.0

    return (
        0.30 * cap
        + 0.25 * hooks
        + 0.20 * fams
        + 0.10 * tags
        + 0.10 * slot_match
        + 0.05 * model_match
    )
