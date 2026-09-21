"""Compatibility and command dispatch checks for the package layout."""
import importlib
import pickle
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("legacy,canonical", [
    ("main", "jev_mem.cli"),
    ("jev_mem_demo", "jev_mem.demo"),
    ("test_fixed_memory", "jev_mem.benchmarks.locomo"),
    ("test_longmemeval_chunked", "jev_mem.benchmarks.longmemeval"),
    ("load_dataset", "jev_mem.datasets.locomo"),
    ("load_longmemeval", "jev_mem.datasets.longmemeval"),
])
def test_legacy_import_is_the_canonical_module(legacy, canonical):
    assert importlib.import_module(legacy) is importlib.import_module(canonical)


def test_legacy_dataset_pickle_globals_still_resolve():
    from jev_mem.datasets.locomo import QA
    from jev_mem.datasets.longmemeval import LongMemQuestion

    # Fixed pickle GLOBAL records model imports used by older serialized objects.
    assert pickle.loads(b"cload_dataset\nQA\n.") is QA
    assert pickle.loads(b"cload_longmemeval\nLongMemQuestion\n.") is LongMemQuestion


def test_public_package_import_does_not_initialize_memory_or_providers():
    subprocess.run([sys.executable, "-c", (
        "import sys, jev_mem; "
        "assert 'memory.memory_builder' not in sys.modules; "
        "assert 'typesafe_sdk' not in sys.modules; "
        "assert 'openai' not in sys.modules; "
        "from jev_mem import JevMemConfig; "
        "assert JevMemConfig().write_enabled is False"
    )], check=True, capture_output=True, text=True)


@pytest.mark.parametrize("module,flag", [
    ("jev_mem", "--jev-config"),
    ("jev_mem.demo", "--cache-dir"),
    ("jev_mem.benchmarks.locomo", "--best-of-n"),
    ("jev_mem.benchmarks.longmemeval", "--memory-level"),
])
def test_module_entry_points_expose_expected_options(module, flag):
    result = subprocess.run([sys.executable, "-m", module, "--help"],
                            capture_output=True, text=True, check=True)
    assert flag in result.stdout


def test_application_dispatches_benchmark_as_module(monkeypatch):
    from jev_mem import cli

    monkeypatch.setattr(sys, "argv", ["jev-mem", "--mode", "test", "--input", "sample.json",
                                    "--jev-config", "profile.json", "--no-jev-read"])
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    calls = []
    monkeypatch.setattr(cli.subprocess, "call", lambda command: calls.append(command) or 7)
    assert cli.main() == 7
    command = calls[0]
    assert command[:3] == [sys.executable, "-m", "jev_mem.benchmarks.locomo"]
    assert command[command.index("--dataset") + 1] == "sample.json"
    assert command[command.index("--jev-config") + 1] == "profile.json"
    assert "--no-jev-read" in command


@pytest.mark.parametrize("path", [".env", ".env.local", "data/locomo10.json",
                                  "jev_mem_cache/demo/graph.json", "results/sample.json"])
def test_local_credentials_and_artifacts_are_ignored(path):
    root = Path(__file__).resolve().parents[1]
    if not (root / ".git").exists():
        pytest.skip("Source distributions do not include Git metadata")
    subprocess.run(["git", "check-ignore", "-q", "--", path], cwd=root, check=True)
