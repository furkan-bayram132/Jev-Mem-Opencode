import json
import time
from dataclasses import replace
from datetime import datetime, timezone

import httpx2 as httpx
import numpy as np
import pytest
from typesafe_sdk import Choice, Noul

from memory.graph_db import EventNode, Link, LinkType, NetworkXGraphDB
from memory.jev_client import CallBudget, JevClient, JevUnavailable
from memory.jev_questions import choice_fixture
from memory.memory_builder import MemoryBuilder
from memory.mock_encoder import MockEncoder
from memory.query_engine import QueryEngine
from memory.jev_mem_config import JevMemConfig
from memory.jev_mem_policies import GraphNeeds, allocate_graph_budgets
from memory.trg_memory import TemporalResonanceGraphMemory
from memory.vector_db import NumpyVectorDB


def fixture_answers(operation, state, questions):
    values = {key: 0.9 for key in questions}
    for key in values:
        if isinstance(questions[key], Choice):
            values[key] = choice_fixture(questions[key], "merge" if key.endswith("representation") else "unknown")
        elif any(word in key for word in ("redundancy", "contradiction", "obsolete", "causes", "caused_by", "before", "after", "overlaps", "same_episode")):
            values[key] = 0.0
    if operation == "stopping":
        values.update(evidence_sufficient=0.0, continue_useful=1.0, missing_evidence=1.0, contradiction=0.0)
    return values


def make_builder(tmp_path, config=None, mock=fixture_answers):
    config = config or JevMemConfig(write_enabled=True, read_enabled=True, jev_mock=True)
    encoder = MockEncoder()
    trg = TemporalResonanceGraphMemory(vector_db=NumpyVectorDB(encoder.dimension), encoder=encoder, llm_backend=None)
    client = JevClient(config, mock=mock)
    return MemoryBuilder(str(tmp_path), sys1_config=config, jev_client=client, trg_memory=trg, llm_enabled=False)


def add_memories(builder, count=5):
    return [builder.build("Alice works on project number " + str(i), datetime(2026, 9, i + 1),
                          {"entities": ["person:alice"], "source": "test"}) for i in range(count)]


def engine_for(builder):
    return QueryEngine(builder.trg, builder.node_index, sys1_config=builder.sys1_config, jev_client=builder.jev)


def test_rejection_has_no_storage_or_embedding_side_effects(tmp_path):
    config = JevMemConfig(write_enabled=True, jev_mock=True, admission_enabled=True)
    builder = make_builder(tmp_path, config, mock=lambda op, state, q: dict.fromkeys(q, 0.0))
    builder.trg.encoder.encode = lambda *_: pytest.fail("Rejected memory must not be embedded")
    assert builder.build("This observation should be discarded") is None
    assert not builder.trg.graph_db.nodes
    assert builder.trg.vector_db.size() == 0
    assert not builder.node_index


def test_canonical_node_multigraph_and_direction(tmp_path):
    def mock(operation, state, questions):
        values = fixture_answers(operation, state, questions)
        if operation == "relations":
            values["pair_0_caused_by"] = 0.91
        return values
    builder = make_builder(tmp_path, mock=mock)
    old, new = add_memories(builder, 2)
    assert len(builder.trg.graph_db.nodes) == 2
    assert builder.trg.vector_db.size() == 2
    assert len(new.attributes["sys1mem"]["memory_type"]) == 4
    links = list(builder.trg.graph_db.links.values())
    assert {link.link_type for link in links} == set(LinkType)
    for link in links:
        if link.link_type in (LinkType.CAUSAL, LinkType.TEMPORAL):
            assert (link.source_node_id, link.target_node_id) == (old.node_id, new.node_id)


def test_no_causality_from_similarity_and_no_timestamp_questions(tmp_path):
    observed = []
    def mock(operation, state, questions):
        observed.append((operation, questions))
        return fixture_answers(operation, state, questions)
    builder = make_builder(tmp_path, mock=mock)
    add_memories(builder, 3)
    assert all(link.link_type != LinkType.CAUSAL for link in builder.trg.graph_db.links.values())
    for op, questions in observed:
        if op == "relations":
            assert not any(key.endswith(("_temporal_order", "_entity")) for key in questions)


def test_implicit_temporal_and_alias_relations(tmp_path):
    def mock(operation, state, questions):
        values = fixture_answers(operation, state, questions)
        for key in questions:
            if key.endswith("_temporal_order"):
                values[key] = choice_fixture(questions[key], "before")
        return values
    builder = make_builder(tmp_path, mock=mock)
    old = builder.build("Dr. Li moved to Dallas", metadata={"entities": ["Dr. Li"]})
    new = builder.build("Professor Li met Alice before moving", metadata={"entities": ["Professor Li"]})
    assert new.timestamp is None
    edges = list(builder.trg.graph_db.links.values())
    assert any(e.link_type == LinkType.ENTITY and e.metadata["origin"] == "mock" for e in edges)
    assert any(e.link_type == LinkType.TEMPORAL and e.source_node_id == new.node_id and e.target_node_id == old.node_id for e in edges)


