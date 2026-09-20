#!/usr/bin/env python3
"""Check public source without printing credential values. Standard library only.

Default: inspect the explicit release allowlist in the working tree.
--tracked: inspect all stage-zero Git index blobs, including staged additions.
This is a pattern guardrail, not a historical or semantic privacy audit.
"""
import argparse
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "public-release-files.txt"
MAX_FILE_BYTES = 5 * 1024 * 1024
PATTERNS = (
    ("TypeSafe credential", re.compile(rb"apikey_[A-Za-z0-9]{20,}_[A-Za-z0-9]{20,}")),
    ("OpenAI credential", re.compile(rb"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}")),
    ("GitHub credential", re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("AWS access key", re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("private key", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("credential assignment", re.compile(
        rb"(?im)(?:[A-Z_]*(?:API_KEY|ACCESS_TOKEN|CLIENT_SECRET|PASSWORD)|api_key|access_token)"
        rb"[\"']?[ \t]*[:=][ \t]*[\"']?([A-Za-z0-9_+/=-]{24,})")),
    ("personal absolute path", re.compile(rb"/(?:Users|home)/[A-Za-z0-9_.-]+/")),
)
AZURE = re.compile(rb"https://([A-Za-z0-9-]+)\.(?:services\.ai\.azure\.com|openai\.azure\.com)")
PRIVATE_SUFFIXES = {".pkl", ".pickle", ".npy", ".npz", ".faiss", ".jsonl", ".log",
                    ".pem", ".key", ".pt", ".pth", ".ckpt", ".safetensors"}


@dataclass(frozen=True)
class Finding:
    path: str
    reason: str
    line: int = 0

    def __str__(self):
        location = self.path + (f":{self.line}" if self.line else "")
        return f"{location}: {self.reason}"


def private_path(name):
    path = PurePosixPath(name)
    parts = tuple(p.lower() for p in path.parts)
    leaf = path.name.lower()
    if path.is_absolute() or ".." in parts or "\\" in name:
        return True
    if leaf != ".env.example" and (leaf == ".env" or leaf.startswith(".env.") or leaf.endswith(".env")):
        return True
    if path.suffix.lower() in PRIVATE_SUFFIXES:
        return True
    if leaf in {"graph.json", "keyword_index.json", "jev_mem_config.json", "sys1mem_config.json",
                ".ds_store", "skill.md"} or leaf.startswith(("credentials", "service-account")):
        return True
    if any(p in {".git", ".venv", "venv", "__pycache__", ".agents", ".codex", "reports", "vectors"}
           or "cache" in p or p.startswith(("results", "locomo_trg", "longmem_")) for p in parts[:-1]):
        return True
    if parts and parts[0] == "data" and name != "data/README.md":
        return True
    return name in {"examples/locomo_sample.json", "examples/longmemeval_sample.json"}


def scan_content(name, content):
    findings = []
    if private_path(name):
        findings.append(Finding(name, "private artifact path"))
    if len(content) > MAX_FILE_BYTES:
        findings.append(Finding(name, "exceeds public-file size limit"))
    for label, pattern in PATTERNS:
        for match in pattern.finditer(content):
            findings.append(Finding(name, label, content[:match.start()].count(b"\n") + 1))
    for match in AZURE.finditer(content):
        tenant = match.group(1).lower()
        if tenant not in {b"your-resource", b"your-resource-name", b"example"}:
            findings.append(Finding(name, "non-placeholder Azure resource endpoint",
                                    content[:match.start()].count(b"\n") + 1))
    return findings


def public_paths(root):
    names = []
    for line in (root / MANIFEST).read_text(encoding="utf-8").splitlines():
        name = line.strip()
        if not name or name.startswith("#"):
            continue
        if private_path(name) or name in names:
            raise ValueError(f"Invalid or duplicate public manifest path: {name}")
        path = root / name
        if any(p.is_symlink() for p in (path, *path.parents)):
            # macOS /tmp itself is a system symlink; inspect only within root.
            relative_parts = PurePosixPath(name).parts
            if any(root.joinpath(*relative_parts[:i]).is_symlink()
                   for i in range(1, len(relative_parts) + 1)):
                raise ValueError(f"Symlink not allowed in release: {name}")
        if not path.is_file():
            raise ValueError(f"Missing public file: {name}")
        names.append(name)
    if not names:
        raise ValueError("Public release manifest is empty")
    return names


def scan_worktree(root):
    names = public_paths(root)
    findings = []
    for name in names:
        findings.extend(scan_content(name, (root / name).read_bytes()))
    return names, findings


def scan_index(root):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)

    top = Path(git("rev-parse", "--show-toplevel").decode().strip()).resolve()
    if top != root.resolve():
        raise ValueError("--root must be the Git repository root")
    entries = git("ls-files", "--stage", "-z").split(b"\0")
    names, findings = [], []
    for entry in filter(None, entries):
        header, raw_name = entry.split(b"\t", 1)
        mode, oid, stage = header.split()
        name = raw_name.decode("utf-8")
        names.append(name)
        if mode not in {b"100644", b"100755"} or stage != b"0":
            findings.append(Finding(name, "symlink, submodule, or unresolved index entry"))
            continue
        content = git("cat-file", "blob", oid.decode())
        findings.extend(scan_content(name, content))
    if not names:
        raise ValueError("Git index is empty; stage public files before running --tracked")
    return names, findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--tracked", action="store_true")
    args = parser.parse_args()
    try:
        names, findings = scan_index(args.root) if args.tracked else scan_worktree(args.root)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        # Never dump subprocess output or file contents in an error report.
        print(f"Public release check could not complete: {type(exc).__name__}")
        return 2
    if findings:
        print("Public release check failed (values redacted):")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print(f"Public release check passed: {len(names)} files; no credential patterns or private artifacts found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
