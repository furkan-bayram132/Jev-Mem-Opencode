# Project layout

```text
jev_mem/
  system.py          Public build/query API
  cli.py             Application argument parsing and dispatch
  demo.py            Offline demonstration
  datasets/          LoCoMo and LongMemEval schemas and loaders
  benchmarks/        Benchmark runners, separate from regression tests
memory/              Graph storage, controllers, retrieval, and evaluation
utils/               Shared provider adapters and scoring utilities
config/              Checked-in experiment profiles
examples/            Original synthetic inputs
data/                Downloaded datasets (ignored by Git)
tests/               Offline regression and compatibility tests
scripts/             Release tools and retrieval diagnostics
docs/                Developer guides and figures
```

## Public API and commands

Use `from jev_mem import JevMemSystem, JevMemConfig` for application integration.
The package also exports `MemoryBuilder` and `QueryEngine`. Public exports are
loaded lazily, so importing `jev_mem` alone does not initialize model providers.

| Task | From a source checkout | After installing the package |
| --- | --- | --- |
| Build/query memory | `python -m jev_mem` | `jev-mem` |
| Offline demo | `python -m jev_mem.demo` | `jev-mem-demo` |
| LoCoMo benchmark | `python -m jev_mem.benchmarks.locomo` | `jev-mem-eval` |
| LongMemEval benchmark | `python -m jev_mem.benchmarks.longmemeval` | `jev-mem-longmemeval` |

Install a development checkout with `python -m pip install -e .`.
Dataset and output paths are relative to the current working directory unless
an absolute path is supplied. Configuration and datasets are explicit inputs;
the wheel contains Python code, while the source distribution includes profiles,
examples, documentation, and tests.

## Where to make changes

Memory algorithms live in `memory/`: `memory_builder.py` owns ingestion,
`query_engine.py` owns querying, and the `jev_mem_*` modules implement typed
control. `graph_db.py` and `vector_db.py` own storage. These module paths remain
stable for callers and persisted objects.

Dataset parsing belongs in `jev_mem/datasets/`. Benchmark orchestration belongs
in `jev_mem/benchmarks/`; it imports the shared memory implementation. Keep
regression tests in `tests/`, with synthetic inputs and mocked model calls.
Repository export and diagnostic tools belong in `scripts/`.

## Naming and migration

The full project title is **Jev-Mem: System-One Controlled Agentic Memory**.
Jev-Mem is an agentic memory system that uses a System-One controller to
organize and retrieve multi-relational memories, with a System-Two language
model for answer synthesis.

| Context | Canonical name |
| --- | --- |
| Project in prose | `Jev-Mem` |
| Python package and saved metadata key | `jev_mem` |
| Distribution, console command, and controller trace identifier | `jev-mem` |
| Application class | `JevMemSystem` |
| Configuration class / argument | `JevMemConfig` / `jev_config` |
| Model used for typed control decisions | TypeSafe Jev |

System One and System Two name architectural roles. MAGMA names the upstream
work and retained baseline. `TemporalResonanceGraphMemory` (TRG) names the
shared graph backend, not the project or its application API.

The root `main.py`, `jev_mem_demo.py`, `test_fixed_memory.py`,
`test_longmemeval_chunked.py`, `load_dataset.py`, and `load_longmemeval.py`
are small compatibility entry points. Their implementations live under
`jev_mem/`; edit those implementations rather than adding logic to the wrappers.
These imports resolve to the canonical modules, preserving class identity and
module-level patches.

The earlier Sys1Mem-branded scripts, modules, API aliases, and CLI flags have
been removed. Use `python -m jev_mem.demo`, `JevMemSystem`, `JevMemConfig`,
`jev_config=...`, `--jev-mem`, `--jev-config`, `--no-jev-write`, and
`--no-jev-read`. Import controllers from `memory.jev_mem_policies` and
`memory.jev_mem_retrieval`.

Existing caches remain readable: `memory/cache_compat.py` recognizes the old
configuration filename and converts old node metadata to `jev_mem` when loading.
Current metadata wins when both forms exist. Saving writes the current metadata
and `jev_mem_config.json`; source cache files are not rewritten merely by loading
them. Existing configuration/version checks still apply.

## Local artifacts

Keep credentials in `.env`, external datasets under `data/`, and generated
graphs/results in their default cache and output directories. `.gitignore`
excludes these locations. New source files must be added to both
`public-release-files.txt` and `MANIFEST.in`; see [releasing](releasing.md).