def test_candidate_set_is_bounded_and_relations_are_batched(tmp_path):
    sizes = []
    def mock(op, state, questions):
        if op == "relations":
            sizes.append(len(state["candidates"]))
        return fixture_answers(op, state, questions)
    builder = make_builder(tmp_path, JevMemConfig(write_enabled=True, jev_mock=True, candidate_top_k=2), mock)
    add_memories(builder, 5)
    assert sizes == [1, 2, 2, 2]


@pytest.mark.parametrize("total,minimum", [(0, 1), (1, 1), (2, 3), (7, 2), (20, 1), (19, 0)])
def test_graph_budgets_respect_total(total, minimum):
    config = JevMemConfig(total_graph_budget=total, minimum_graph_budget=minimum)
    needs = GraphNeeds(0.8, 0.9, 0.7, 0.6, 0.5, 0.5)
    values = allocate_graph_budgets(needs, config)
    assert sum(values.values()) == total
    assert all(type(v) is int and v >= 0 for v in values.values())
    assert values["temporal"] >= values["entity"]


def test_zero_need_does_not_activate_graphs():
    needs = GraphNeeds(0, 0, 0, 0, 0, 0)
    assert sum(allocate_graph_budgets(needs, JevMemConfig(graph_activation_threshold=0)).values()) == 0


def test_retrieval_limits_and_no_system_two(tmp_path):
    cfg = JevMemConfig(write_enabled=True, read_enabled=True, jev_mock=True, anchor_count=1,
                        maximum_nodes=3, maximum_depth=1, maximum_edges=4, total_graph_budget=2)
    builder = make_builder(tmp_path, cfg)
    add_memories(builder)
    context, text = engine_for(builder).query("What project does Alice work on?", top_k=10)
    m = context.metadata
    assert m["nodes_visited"] <= 3
    assert m["retrieval_depth"] <= 1
    assert m["edges_examined"] <= 4
    assert sum(m["graph_budget_used"].values()) <= 2
    assert m["jev_calls"] <= cfg.maximum_jev_calls
    assert m["llm_calls"] == 0
    assert text


def test_adaptive_stop_before_traversal(tmp_path):
    def mock(op, state, questions):
        if op == "stopping":
            return dict(evidence_sufficient=0.98, continue_useful=0.8, missing_evidence=0.0, contradiction=0.0)
        return fixture_answers(op, state, questions)
    builder = make_builder(tmp_path, mock=mock)
    add_memories(builder)
    context, _ = engine_for(builder).query("What about Alice?", top_k=2)
    assert context.metadata["stopping_decision"] == "evidence_sufficient"
    assert context.metadata["edges_examined"] == 0
    assert len(context.anchor_nodes) <= 2


def test_contradiction_prevents_sufficient_stop(tmp_path):
    def mock(op, state, questions):
        if op == "stopping":
            return dict(evidence_sufficient=0.99, continue_useful=0.9, missing_evidence=0, contradiction=0.9)
        return fixture_answers(op, state, questions)
    cfg = JevMemConfig(write_enabled=True, read_enabled=True, jev_mock=True, anchor_count=1, maximum_depth=1)
    builder = make_builder(tmp_path, cfg, mock)
    add_memories(builder)
    context, _ = engine_for(builder).query("What about Alice?")
    assert context.metadata["retrieval_depth"] == 1
    assert context.metadata["stopping_decision"] != "evidence_sufficient"


def test_call_budget_and_deadline(tmp_path):
    cfg = JevMemConfig(write_enabled=True, read_enabled=True, jev_mock=True, maximum_jev_calls=1)
    builder = make_builder(tmp_path, cfg)
    add_memories(builder, 2)
    context, _ = engine_for(builder).query("Alice project")
    assert context.metadata["jev_calls"] == 1
    assert context.metadata["stopping_decision"] == "max_jev_calls"
    budget = CallBudget(10, time.monotonic() - 1)
    assert builder.jev.probabilities("test", {}, {"x": "Test?"}, budget=budget) is None
    assert budget.calls == 0


