"""Server-side memory contract: System One retrieves, System Two is never called."""
import json
from pathlib import Path

import pytest

from jev_mem.store import MAXIMUM_TOP_K, MemoryStore, parse_timestamp
from memory.mock_encoder import MockEncoder

OBSERVATIONS = [
    "Alice started the Jev-Mem project in Dallas.",
    "Alice prefers concise explanations about the Jev-Mem project.",
    "Alice presented the Jev-Mem project results on Friday.",
]


def make_store(path, **overrides):
    """Mock decisions and a mock encoder keep these tests offline."""
    return MemoryStore(path, jev_mock=True, encoder=MockEncoder(), **overrides)


@pytest.fixture
def populated(tmp_path):
    store = make_store(tmp_path / "memory")
    for day, text in enumerate(OBSERVATIONS, 1):
        store.remember(text, timestamp=f"2026-09-0{day}T00:00:00", metadata={"source": "test"})
    return store


def test_remember_persists_a_reloadable_graph(populated, tmp_path):
    directory = tmp_path / "memory"
    for name in ("graph.json", "keyword_index.json", "jev_mem_config.json"):
        assert (directory / name).exists()

    reopened = make_store(directory)
    result = reopened.recall("What does Alice prefer about Jev-Mem explanations?")
    assert "concise" in result["evidence"]


def test_recall_returns_evidence_without_calling_system_two(populated):
    result = populated.recall("Where did Alice start the Jev-Mem project?")
    assert result["observations"]
    assert result["trace"]["llm_calls"] == 0
    assert result["trace"]["controller"] == "jev-mem"


def test_recall_bounds_the_context_it_hands_back(populated):
    assert len(populated.recall("Alice", top_k=1)["observations"]) == 1
    oversized = populated.recall("Alice", top_k=500)
    assert len(oversized["observations"]) <= MAXIMUM_TOP_K


def test_compact_format_drops_benchmark_decoration(populated):
    compact = populated.recall("Alice", output_format="compact")["evidence"]
    assert "MOST RELEVANT" not in compact and "Key Information" not in compact
    assert compact.startswith("1. [2026-09-")

    qa = populated.recall("Alice", output_format="qa")["evidence"]
    assert "MOST RELEVANT" in qa


def test_recall_on_empty_memory_is_not_an_error(tmp_path):
    result = make_store(tmp_path / "empty").recall("anything")
    assert result["observations"] == []
    assert result["trace"]["stopping_decision"] == "empty_memory"


def test_reopening_with_different_write_settings_is_refused(populated, tmp_path):
    directory = tmp_path / "memory"
    saved = json.loads((directory / "jev_mem_config.json").read_text())
    saved["candidate_top_k"] += 1
    (directory / "jev_mem_config.json").write_text(json.dumps(saved))

    with pytest.raises(ValueError, match="different construction settings"):
        make_store(directory).recall("Alice")


@pytest.mark.parametrize("text", ["", "   ", None])
def test_remember_rejects_empty_observations(tmp_path, text):
    with pytest.raises(ValueError):
        make_store(tmp_path / "memory").remember(text)


def test_timestamps_accept_iso_text_including_zulu():
    assert parse_timestamp("2026-09-22T10:00:00Z").year == 2026
    assert parse_timestamp(None) is None
    with pytest.raises(ValueError):
        parse_timestamp(17)


def test_tools_are_registered_with_agent_facing_descriptions(tmp_path):
    pytest.importorskip("mcp")
    from jev_mem.mcp_server import build_server

    server = build_server(make_store(tmp_path / "memory"))
    assert server is not None


# --- Reaching Jev through a host that serves it at a different path ---------


def openrouter_profile():
    from memory.jev_mem_config import JevMemConfig
    return JevMemConfig.load("config/jev_mem_openrouter.json")


def test_openrouter_profile_targets_the_decisions_endpoint():
    config = openrouter_profile()
    assert config.jev_base_url == "https://openrouter.ai"
    assert config.jev_endpoint_path == "/api/alpha/decisions"
    assert config.jev_api_key_env == "OPENROUTER_API_KEY"
    assert config.jev_model == "~typesafe/jev-latest"
    assert config.write_enabled and config.read_enabled


