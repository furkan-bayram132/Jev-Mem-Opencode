"""Offline LongMemEval integration checks; no providers or model downloads."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

import pytest

from load_longmemeval import LongMemMessage, LongMemQuestion, LongMemSession
from memory import longmemeval_jev as adapter
from memory.jev_mem_config import JevMemConfig
from memory.memory_builder import MemoryBuilder
from memory.mock_encoder import MockEncoder
from memory.trg_memory import QueryContext, TemporalResonanceGraphMemory
from memory.vector_db import NumpyVectorDB


@pytest.fixture
def question():
    sessions = [LongMemSession("later", "2023/05/30 (Tue) 23:40", [
        LongMemMessage("user", "I visited the observatory yesterday."),
        LongMemMessage("assistant", "You mentioned visiting the observatory.")]),
        LongMemSession("earlier", "2023/05/20 (Sat) 02:21", [
            LongMemMessage("user", "I am planning an observatory visit.")])]
    return LongMemQuestion("synthetic-1", "temporal-reasoning", "When did I visit the observatory?",
                           "2023/05/31 (Wed) 12:00", "GOLD_ONLY_SENTINEL", ["GOLD_SESSION_SENTINEL"],
                           [s.date for s in sessions], [s.session_id for s in sessions], sessions)


@pytest.fixture
def memory(tmp_path, monkeypatch):
    def offline_builder(cache_dir, jev_config, **kwargs):
        encoder = MockEncoder()
        trg = TemporalResonanceGraphMemory(encoder=encoder, vector_db=NumpyVectorDB(encoder.dimension),
                                          llm_backend=None)
        return MemoryBuilder(cache_dir, jev_config=jev_config, trg_memory=trg, llm_enabled=False)
    monkeypatch.setattr(adapter, "MemoryBuilder", offline_builder)
    cfg = JevMemConfig(write_enabled=True, read_enabled=True, jev_mock=True)
    instance = adapter.LongMemEvalJevMemory(cfg, "test-model", "mock", tmp_path)
    yield instance
    instance.close()


def test_build_all_messages_and_preserve_dates_roles(memory, question):
    memory.build(question)
    nodes = list(memory.builder.trg.graph_db.nodes.values())
    assert len(nodes) == memory.builder.trg.vector_db.size() == 3
    assert [n.attributes["session_id"] for n in nodes] == ["earlier", "later", "later"]
    assert nodes[1].timestamp == nodes[2].timestamp == datetime(2023, 5, 30, 23, 40)
    assert nodes[2].attributes["speaker"] == "assistant"
    assert nodes[1].attributes["temporal_references"][0]["normalized"] == "29 May 2023"
    assert not memory.timing["cache_hit"]
    assert memory.timing["graph_construction_seconds"] >= 0


def test_cache_content_identity_and_forced_rebuild(memory, question):
    memory.build(question)
    original_ids = set(memory.builder.trg.graph_db.nodes)
    original_dir = memory.timing["cache_dir"]
    changed_gold = replace(question, answer="different", answer_session_ids=[], question="Different question?")
    memory.build(changed_gold)
    assert memory.timing["cache_hit"]
    assert memory.timing["graph_construction_seconds"] is None
    assert set(memory.builder.trg.graph_db.nodes) == original_ids
    memory.build(question, rebuild=True)
    assert not memory.timing["cache_hit"]
    assert len(memory.builder.trg.graph_db.nodes) == memory.builder.trg.vector_db.size() == 3
    assert set(memory.builder.trg.graph_db.nodes).isdisjoint(original_ids)
    changed = deepcopy(question)
    changed.haystack_sessions[0].messages[0].content += " New detail."
    memory.build(changed)
    assert not memory.timing["cache_hit"]
    assert memory.timing["cache_dir"] != original_dir


def test_cache_invalidates_dates_roles_and_configuration(memory, question):
    manifest = memory.cache_manifest(question)
    for field, value in (("date", "2023-06-01"), ("session_id", "changed")):
        changed = deepcopy(question)
        setattr(changed.haystack_sessions[0], field, value)
        assert memory.cache_manifest(changed) != manifest
    changed = deepcopy(question)
    changed.haystack_sessions[0].messages[0].role = "assistant"
    assert memory.cache_manifest(changed) != manifest
    memory.config = replace(memory.config, relation_threshold=0.1)
    assert memory.cache_manifest(question) != manifest


def test_answer_uses_only_retrieved_evidence_not_gold_or_full_haystack(memory, question, monkeypatch):
    memory.build(question)
    node = list(memory.builder.trg.graph_db.nodes.values())[1]
    selected = QueryContext(question.question, [node], [], "", {"query_id": "test"})
    monkeypatch.setattr(memory.engine, "query", lambda *a, **kw: (selected, ""))
    prompts = []
    def completion(prompt, **kwargs):
        prompts.append(prompt)
        return "29 May 2023"
    answer, details = memory.answer(question, SimpleNamespace(llm=SimpleNamespace(get_completion=completion)))
    assert answer == "29 May 2023"
    assert "GOLD_ONLY_SENTINEL" not in prompts[0] and "GOLD_SESSION_SENTINEL" not in prompts[0]
    assert "I am planning an observatory visit." not in prompts[0]
    assert "29 May 2023" in prompts[0] and question.question_date in prompts[0]
    assert details["retrieved_session_ids"] == ["later"]
    assert details["query_seconds"] >= details["retrieval_seconds"] >= 0


def test_real_shared_retrieval_controller_runs_offline(memory, question):
    memory.build(question)
    context, _ = memory.engine.query(question.question, top_k=3)
    assert context.anchor_nodes
    assert context.metadata["controller"] == "jev-mem"
    assert context.metadata["jev_calls"] <= memory.config.maximum_jev_calls


def test_date_parsing_does_not_invent_today():
    assert adapter.parse_date("") is None
    assert adapter.parse_date("2023-05-30T12:00:00Z") == datetime(2023, 5, 30, 12)
    with pytest.raises(ValueError, match="Unsupported LongMemEval date"):
        adapter.parse_date("not a date")


@pytest.mark.parametrize("use_jev", [False, True])
def test_harness_dispatch_and_result_metadata(memory, question, use_jev):
    from test_longmemeval_chunked import ChunkedLongMemEvalTester
    tester = ChunkedLongMemEvalTester.__new__(ChunkedLongMemEvalTester)
    tester.memory_level = "message"
    tester.jev_memory = memory if use_jev else None
    tester.llm_controller = SimpleNamespace(llm=SimpleNamespace(get_completion=lambda *a, **kw: "29 May 2023"))
    tester.evaluate_lenient = lambda *a: 1.0
    calls = []
    tester.build_memory_message_level = lambda *a, **kw: (calls.append("baseline"), None)
    tester.answer_question_improved = lambda *a: "baseline answer"
    result = tester.test_questions([question], max_questions=1)["results"][0]
    assert result["correct"]
    assert ("memory_timing" in result) == use_jev
    assert calls == ([] if use_jev else ["baseline"])
    if use_jev:
        assert memory.builder is None