def test_roundtrip_keeps_metadata_edges_vectors_and_missing_time(tmp_path):
    builder = make_builder(tmp_path)
    nodes = add_memories(builder, 2)
    untimed = builder.build("Alice also prefers concise answers")
    builder.save()
    restored = make_builder(tmp_path)
    restored.load()
    assert len(restored.trg.graph_db.nodes) == 3
    assert restored.trg.vector_db.size() == 3
    assert restored.trg.graph_db.get_node(untimed.node_id).timestamp is None
    assert restored.node_index == builder.node_index
    assert restored.trg.graph_db.get_node(nodes[0].node_id).attributes == nodes[0].attributes
    assert len(restored.trg.graph_db.links) == len(builder.trg.graph_db.links)
    context, _ = engine_for(restored).query("Alice concise answers")
    assert context.anchor_nodes


def test_live_wire_format_retry_validation_and_cache():
    requests = []
    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.url.path == "/v1/systemone"
        assert request.headers["Authorization"] == "Bearer test-secret"
        assert body["questions"]["store"]["type"] == "noul"
        if len(requests) == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"model": "jev-latest", "usage": {}, "answers": {"store": {"type": "noul", "noul": 0.9}}})
    client = JevClient(JevMemConfig(max_retries=1), api_key="test-secret", transport=httpx.MockTransport(handle))
    first = client.probabilities("test", {"content": "x"}, {"store": "Should store?"})
    second = client.probabilities("test", {"content": "x"}, {"store": "Should store?"})
    assert first.values == second.values == {"store": 0.9}
    assert second.source == "cache"
    assert len(requests) == 2


@pytest.mark.parametrize("value", [-0.1, 1.1, "0.5", None, True])
def test_malformed_probabilities_fallback_without_caching(value):
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"model": "jev-latest", "usage": {}, "answers": {"x": {"type": "noul", "noul": value}}}))
    client = JevClient(JevMemConfig(max_retries=0), api_key="test", transport=transport)
    assert client.probabilities("test", {}, {"x": "Question?"}) is None
    assert not client.cache


def test_nonfinite_probability_rejected():
    with pytest.raises(ValueError):
        JevClient._validate({"answers": {"x": {"type": "noul", "noul": float("nan")}}}, {"x": "Q"})


def test_auth_error_not_retried_and_fail_closed():
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(401)
    client = JevClient(JevMemConfig(fallback_to_magma=False), api_key="test", transport=httpx.MockTransport(handle))
    with pytest.raises(JevUnavailable, match="http_401"):
        client.probabilities("test", {}, {"x": "Question?"})
    assert len(requests) == 1


def test_missing_key_write_fallback_and_independent_ablations(tmp_path):
    cfg = JevMemConfig(write_enabled=True)
    builder = make_builder(tmp_path, cfg)
    builder.jev.api_key = ""
    node = builder.build("Alice lives and works in Dallas")
    assert node.attributes["sys1mem"]["controller"] == "magma_fallback"
    assert builder.trg.vector_db.size() == 1
    assert not builder.sys1_config.read_enabled
    baseline = make_builder(tmp_path / "baseline", JevMemConfig(read_enabled=True, jev_mock=True))
    baseline.jev.evaluate = lambda *_args, **_kwargs: pytest.fail("Ablated write must not call Jev")
    baseline.build("Alice likes learning about new projects")
    assert baseline.trg.vector_db.size() == 1


def test_consolidation_records_contradiction_without_destructive_merge(tmp_path):
    def mock(op, state, questions):
        values = fixture_answers(op, state, questions)
        if op == "consolidation":
            values.update({key: 0.95 for key, question in questions.items() if isinstance(question, Noul)})
        return values
    builder = make_builder(tmp_path, mock=mock)
    nodes = add_memories(builder, 2)
    decisions = builder.consolidate(nodes[-1].node_id, summarizer=lambda texts: pytest.fail("Contradiction must block merging"))
    assert decisions[0]["contradiction"] == 0.95
    assert len(builder.trg.graph_db.nodes) == 2
    assert any(l.properties["sub_type"] == "CONTRADICTS" for l in builder.trg.graph_db.links.values())
    links = len(builder.trg.graph_db.links)
    builder.consolidate(nodes[-1].node_id)
    assert len(builder.trg.graph_db.links) == links


def test_summary_only_after_jev_approval_and_no_recursion(tmp_path):
    cfg = JevMemConfig(write_enabled=True, jev_mock=True, consolidation_interval=1)
    builder = make_builder(tmp_path, cfg)
    nodes = add_memories(builder, 2)
    calls = []
    def summarize(texts):
        calls.append(texts)
        return "Alice consistently works on project planning"
    builder.consolidate(nodes[-1].node_id, summarizer=summarize)
    assert len(calls) == 1
    assert len(builder.trg.graph_db.nodes) == 3
    assert any(n.attributes.get("source_memory_ids") == [nodes[-1].node_id, nodes[0].node_id] for n in builder.trg.graph_db.nodes.values())


