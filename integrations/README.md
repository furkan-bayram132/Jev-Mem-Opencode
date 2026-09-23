# Use Jev-Mem as a memory server

Jev-Mem's System One handles memory writing and retrieval on its own. The model
you already use -- opencode, Claude Code, Gemini CLI, Codex, or anything else
that speaks MCP -- stays in place as System Two and writes the answers.

The agent never sees the graph. It sends a question and receives only the
observations Jev selected, so the context stays bounded as the memory grows.

## Install

```bash
python -m pip install -e .
cp .env.example .env    # then fill in TYPESAFE_API_KEY or OPENROUTER_API_KEY
```

This needs Python 3.11 or newer. On an older interpreter the editable install is
refused and the `jev-mem-mcp` command is never created; run the server as a
module from a source checkout instead, and give the client an explicit `cwd`:

```json
{
  "command": ["/path/to/checkout/.venv/bin/python", "-m", "jev_mem.mcp_server",
              "--cache-dir", ".jev-mem"],
  "cwd": "/path/to/checkout"
}
```

### Which key drives System One

System-One decisions are typed Noul and Choice questions about a state, not chat
completions, so an ordinary chat-model key cannot answer them. Two hosts serve
that protocol, and a profile picks between them:

| Profile | Host | Key |
| --- | --- | --- |
| `config/jev_mem.json` (default) | `api.typesafe.ai/v1/systemone` | `TYPESAFE_API_KEY` |
| `config/jev_mem_openrouter.json` | `openrouter.ai/api/alpha/decisions` | `OPENROUTER_API_KEY` |

The OpenRouter route publishes Jev as `~typesafe/jev-latest` through its
Decisions API and bills your OpenRouter account, so an OpenRouter key is enough:

```bash
jev-mem-mcp --jev-config config/jev_mem_openrouter.json --cache-dir .jev-mem
```

The request and response bodies are identical on both hosts; only the path
differs, which `memory/jev_endpoint.py` rewrites in the HTTP transport.

Note that an OpenRouter *chat* model still cannot serve this -- it is the
Decisions API that answers, not `/v1/chat/completions`. Chat models belong on the
System-Two side, as the agent you connect this server to.

Without a usable key the server still runs, but every decision falls back to
heuristics and System One is effectively off. Check the decision log to tell the
two apart (see below).

Run it once by hand to confirm it starts:

```bash
jev-mem-mcp --jev-mock --cache-dir ./.jev-mem-smoke
```

It waits on stdin and prints nothing to stdout -- that is correct for stdio MCP.
Press Ctrl+C to exit.

## opencode

Copy [`opencode.json`](opencode.json) into your project root, or merge its `mcp`
block into an existing `opencode.json`. Confirm the connection with `/mcp`.

## Claude Code

Copy [`claude_code.json`](claude_code.json) to `.mcp.json` in your project root,
or run:

```bash
claude mcp add jev-mem -- jev-mem-mcp --cache-dir .jev-mem
```

## Gemini CLI, Codex, and other MCP clients

Every stdio MCP client needs the same three things: the command
`jev-mem-mcp`, the arguments `--cache-dir .jev-mem`, and the key named by the
active profile in the environment. Only the config file's shape differs.

## Tell the agent to use it

Connecting the server is not enough; the model decides when to call the tools.
Append [`AGENTS.md`](AGENTS.md) to your project's `AGENTS.md` (opencode, Codex)
or `CLAUDE.md` (Claude Code).

## Tools

| Tool | Purpose |
| --- | --- |
| `memory_recall(query, top_k=8, output_format="compact")` | Retrieve evidence. Returns observations and a decision trace, never an answer. `top_k` is capped at 25. |
| `memory_remember(text, timestamp=None, source=None, tags=None)` | Store one durable observation. |
| `memory_stats()` | Memory size, active profile, decision log path. |

## Options

| Flag | Default | Purpose |
| --- | --- | --- |
| `--cache-dir` | `./.jev-mem` | Graph, vectors, and decision log. One directory per project. |
| `--jev-config` | `config/jev_mem.json` | Jev-Mem profile; `config/jev_mem_openrouter.json` reaches Jev through OpenRouter. See [`config/README.md`](../config/README.md). |
| `--embedding-model` | `minilm` | `minilm` runs locally; `openai` needs `OPENAI_API_KEY`. |
| `--jev-mock` | off | Deterministic mock decisions for smoke tests. Never for measurement. |

Reopening a directory whose saved profile differs in its write settings is
refused rather than silently mixing two memories.

## Confirm System One is actually driving

```bash
tail .jev-mem/decisions.jsonl
```

- `"event": "jev_decision"` with `"source": "jev"` -- live System-One decisions.
  `"cache"` is a repeat of an identical question; `"mock"` means `--jev-mock`.
- `"event": "query"` carries the retrieval trace. `"llm_calls": 0` confirms no
  answer model ran during retrieval, and `stopping_decision` says why the
  search stopped.
- `"event": "jev_fallback"` means a decision could not be obtained and
  heuristics took over. Frequent entries usually mean a missing or rejected key
  for whichever host the active profile names.