def test_default_profile_still_targets_typesafe():
    from memory.jev_mem_config import JevMemConfig
    config = JevMemConfig.load("config/jev_mem.json")
    assert config.jev_base_url == "https://api.typesafe.ai"
    assert config.jev_endpoint_path == "/v1/systemone"
    assert config.jev_api_key_env == "TYPESAFE_API_KEY"


@pytest.mark.parametrize("path", ["v1/systemone", "", 7])
def test_endpoint_path_must_be_absolute(path):
    from memory.jev_mem_config import JevMemConfig
    with pytest.raises(ValueError):
        JevMemConfig(jev_endpoint_path=path)


def test_client_reads_the_key_named_by_the_profile(monkeypatch):
    from memory.jev_client import JevClient
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-fixture-key")
    assert JevClient(openrouter_profile()).api_key == "openrouter-fixture-key"


def test_missing_key_names_the_configured_variable(monkeypatch):
    from memory.jev_client import JevClient
    from memory.jev_questions import routing_questions

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client = JevClient(openrouter_profile(), api_key="")
    events = []
    client.audit.emit = lambda event, **values: events.append((event, values))

    assert client.evaluate("routing", {"query": "x"}, routing_questions()) is None
    assert [v["reason"] for e, v in events if e == "jev_fallback"] == ["missing_openrouter_api_key"]


def test_request_is_rewritten_onto_the_decisions_path():
    """The SDK posts to /v1/systemone; the transport must retarget the host path."""
    import httpx2
    from memory.jev_client import JevClient
    from memory.jev_questions import routing_questions

    seen = {}

    def respond(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        answers = {name: {"type": "noul", "noul": 0.5} for name in routing_questions()}
        return httpx2.Response(200, json={"model": "~typesafe/jev-latest", "usage": {}, "answers": answers})

    from memory.jev_endpoint import PathRewriteTransport
    client = JevClient(openrouter_profile(), api_key="fixture-key",
                       transport=PathRewriteTransport("/api/alpha/decisions", httpx2.MockTransport(respond)))

    result = client.evaluate("routing", {"query": "Where does Alice live?"}, routing_questions())
    assert result is not None and result.source == "jev"
    assert seen["url"] == "https://openrouter.ai/api/alpha/decisions"
    assert seen["auth"] == "Bearer fixture-key"
    assert seen["body"]["model"] == "~typesafe/jev-latest"
    assert set(seen["body"]["questions"]) == set(routing_questions())
    assert seen["body"]["questions"]["semantic"]["type"] == "noul"


def test_path_rewrite_rejects_a_relative_path():
    from memory.jev_endpoint import PathRewriteTransport
    with pytest.raises(ValueError):
        PathRewriteTransport("api/alpha/decisions")


def test_client_builds_the_rewrite_transport_from_the_profile(monkeypatch):
    """Without an explicit transport the profile's path must still be honoured."""
    from memory.jev_client import JevClient
    from memory.jev_endpoint import PathRewriteTransport

    monkeypatch.setenv("OPENROUTER_API_KEY", "fixture-key")
    transport = JevClient(openrouter_profile())._get_sdk()._http_client._transport
    assert isinstance(transport, PathRewriteTransport)
    assert transport.path == "/api/alpha/decisions"


def test_default_profile_uses_no_rewrite_transport(monkeypatch):
    from memory.jev_client import JevClient
    from memory.jev_endpoint import PathRewriteTransport
    from memory.jev_mem_config import JevMemConfig

    monkeypatch.setenv("TYPESAFE_API_KEY", "fixture-key")
    transport = JevClient(JevMemConfig.load("config/jev_mem.json"))._get_sdk()._http_client._transport
    assert not isinstance(transport, PathRewriteTransport)


def test_profile_model_wins_over_the_environment_default(monkeypatch):
    """A stray TYPESAFE_DEFAULT_MODEL must not retarget an explicit profile."""
    monkeypatch.setenv("TYPESAFE_DEFAULT_MODEL", "jev-latest")
    assert openrouter_profile().jev_model == "~typesafe/jev-latest"


def test_environment_default_still_applies_without_a_profile(monkeypatch):
    from memory.jev_mem_config import JevMemConfig
    monkeypatch.setenv("TYPESAFE_DEFAULT_MODEL", "jev-1.13")
    assert JevMemConfig.load().jev_model == "jev-1.13"