def test_audit_records_decisions_without_credentials_or_content(tmp_path):
    path = tmp_path / "decisions.jsonl"
    cfg = JevMemConfig(write_enabled=True, read_enabled=True, jev_mock=True, audit_path=str(path))
    builder = make_builder(tmp_path, cfg)
    builder.jev.api_key = "private-test-secret"
    add_memories(builder, 2)
    engine_for(builder).query("Alice project")
    text = path.read_text()
    records = [json.loads(line) for line in text.splitlines()]
    assert {"memory_constructed", "query", "jev_decision"} <= {r["event"] for r in records}
    assert "private-test-secret" not in text
    assert "Alice works" not in text


def test_failed_graph_insertion_rolls_back_vector(tmp_path, monkeypatch):
    builder = make_builder(tmp_path)
    add_memories(builder, 1)
    def fail(link):
        raise RuntimeError("storage failed")
    monkeypatch.setattr(builder.trg.graph_db, "add_link", fail)
    with pytest.raises(RuntimeError, match="storage failed"):
        builder.build("Alice works on another project")
    assert len(builder.trg.graph_db.nodes) == builder.trg.vector_db.size() == 1


def test_config_rejects_unknown_and_invalid_settings(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"maximum_nods": 4}')
    with pytest.raises(ValueError, match="Unknown"):
        JevMemConfig.load(path)
    with pytest.raises(ValueError):
        JevMemConfig(maximum_jev_calls=-1)
    with pytest.raises(ValueError):
        JevMemConfig(admission_threshold=float("nan"))


def test_openai_embedding_adapter_batches_and_orders(monkeypatch):
    from types import SimpleNamespace
    from memory.openai_encoder import OpenAIVectorEncoder
    monkeypatch.delenv("OPENAI_EMBEDDING_MODEL", raising=False)
    requests = []
    def create(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(index=i, embedding=[float(i + 1), 0.0])
                                     for i in reversed(range(len(kwargs['input'])))])
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    encoder = OpenAIVectorEncoder(client=client, dimension=2)
    vectors = encoder.encode_batch(["one", "two", "three"], batch_size=2)
    assert vectors.tolist() == [[1, 0], [2, 0], [1, 0]]
    assert len(requests) == 2
    assert requests[0]["dimensions"] == 2


def test_locomo_write_path_avoids_llm_extraction(tmp_path, monkeypatch):
    from types import SimpleNamespace
    builder = make_builder(tmp_path)
    monkeypatch.setattr(builder, "extract_event", lambda *_: pytest.fail("Jev-Mem must not use LLM extraction"))
    monkeypatch.setattr(builder, "create_session_nodes", lambda *_: pytest.fail("Raw observations must be admitted first"))
    turn = SimpleNamespace(speaker="Alice", text="I prefer concise project explanations", dia_id="D1:1")
    session = SimpleNamespace(turns=[turn], date_time="1:00 pm on 1 September, 2026")
    sample = SimpleNamespace(sample_id="example", conversation=SimpleNamespace(sessions={1: session}))
    stats = builder.build_memory(sample)
    assert stats['events_created'] == 1
    node = next(iter(builder.trg.graph_db.nodes.values()))
    assert node.attributes['parent_interaction_id'] == "D1:1"


def test_magma_read_path_remains_usable(tmp_path):
    builder = make_builder(tmp_path, JevMemConfig(write_enabled=True, read_enabled=False, jev_mock=True))
    add_memories(builder, 3)
    engine = engine_for(builder)
    engine.jev.evaluate = lambda *_args, **_kwargs: pytest.fail("Ablated read must not call Jev")
    context, evidence = engine.query("Alice project", top_k=2)
    assert context.anchor_nodes
    assert evidence
    assert context.metadata.get('controller') != 'sys1mem'


def test_faiss_cache_roundtrip(tmp_path):
    from memory.vector_db import FAISSVectorDB, FAISS_AVAILABLE
    if not FAISS_AVAILABLE:
        pytest.skip("FAISS is optional")
    builder = make_builder(tmp_path)
    builder.trg.vector_db = FAISSVectorDB(builder.trg.encoder.dimension)
    add_memories(builder, 2)
    builder.save()
    restored = make_builder(tmp_path)
    restored.trg.vector_db = FAISSVectorDB(restored.trg.encoder.dimension)
    restored.load()
    assert restored.trg.vector_db.size() == 2
    assert restored.trg.stats['events_added'] == 2
    assert restored.trg.stats['links_created'] > 0
    assert engine_for(restored).query("Alice project")[0].anchor_nodes


