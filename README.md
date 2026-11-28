# Aether

[![PyPI - Version](https://img.shields.io/pypi/v/aether-agent-framework)](https://pypi.org/project/aether-agent-framework/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/aether-agent-framework)](https://pypi.org/project/aether-agent-framework/)
[![CI](https://github.com/Atikur-rahman-ar/Localrepo/actions/workflows/ci.yml/badge.svg)](https://github.com/Atikur-rahman-ar/Localrepo/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-74%20passing-brightgreen)](https://github.com/Atikur-rahman-ar/Localrepo/actions)
[![License](https://img.shields.io/github/license/Atikur-rahman-ar/Localrepo)](LICENSE)

A free, fully autonomous agent framework. Give it a task; it plans, acts with real tools (shell, files, web, code execution), observes the results, recovers from failures, and reports back when the job is done.

```
TASK -> PLAN -> [ ACT -> OBSERVE -> THINK ] x N -> RESULT
```

## What it does

- **Autonomous loop** - the agent chains tool calls on its own until the task is finished, with a configurable hard stop (`max_iterations`).
- **Planning** - every task starts with a checklist the agent follows and adapts (disable with `--no-plan`).
- **19 built-in tools + sub-agents** - shell, file read/write/edit, directory listing, Python execution, DuckDuckGo web search, URL fetching, generic HTTP calls, file downloads, Wikipedia/arXiv/GitHub search, SQLite queries, chart rendering, long-term memory (remember/recall), email sending, calendar event files - and `delegate_task` for handing subtasks to sub-agents.
- **Live Web UI** - `python -m aether.web` and watch the agent think and act in real time: plan, tool calls, observations and the final result stream into your browser as they happen.
- **Multi-agent handoffs** - the agent can spawn sub-agents with fresh context and their own loop budget for self-contained subtasks; depth and iteration limits keep the tree bounded, and sub-agent activity streams into the same dashboard.
- **Any LLM backend** - any OpenAI-compatible API (Z.ai, OpenRouter, Groq, Google AI Studio, llama.cpp, vLLM...) and local Ollama. If it speaks tool-calling, Aether can drive it. A built-in `mock` backend runs a scripted demo with zero network access.
- **Stuck detection** - repeating the same failed action 3 times triggers an automatic strategy-change nudge instead of an infinite loop.
- **Long-term memory** - durable notes persist across sessions in plain Markdown under `.aether/notes.md`; every session is transcribed to JSONL for replay/audit.
- **Safety model** - a hard blocklist that *never* runs catastrophic commands, plus a confirmation tier for impactful ones.

## Why it is free

Aether is just Python and two tiny dependencies (`requests`, `PyYAML`); the Web UI adds one more (`Flask`). The cost depends entirely on the backend you plug in:

| Backend | Cost | Notes |
| --- | --- | --- |
| Ollama (local) | Free, offline | `ollama pull llama3.1` / `qwen2.5-coder` / any tool-calling model |
| Z.ai GLM Flash models | Free tier | `base_url: https://api.z.ai/api/paas/v4` |
| OpenRouter `:free` models | Free tier | `base_url: https://openrouter.ai/api/v1` |
| Groq | Free tier | very fast inference |
| Google AI Studio | Free tier | OpenAI-compatible endpoint available |
| llama.cpp / vLLM server | Free, local | any GGUF / served model |

## Installation

From PyPI (recommended):

```bash
pip install aether-agent-framework           # core: CLI + all keyless tools
pip install "aether-agent-framework[web]"    # + the live dashboard (Flask)
pip install "aether-agent-framework[all]"    # + charts (matplotlib) + web
```

That installs two commands: `aether` (one-shot tasks + REPL) and `aether-web` (the dashboard).

From source:

```bash
git clone https://github.com/Atikur-rahman-ar/Localrepo aether
cd aether
pip install -e ".[web]"
```

## Quickstart

```bash
git clone https://github.com/Atikur-rahman-ar/Localrepo aether
cd aether
pip install -r requirements.txt

# Hosted backend (pick a free-tier model from your provider)
export AETHER_API_KEY="your-key"
python -m aether --model glm-4.7-flash "scaffold a flask todo app with tests and run the tests"

# 100% free and offline with Ollama
ollama pull llama3.1
python -m aether --provider ollama --model llama3.1 \
    --workspace ./demo "write a fib.py with memoization and prove it with tests"
```

With no task argument you get the interactive REPL:

```
$ python -m aether --provider ollama
aether> analyze the csv in ./data and plot monthly totals
```

REPL commands: `/reset` new conversation, `/notes` show long-term memory, `/forget` wipe notes, `/tools` list tools, `/help`, `/exit`.

## Live Web UI

```bash
python -m aether.web --workspace ./demo
# open http://127.0.0.1:5000
```

A local dashboard where you type tasks and watch the loop execute:

- every step streams live over Server-Sent Events: **task → plan → thinking → tool calls with arguments → results → final answer**;
- per-run overrides for provider, `base_url`, model and `max_iterations` (API keys stay in the server environment - never typed in the browser);
- run history in the sidebar, click any past run to replay its full trace;
- a **Stop** button that halts the agent before its next model turn or tool call;
- no key at hand? pick the `mock` provider for an offline scripted demo.

Optional hardening: set `AETHER_WEB_TOKEN` and every API call must present it (the UI asks for it once and stores it in `localStorage`). The server binds to `127.0.0.1` by default - it is a personal dashboard, not something to expose to the internet.

## Multi-agent handoffs

Big tasks decompose well when focused pieces can be handed off completely. The `delegate_task` tool spawns a **sub-agent** with:

- a **fresh conversation** - the child does not inherit the parent's context (pass what it needs via the `context` argument);
- its **own loop budget** (`delegate_max_iterations`, default 15) - a delegation can never outlive its parent;
- the **same toolbelt** minus further delegation once `max_delegate_depth` is reached;
- the parent's **stop flag** - stopping a run stops the whole agent tree;
- live **sub-agent events** in the Web UI, labelled with their nesting depth.

```yaml
# config.yaml
max_delegate_depth: 1        # 0 disables delegation; 2 allows sub-agents to delegate too
delegate_max_iterations: 15  # loop budget per sub-agent
```

Defaults are deliberately conservative: depth 1 means the top-level agent may delegate, sub-agents may not. Raise it when a task genuinely needs fan-out (e.g. "refactor these five modules" delegating one module each). The parent sees the child's final report as the tool result, prefixed with its depth.

## Configuration

Precedence: CLI flags > environment variables (`AETHER_PROVIDER`, `AETHER_BASE_URL`, `AETHER_API_KEY`, `AETHER_MODEL`, `AETHER_MAX_ITERATIONS`, `AETHER_AUTO_APPROVE`, `AETHER_WORKSPACE`, `AETHER_CUSTOM_TOOLS`, `AETHER_MAX_DELEGATE_DEPTH`, `AETHER_DELEGATE_MAX_ITERATIONS`) > `config.yaml` > defaults. See `config.example.yaml`.

For `send_email`, the SMTP settings are also environment variables: `AETHER_SMTP_HOST`, `AETHER_SMTP_PORT`, `AETHER_SMTP_USER`, `AETHER_SMTP_PASS` (use an app-specific password where offered).

## Built-in tools

| Tool | What it does |
| --- | --- |
| `run_command` | shell in the workspace, stdout/stderr/exit code back to the model |
| `read_file` | read text files, optional line ranges |
| `write_file` | create/overwrite files, auto-creates directories |
| `edit_file` | exact-string replacement with uniqueness check |
| `list_dir` | recursive listing with noise dirs skipped |
| `execute_python` | run Python in a subprocess for math/data/scripts |
| `web_search` | DuckDuckGo search, no API key |
| `fetch_url` | fetch a page, return readable text |
| `remember` | write a durable fact to long-term notes |
| `recall` | search long-term notes |
| `http_request` | call any HTTP API: method, headers, raw or JSON body, status + body back |
| `download_file` | download binary/text files into the workspace (200 MB cap) |
| `search_wikipedia` | Wikipedia search with snippets; optional full article extract |
| `search_arxiv` | paper search: titles, authors, abstracts, PDF links |
| `search_github` | repo/issue/user search via the public GitHub API (no key) |
| `run_sqlite` | one SQL statement against a local SQLite file; read-only by default |
| `render_chart` | line/bar/scatter/pie/histogram charts saved as PNG |
| `send_email` | SMTP email; credentials from env only; `dry_run=true` previews without sending |
| `create_calendar_event` | writes an RFC 5545 `.ics` file into `workspace/calendar/`, importable everywhere |
| `delegate_task` | spawns a sub-agent for a self-contained subtask; depth/iteration capped; result returns to the parent |

Everything runs keyless on `requests` alone. Optional extras: `render_chart` uses matplotlib and the Web UI uses Flask - `pip install matplotlib flask` (a clear error is returned if missing).

## Tests & CI

```bash
pip install -e ".[dev,web]"
pytest
```

74 tests cover the config loader, memory, the tool registry, file-tool sandboxing, the custom-tool loader, the agent loop (with a scripted LLM and the offline mock backend), multi-agent delegation, the productivity tools and every Web UI endpoint - all without network access. The offline `mock` provider exists precisely so the full loop is testable anywhere.

GitHub Actions runs the suite on Python 3.10-3.12 plus a build job that compiles the sdist/wheel, validates metadata with twine and smoke-tests the wheel in a clean venv (`.github/workflows/ci.yml`).

## Safety model

Three tiers:

1. **Hard blocklist (never runs, even with `--auto`)** - recursive `rm` of `/`, `~`, `$HOME` or system directories, `mkfs`, raw disk writes (`dd of=/dev/...`), fork bombs, `shutdown`/`reboot`, global `chmod 777`.
2. **Confirmation tier** - `sudo`, package installs, `git push`, `curl | sh`, `docker` ask you `y/N` first. Skip prompts with `--auto` (the blocklist still applies).
3. **Everything else** - runs directly in the workspace.

### A note on "uncensored"

Aether itself puts **no restrictions on what tasks you can give it**. Two things remain by design and are not bugs:

- Your chosen LLM provider's usage policy still applies to the model's outputs. Aether is an agent harness, not a jailbreak tool.
- The destructive-command blocklist exists so a confused model cannot wipe your disk.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full loop, message format and design decisions.

```
aether/
  agent.py        # the act-observe-think loop, stuck detection, event stream, stop flag
  cli.py          # one-shot + interactive mode
  config.py       # YAML + env + CLI flag merging
  llm.py          # OpenAI-compatible, Ollama and mock backends, retries
  memory.py       # session JSONL transcripts + notes.md
  planner.py      # checklist generation
  web/            # live Web UI: Flask server, SSE streaming, run manager
  tools/          # base registry, all built-in tools, delegate.py (sub-agents)
tests/            # pytest suite (offline: scripted LLM + mock provider)
```

## Add your own tools

The zero-code way: create a folder, drop in plain Python files, point Aether at it.

```python
# ~/aether-tools/shout.py
from aether.tools.base import Tool

class Shout(Tool):
    name = "shout"
    description = "Repeat a message in capital letters."
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }
    def run(self, args: dict) -> str:
        return args["text"].upper() + "!"
```

Then either `export AETHER_CUSTOM_TOOLS=~/aether-tools` or set `custom_tools_dir` in `config.yaml`. Every `*.py` file is imported at startup and every `Tool` subclass found is registered - a tool whose name collides with a built-in replaces it (handy for overrides). Broken files are skipped with a warning instead of killing the run.

Alternatively register tools directly in `build_default_tools()` in `aether/tools/__init__.py`. That is the whole extension contract.

## License

MIT - see [LICENSE](LICENSE).