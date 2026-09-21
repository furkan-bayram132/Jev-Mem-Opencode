"""Naming contracts and migration of historical memory metadata."""
import importlib.util
import inspect
from pathlib import Path
import tomllib

import pytest

from memory.cache_compat import memory_config_path
from memory.graph_db import EventNode, EpisodeNode, SessionNode, Link


def test_public_api_and_distribution_use_the_canonical_project_name():
    import jev_mem
    import memory

    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    assert project["name"] == "jev-mem"
    assert project["description"] == "System-One Controlled Agentic Memory"
    assert f'# Jev-Mem: {project["description"]}' in (root / "README.md").read_text()
    assert f'{{Jev-Mem}}: {project["description"]}' in (root / "CITATION.bib").read_text()
    for cls in [jev_mem.JevMemSystem, jev_mem.MemoryBuilder, jev_mem.QueryEngine]:
        parameters = inspect.signature(cls).parameters
        assert "jev_config" in parameters and "sys1_config" not in parameters
    assert not hasattr(memory, "Sys1MemConfig")
    for module in ["sys1mem_demo", "memory.sys1_config", "memory.sys1_policies", "memory.sys1_retrieval"]:
        assert importlib.util.find_spec(module) is None


@pytest.mark.parametrize("node_class", [EventNode, EpisodeNode, SessionNode])
def test_cache_metadata_migration_preserves_evidence_and_current_fields(node_class):
    attrs = {
        "original_text": "Original evidence.",
        "source": "sys1mem_consolidation",
        "sys1mem": {"admission": None, "memory_type": {"preference": 0.7}, "controller": "old"},
        "jev_mem": {"controller": "mock", "consolidation": []},
    }
    data = node_class(attributes=attrs).to_dict()
    node = node_class.from_dict(data)
    assert node.attributes["original_text"] == "Original evidence."
    assert node.attributes["source"] == "jev_mem_consolidation"
    assert node.attributes["jev_mem"] == {
        "admission": None, "memory_type": {"preference": 0.7},
        "controller": "mock", "consolidation": [],
    }
    assert "sys1mem" not in node.to_dict()["attributes"]
    assert "sys1mem" in attrs  # Loading does not mutate the source dictionary.


def test_cache_link_controller_name_is_normalized():
    from memory.graph_db import LinkType

    link = Link(source_node_id="a", target_node_id="b", link_type=LinkType.SEMANTIC,
                metadata={"controller": "sys1mem", "probability": 0.8})
    loaded = Link.from_dict(link.to_dict())
    assert loaded.metadata == {**link.metadata, "controller": "jev-mem"}


def test_current_cache_config_takes_precedence(tmp_path):
    old = tmp_path / "sys1mem_config.json"
    old.write_text("{}")
    assert memory_config_path(tmp_path) == old
    current = tmp_path / "jev_mem_config.json"
    current.write_text("{}")
    assert memory_config_path(tmp_path) == current