def test_system_two_receives_retrieved_evidence(tmp_path):
    from types import SimpleNamespace
    from main import JevMemSystem
    builder = make_builder(tmp_path)
    add_memories(builder, 3)
    calls = []
    def complete(prompt, **kwargs):
        calls.append(prompt)
        return "Alice works on projects."
    builder.llm_controller = SimpleNamespace(llm=SimpleNamespace(get_completion=complete))
    system = JevMemSystem(cache_dir=str(tmp_path), memory_builder=builder)
    assert system.query("What does Alice work on?") == "Alice works on projects"
    assert len(calls) == 1 and "Alice works on project number" in calls[0]
    system.save_memory()
    system.load_memory()
    assert system.query_engine.node_index == builder.node_index


def test_cli_build_validates_before_inserting(tmp_path):
    from main import JevMemSystem
    builder = make_builder(tmp_path)
    system = JevMemSystem(memory_builder=builder)
    with pytest.raises(ValueError):
        system.build_memory_from_conversation(["Alice works in Dallas", {"content": ""}])
    assert not builder.trg.graph_db.nodes
    assert system.build_memory_from_conversation(["Alice works in Dallas"]) == {"admitted": 1, "rejected": 0}


def test_sdk_mixed_questions_env_auth_and_cache(tmp_path, monkeypatch):
    from dotenv import load_dotenv
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("TYPESAFE_API_KEY=fixture-typesafe-key\n")
    load_dotenv(env_path, override=False)
    monkeypatch.setenv("TYPESAFE_DEFAULT_MODEL", "jev-latest")
    monkeypatch.setenv("TYPESAFE_BASE_URL", "https://api.typesafe.ai")
    questions = {
        "store": Noul(instructions="Does `observation` contain a personal fact?",
                      criteria={"true": "Specific fact", "false": "Only filler"}),
        "order": Choice(instructions="How is `observation` ordered relative to `previous`?",
                        criteria={"before": "Earlier", "unknown": "Not established"}),
    }
    state = {"observation": "Alice arrived before Bob.", "previous": "Bob arrived."}
    calls = []
    def handle(request):
        calls.append(request)
        assert request.url == "https://api.typesafe.ai/v1/systemone"
        assert request.headers["Authorization"] == "Bearer fixture-typesafe-key"
        assert json.loads(request.content) == {"model": "jev-latest", "state": state,
            "questions": {key: q.model_dump() for key, q in questions.items()}}
        return httpx.Response(200, json={"model": "jev-latest", "usage": {"input_tokens": 20, "output_tokens": 5},
            "answers": {"store": {"type": "noul", "noul": 0.9}, "order": {
                "type": "choice", "choice": "before", "probabilities": {"before": 0.85, "unknown": 0.15},
                "confidence": 0.6}}})
    with JevClient(transport=httpx.MockTransport(handle)) as client:
        first = client.evaluate("mixed", state, questions)
        assert first.values == {"store": 0.9}
        assert first.choices["order"].confidence == 0.6
        assert first.choices["order"].probabilities["before"] == 0.85
        assert first.usage == {"input_tokens": 20, "output_tokens": 5}
        first.choices["order"].probabilities["before"] = 0.0
        second = client.evaluate("mixed", state, questions)
        assert second.source == "cache" and second.usage == {}
        assert second.choices["order"].probabilities["before"] == 0.85
        assert len(calls) == 1
        questions["store"] = Noul(instructions="Is `observation` new?")
        assert client.evaluate("mixed", state, questions).source == "jev"
        assert len(calls) == 2


@pytest.mark.parametrize("key,expected", [(None, "environment-key"), ("explicit-key", "explicit-key"), ("", None)])
def test_api_key_precedence(key, expected, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "environment-key")
    monkeypatch.setenv("OPENAI_API_KEY", "different-provider-key")
    calls = []
    def handle(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer " + expected
        return httpx.Response(200, json={"model": "jev-latest", "usage": {},
                                       "answers": {"x": {"type": "noul", "noul": 0.8}}})
    with JevClient(JevMemConfig(max_retries=0), api_key=key, transport=httpx.MockTransport(handle)) as client:
        result = client.evaluate("key", {}, {"x": Noul(instructions="A fact?")})
    assert len(calls) == (1 if expected else 0)
    assert (result is not None) == bool(expected)


@pytest.mark.parametrize("answer", [
    {"type": "noul", "noul": 0.8},
    {"type": "choice", "choice": "a", "probabilities": {"a": 1.0}, "confidence": 1.0},
    {"type": "choice", "choice": "a", "probabilities": {"a": 0.8, "b": 0.1, "extra": 0.1}, "confidence": 0.7},
    {"type": "choice", "choice": "a", "probabilities": {"a": 0.9, "b": 0.9}, "confidence": 0.7},
    {"type": "choice", "choice": "a", "probabilities": {"a": 0.1, "b": 0.9}, "confidence": 0.7},
    {"type": "choice", "choice": "missing", "probabilities": {"a": 0.9, "b": 0.1}, "confidence": 0.7},
    {"type": "choice", "choice": "a", "probabilities": {"a": True, "b": 0.0}, "confidence": 1.0},
    {"type": "choice", "choice": "a", "probabilities": {"a": 1.1, "b": -0.1}, "confidence": 1.0},
    {"type": "choice", "choice": "a", "probabilities": {"a": 0.9, "b": 0.1}, "confidence": 1.2},
])
def test_invalid_choice_is_not_cached(answer):
    question = Choice(instructions="Which?", criteria={"a": None, "b": None})
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        "model": "jev-latest", "usage": {}, "answers": {"x": answer}}))
    with JevClient(JevMemConfig(max_retries=0), api_key="test", transport=transport) as client:
        assert client.evaluate("invalid-choice", {}, {"x": question}) is None
        assert not client.cache


