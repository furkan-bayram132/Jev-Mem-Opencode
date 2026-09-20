"""Regression tests for the release boundary and project-name compatibility."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

from memory.jev_mem_config import JevMemConfig
from scripts.check_public_release import private_path, scan_content, scan_index, scan_worktree
from scripts.export_public_repo import export


def test_public_manifest_passes_and_excludes_local_data():
    root = Path(__file__).resolve().parents[1]
    names, findings = scan_worktree(root)
    assert not findings, [str(f) for f in findings]
    assert ".env.example" in names
    assert ".env" not in names
    assert "data/locomo10.json" not in names
    assert "README.md" in names
    assert "config/jev_mem.json" in names


@pytest.mark.parametrize("name", [".env", ".env.production", "local.env", "data/locomo10.json",
                                      "graph.json", "results_model/sample.json", "reports/private.md",
                                      "private_cache/observations.json", "vectors/index.pkl",
                                      "../secret.txt", ".agents/settings.json"])
def test_private_artifacts_are_rejected(name):
    assert private_path(name)


@pytest.mark.parametrize("credential", [
    "apikey_" + "a" * 32 + "_" + "b" * 64,
    "sk-" + "x" * 40,
    "github_pat_" + "a" * 50,
    "OPENAI_API_KEY=" + "a1" * 32,
    'api_key="' + "a1" * 32 + '"',
])
def test_credentials_detected_without_printing_values(credential):
    findings = scan_content("example.py", credential.encode())
    assert findings
    assert credential not in "\n".join(map(str, findings))


def test_placeholder_env_and_endpoint_are_allowed():
    assert not scan_content(".env.example", b"OPENAI_API_KEY=\nTYPESAFE_API_KEY=\nTYPESAFE_DEFAULT_MODEL=jev-latest\n")
    endpoint = b"https://YOUR-RESOURCE.services.ai.azure.com/openai/v1/"
    assert not scan_content("README.md", endpoint)
    assert scan_content("README.md", endpoint.replace(b"YOUR-RESOURCE", b"private-tenant"))


def test_export_is_allowlisted_and_refuses_overwrite(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "public-release-files.txt").write_text("README.md\npublic-release-files.txt\n")
    (root / "README.md").write_text("# Jev-Mem\n")
    (root / ".env").write_text("private local configuration")
    output = tmp_path / "Jev-Mem"
    count, archive = export(root, output)
    assert count == 2 and archive.is_file()
    assert not (output / ".env").exists()
    assert (output / "SHA256SUMS").is_file()
    import zipfile
    with zipfile.ZipFile(archive) as bundle:
        assert set(bundle.namelist()) == {"Jev-Mem/README.md", "Jev-Mem/public-release-files.txt",
                                          "Jev-Mem/SHA256SUMS"}
    with pytest.raises(ValueError, match="already exists"):
        export(root, output)


def test_release_refuses_symlinks(tmp_path):
    (tmp_path / "public-release-files.txt").write_text("README.md\n")
    (tmp_path / "target.md").write_text("private content")
    (tmp_path / "README.md").symlink_to(tmp_path / "target.md")
    with pytest.raises(ValueError, match="Symlink"):
        scan_worktree(tmp_path)


def test_tracked_check_reads_index_not_working_copy(tmp_path):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q")
    secret = "sk-" + "x" * 40
    file = tmp_path / "sample.py"
    file.write_text(secret)
    git("add", "sample.py")
    file.write_text("sanitized working copy")
    names, findings = scan_index(tmp_path)
    assert names == ["sample.py"]
    assert findings and secret not in str(findings)
    git("add", "sample.py")
    assert not scan_index(tmp_path)[1]


def test_legacy_imports_and_saved_config_are_compatible(tmp_path):
    from memory import Sys1MemConfig
    from memory.sys1_config import Sys1MemConfig as OldModuleConfig
    from memory.sys1_policies import WritePolicy
    from memory.jev_mem_policies import WritePolicy as NewWritePolicy
    from main import JevMemSystem, Sys1MemSystem, TRGSystem
    from test_fixed_memory import validate_reuse_memory

    assert Sys1MemConfig is OldModuleConfig is JevMemConfig
    assert WritePolicy is NewWritePolicy
    assert Sys1MemSystem is TRGSystem is JevMemSystem
    config = JevMemConfig(write_enabled=True, read_enabled=True)
    (tmp_path / "vectors").mkdir()
    (tmp_path / "graph.json").write_text("{}")
    (tmp_path / "keyword_index.json").write_text("{}")
    (tmp_path / "sys1mem_config.json").write_text(json.dumps(config.to_dict()))
    assert validate_reuse_memory(tmp_path, replace(config, anchor_count=20)) == tmp_path
    with pytest.raises(ValueError, match="construction settings"):
        validate_reuse_memory(tmp_path, replace(config, candidate_top_k=30))


@pytest.mark.parametrize("script", ["main.py", "test_fixed_memory.py"])
def test_cli_advertises_new_and_legacy_names(script):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / script), "--help"],
                            capture_output=True, text=True, check=True)
    for flag in ("--jev-mem", "--jev-config", "--no-jev-write", "--no-jev-read", "--sys1-config"):
        assert flag in result.stdout


def test_synthetic_locomo_example_loads():
    from load_dataset import load_locomo_dataset
    root = Path(__file__).resolve().parents[1]
    samples = load_locomo_dataset(root / "examples/locomo_synthetic.json")
    assert len(samples) == 1 and len(samples[0].qa) == 2
    assert len(samples[0].conversation.sessions[1].turns) == 3
