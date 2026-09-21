"""Optional metric resources must not download while importing project modules."""
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys

import pytest


@pytest.fixture
def metrics(monkeypatch):
    calls = []
    nltk = ModuleType("nltk")
    nltk.download = lambda resource, **kw: calls.append(("download", resource))
    nltk.word_tokenize = str.split
    translate = ModuleType("nltk.translate")
    bleu = ModuleType("nltk.translate.bleu_score")
    bleu.sentence_bleu = lambda *a, **kw: 0.5
    bleu.SmoothingFunction = lambda: SimpleNamespace(method1=None)
    meteor = ModuleType("nltk.translate.meteor_score")
    meteor.meteor_score = lambda *a: 0.75
    embeddings = ModuleType("sentence_transformers")
    def create_model(name):
        calls.append(("model", name))
        return SimpleNamespace(encode=lambda *a, **kw: [1.0])
    embeddings.SentenceTransformer = create_model
    util = ModuleType("sentence_transformers.util")
    util.pytorch_cos_sim = lambda *a: SimpleNamespace(item=lambda: 0.8)
    for module in [nltk, translate, bleu, meteor, embeddings, util]:
        monkeypatch.setitem(sys.modules, module.__name__, module)
    path = Path(__file__).resolve().parents[1] / "utils" / "utils.py"
    spec = importlib.util.spec_from_file_location("metric_resource_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, calls


def test_import_does_not_initialize_optional_resources(metrics):
    module, calls = metrics
    assert module.NLTK_AVAILABLE and module.SENTENCE_TRANSFORMER_AVAILABLE
    assert calls == []


def test_explicit_metrics_initialize_resources_once(metrics):
    module, calls = metrics
    for _ in range(2):
        assert module.calculate_bleu_scores("test", "test")["bleu1"] == 0.5
        assert module.calculate_meteor_score("test", "test") == 0.75
        assert module.calculate_sentence_similarity("test", "test") == 0.8
    assert calls == [("download", "punkt"), ("download", "punkt_tab"),
                     ("download", "wordnet"), ("model", "all-MiniLM-L6-v2")]


def test_unavailable_semantic_model_is_not_repeatedly_loaded(metrics, monkeypatch):
    module, calls = metrics
    def fail(name):
        calls.append(("unavailable", name))
        raise OSError("Model is unavailable")
    monkeypatch.setattr(module, "SentenceTransformer", fail)
    assert module.calculate_sentence_similarity("test", "test") == 0.0
    assert module.calculate_sentence_similarity("test", "test") == 0.0
    assert calls == [("unavailable", "all-MiniLM-L6-v2")]