@pytest.mark.parametrize("status", [401, 422, 429, 529])
def test_sdk_retries_count_against_budget_and_honor_retry_after(status, monkeypatch):
    calls, sleeps = [], []
    monkeypatch.setattr("memory.jev_client.time.sleep", sleeps.append)
    def handle(request):
        calls.append(request)
        return httpx.Response(status, headers={"Retry-After": "0.25"}, json={"error": "fixture"})
    budget = CallBudget(2, time.monotonic() + 10)
    with JevClient(JevMemConfig(max_retries=5), api_key="test", transport=httpx.MockTransport(handle)) as client:
        assert client.evaluate("retry", {}, {"x": Noul(instructions="Relevant?")}, budget=budget) is None
    expected = 1 if status in (401, 422) else 2
    assert len(calls) == budget.calls == expected
    assert sleeps == ([] if expected == 1 else [0.25])


def test_retry_after_cannot_exceed_deadline(monkeypatch):
    monkeypatch.setattr("memory.jev_client.time.sleep", lambda *_: pytest.fail("Must respect deadline"))
    transport = httpx.MockTransport(lambda request: httpx.Response(529, headers={"Retry-After": "120"}))
    budget = CallBudget(3, time.monotonic() + 5)
    with JevClient(api_key="test", transport=transport) as client:
        assert client.evaluate("retry", {}, {"x": Noul(instructions="Relevant?")}, budget=budget) is None
    assert budget.calls == 1


def test_admission_and_multilabel_typing_share_single_request(tmp_path):
    calls = []
    def mock(op, state, questions):
        calls.append((op, questions))
        return fixture_answers(op, state, questions)
    config = JevMemConfig(write_enabled=True, jev_mock=True, admission_enabled=True)
    builder = make_builder(tmp_path, config, mock=mock)
    node = builder.build("Alice prefers to paint on weekends")
    assert len(calls) == 1 and calls[0][0] == "observation"
    assert set(node.attributes["sys1mem"]["memory_type"].values()) == {0.9}
    assert all(isinstance(q, Noul) and q.criteria for q in calls[0][1].values())


def test_default_write_keeps_short_and_duplicate_turns_with_zero_type_scores(tmp_path):
    calls = []
    def mock(op, state, questions):
        assert op != "observation"
        if op == "memory_type":
            assert set(questions) == {"episodic", "semantic", "procedural", "preference"}
            calls.append(op)
            return dict.fromkeys(questions, 0.0)
        return fixture_answers(op, state, questions)
    builder = make_builder(tmp_path, mock=mock)
    builder.write_policy.assess_observation = lambda *_: pytest.fail("Admission must be bypassed")
    nodes = [builder.build(text) for text in ["Hi", "Yes", "Hi"]]
    assert len({node.node_id for node in nodes}) == 3
    assert [node.content_narrative for node in nodes] == ["Hi", "Yes", "Hi"]
    assert builder.trg.vector_db.size() == 3
    for node in nodes:
        metadata = node.attributes["sys1mem"]
        assert metadata["admission_enabled"] is False
        assert metadata["admission"] is None and metadata["admission_score"] is None
        assert set(metadata["memory_type"].values()) == {0.0}
    assert calls


