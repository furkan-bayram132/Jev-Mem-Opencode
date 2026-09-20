#!/usr/bin/env python3
"""Create a new allowlisted source tree and ZIP; never include private history."""
import argparse
import hashlib
from pathlib import Path
import shutil
import zipfile

try:
    from .check_public_release import ROOT, scan_content, scan_worktree
except ImportError:
    from check_public_release import ROOT, scan_content, scan_worktree


def export(root, output):
    root = root.resolve()
    output = output.resolve()
    archive = output.with_suffix(".zip")
    if output == root or output in root.parents or output == archive:
        raise ValueError("Output must be a new directory separate from the source root")
    if output.exists() or archive.exists():
        raise ValueError("Output directory or archive already exists; choose a fresh output path")
    names, findings = scan_worktree(root)
    if findings:
        raise ValueError("Public-source check failed:\n" + "\n".join(map(str, findings)))
    # Validate before writing. All copied paths are explicitly allowlisted.
    output.mkdir(parents=True)
    digests = []
    for name in names:
        source = root / name
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        content = source.read_bytes()
        if source.is_symlink() or scan_content(name, content):
            raise ValueError(f"Source changed during export: {name}")
        target.write_bytes(content)
        shutil.copymode(source, target)
        digests.append(f"{hashlib.sha256(content).hexdigest()}  {name}\n")
    (output / "SHA256SUMS").write_text("".join(digests), encoding="utf-8")
    _, findings = scan_worktree(output)
    if findings:
        raise ValueError("Export validation failed")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in [*names, "SHA256SUMS"]:
            bundle.write(output / name, arcname=f"{output.name}/{name}")
    return len(names), archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=Path("dist/Jev-Mem"))
    args = parser.parse_args()
    try:
        count, archive = export(args.root, args.output)
    except (OSError, ValueError) as exc:
        print(f"Export failed: {exc}")
        return 1
    print(f"Exported {count} public files to {args.output}; archive: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