def test_locomo_keeps_every_turn_and_provenance_without_admission(tmp_path):
    from types import SimpleNamespace
    builder = make_builder(tmp_path)
    builder.write_policy.assess_observation = lambda *_: pytest.fail("Admission must be bypassed")
    turns = [SimpleNamespace(speaker="Alice", text=text, dia_id=f"D1:{i}")
             for i, text in enumerate(["Hi", "Yes", "Hi", "I moved to Dallas"], 1)]
    session = SimpleNamespace(turns=turns, date_time="1:00 pm on 1 September, 2026")
    sample = SimpleNamespace(sample_id="example", conversation=SimpleNamespace(sessions={1: session}))
    stats = builder.build_memory(sample)
    assert stats["events_created"] == len(turns)
    assert stats["events_rejected"] == 0
    assert {node.attributes["dia_id"] for node in builder.trg.graph_db.nodes.values()} == {t.dia_id for t in turns}
    builder.save()
    restored = make_builder(tmp_path)
    restored.load()
    assert len(restored.trg.graph_db.nodes) == restored.trg.vector_db.size() == len(turns)


def test_admission_setting_is_validated_and_part_of_cache_config():
    disabled = JevMemConfig()
    enabled = replace(disabled, admission_enabled=True)
    assert disabled.to_dict() != enabled.to_dict()
    with pytest.raises(ValueError, match="admission_enabled"):
        JevMemConfig(admission_enabled="false")


@pytest.mark.parametrize("option,subtype,reverse", [
    ("before", "PRECEDES", False), ("after", "PRECEDES", True),
    ("during", "DURING", False), ("contains", "DURING", True),
    ("overlaps", "OVERLAPS", False), ("same_time", "CONCURRENT", False),
    ("unknown", None, False),
])
def test_temporal_choice_creates_only_selected_relation(tmp_path, option, subtype, reverse):
    def mock(op, state, questions):
        values = fixture_answers(op, state, questions)
        for key, question in questions.items():
            if key.endswith("temporal_order"):
                values[key] = choice_fixture(question, option)
                values[key]["confidence"] = 0.1  # Gate on option probability, not this summary.
        return values
    builder = make_builder(tmp_path, mock=mock)
    old = builder.build("Alice attended a painting workshop")
    new = builder.build("Alice presented paintings at a gallery")
    edges = [edge for edge in builder.trg.graph_db.links.values() if edge.link_type == LinkType.TEMPORAL]
    assert len(edges) == (1 if subtype else 0)
    if subtype:
        edge = edges[0]
        assert edge.properties["sub_type"] == subtype
        assert (edge.source_node_id, edge.target_node_id) == (
            (old.node_id, new.node_id) if reverse else (new.node_id, old.node_id))


@pytest.mark.parametrize("option,probability", [("keep_separate", 1.0), ("uncertain", 1.0), ("merge", 0.55), ("promote", 0.55)])
def test_consolidation_requires_supported_action(tmp_path, option, probability):
    def mock(op, state, questions):
        values = fixture_answers(op, state, questions)
        if op == "consolidation":
            for key, question in questions.items():
                if isinstance(question, Choice):
                    values[key] = {"type": "choice", "choice": option, "confidence": 1.0,
                        "probabilities": {name: probability if name == option else (1 - probability) / 3
                                          for name in question.criteria}}
        return values
    builder = make_builder(tmp_path, mock=mock)
    nodes = add_memories(builder, 2)
    decisions = builder.consolidate(nodes[-1].node_id, summarizer=lambda *_: pytest.fail("No approved action"))
    assert decisions[0]["representation"]["choice"] == option
    assert len(builder.trg.graph_db.nodes) == 2


@pytest.mark.parametrize("backend", ["numpy", "faiss"])
def test_existing_cache_is_loaded_only_explicitly_and_rebuild_replaces_it(tmp_path, monkeypatch, backend):
    from memory import trg_memory
    from memory.vector_db import FAISS_AVAILABLE, create_vector_db
    if backend == "faiss" and not FAISS_AVAILABLE:
        pytest.skip("FAISS is optional")
    monkeypatch.setattr(trg_memory, "VectorEncoder", lambda **kwargs: MockEncoder())
    monkeypatch.setattr(trg_memory, "create_vector_db", lambda **kwargs: create_vector_db(
        backend=backend, dimension=kwargs["dimension"], persist_path=kwargs.get("persist_path")))
    config = JevMemConfig(write_enabled=True, jev_mock=True)
    def new_builder():
        return MemoryBuilder(str(tmp_path), sys1_config=config, llm_enabled=False)
    initial = new_builder()
    old_node = initial.build("Alice works on the original project")
    initial.save()

    reused = new_builder()
    assert reused.trg.vector_db.size() == 0
    reused.load()
    assert reused.trg.graph_db.get_node(old_node.node_id) is not None
    assert reused.trg.vector_db.exists(old_node.node_id)
    assert reused.node_index == initial.node_index

    rebuilt = new_builder()  # --rebuild skips load() on this fresh instance.
    assert not rebuilt.trg.graph_db.nodes
    assert rebuilt.trg.vector_db.size() == 0
    new_node = rebuilt.build("Bob works on a completely different project")
    rebuilt.save()
    restored = new_builder()
    restored.load()
    assert set(restored.trg.graph_db.nodes) == {new_node.node_id}
    assert restored.trg.vector_db.size() == 1
    assert restored.trg.vector_db.exists(new_node.node_id)
    assert not restored.trg.vector_db.exists(old_node.node_id)
    assert restored.node_index == rebuilt.node_index


@pytest.mark.parametrize("question,answer", [
    ("What activities does Alex enjoy?", "Pottery, camping, painting, swimming, running, and playing the violin"),
    ("Who attended?", "Alex Rivera, Sam Lee, and Dr. Morgan"),
    ("Would Alex pursue counseling?", "Likely no, because their interest in counseling grew out of the support they received"),
    ("Would Alex read these books?", "Yes, Alex would likely have Dr. Seuss books because they collect children's classics"),
    ("When was the trip?", "The week before 9 June 2023"),
    ("What is known?", "Their birthplace is not mentioned, but they grew up in Rome"),
    ("What is Alex's relationship status?", "Not married"),
])
def test_answer_cleaning_preserves_complete_meaning(question, answer):
    from memory.answer_formatter import AnswerFormatter
    assert AnswerFormatter().extract_answer(answer, question) == answer


def test_multihop_context_preserves_speakers_dates_and_raw_text():
    from memory.answer_formatter import AnswerFormatter
    nodes = [EventNode(timestamp=datetime(2023, 6, 9), content_narrative="original",
                       attributes={"speaker": speaker, "dia_id": f"D1:{i}", "original_text": text})
             for i, (speaker, text) in enumerate([("Alex", "I started painting last week."),
                                                 ("Sam", "I started pottery yesterday.")], 1)]
    context = AnswerFormatter().format_context_for_qa(nodes, "What activities do both people enjoy?")
    for node in nodes:
        assert f"[Speaker: {node.attributes['speaker']}]" in context
        assert node.attributes["dia_id"] in context
        assert node.attributes["original_text"] in context
    assert "[Conversation: 09 June 2023]" in context


def test_keyword_ranking_uses_all_postings_and_is_deterministic(tmp_path):
    builder = make_builder(tmp_path)
    for i in range(50):
        builder.trg.graph_db.add_node(EventNode(node_id=f"n{i:02}", content_narrative="Alice likes art"))
    target = builder.trg.graph_db.get_node("n49")
    target.content_narrative = "Alice art pottery exhibition"
    builder.node_index = {"art": set(builder.trg.graph_db.nodes)}
    engine = engine_for(builder)
    result = engine._keyword_search("art pottery exhibition", limit=50)
    assert len(result) == 50 and result[0].node_id == target.node_id
    builder.node_index["art"] = set(reversed(sorted(builder.node_index["art"])))
    assert [n.node_id for n in engine._keyword_search("art pottery exhibition", limit=50)] == [n.node_id for n in result]


def test_retrieval_parameters_and_evidence_diagnostics(tmp_path):
    from types import SimpleNamespace
    from memory.test_harness import TestHarness
    config = JevMemConfig(write_enabled=True, read_enabled=True, jev_mock=True, answer_top_k=30, multihop_top_k=40)
    builder = make_builder(tmp_path, config)
    node = builder.build("Alice enjoys painting on weekends", metadata={"dia_id": "D1:1"})
    harness = TestHarness(builder, engine_for(builder))
    assert harness.retrieval_top_k(1) == 40
    assert harness.retrieval_top_k(4) == 30
    assert harness.retrieval_diagnostics(SimpleNamespace(evidence=["D1:1", "D1:2"]),
        SimpleNamespace(anchor_nodes=[node])) == {"retrieved_dia_ids": ["D1:1"], "evidence_recall": 0.5}


def test_reuse_memory_allows_read_tuning_but_rejects_write_changes(tmp_path):
    from test_fixed_memory import validate_reuse_memory
    builder = make_builder(tmp_path / "source")
    add_memories(builder, 2)
    builder.save()
    tuned = replace(builder.sys1_config, anchor_count=20, maximum_edges=1200)
    source = validate_reuse_memory(builder.cache_dir, tuned)
    restored = make_builder(tmp_path / "new_experiment", tuned)
    restored.load(source)
    assert len(restored.trg.graph_db.nodes) == restored.trg.vector_db.size() == 2
    assert restored.cache_dir == tmp_path / "new_experiment"
    with pytest.raises(ValueError, match="construction settings"):
        validate_reuse_memory(source, replace(tuned, admission_enabled=True))
    with pytest.raises(ValueError, match="construction settings"):
        validate_reuse_memory(source, replace(tuned, candidate_top_k=20))
