# Aether

A free, fully autonomous agent framework. Give it a task; it plans, acts with real tools (shell, files, web, code execution), observes the results, recovers from failures, and reports back when the job is done.

```
TASK -> PLAN -> [ ACT -> OBSERVE -> THINK ] x N -> RESULT
```

## What it does

- **Autonomous loop** - the agent chains tool calls on its own until the task is finished, with a configurable hard stop (`max_iterations`).
- **Planning** - every task starts with a checklist the agent follows and adapts (disable with `--no-plan`).
- **10 built-in tools** - shell, file read/write/edit, directory listing, Python execution, DuckDuckGo web search, URL fetching, long-term memory (remember/recall).
- **Any LLM backend** - any OpenAI-compatible API (Z.ai, OpenRouter, Groq, Google AI Studio, llama.cpp, vLLM...) and local Ollama. If it speaks tool-calling, Aether can drive it.
- **Stuck detection** - repeating the same failed action 3 times triggers an automatic strategy-change nudge instead of an infinite loop.
- **Long-term memory** - durable notes persist across sessions in plain Markdown under `.aether/notes.md`; every session is transcribed to JSONL for replay/audit.
- **Safety model** - a hard blocklist that *never* runs catastrophic commands, plus a confirmation tier for impactful ones.

## Why it is free

Aether is just Python and two tiny dependencies (`requests`, `PyYAML`). The cost depends entirely on the backend you plug in:

| Backend | Cost | Notes |
| --- | --- | --- |
| Ollama (local) | Free, offline | `ollama pull llama3.1` / `qwen2.5-coder` / any tool-calling model |
| Z.ai GLM Flash models | Free tier | `base_url: https://api.z.ai/api/paas/v4` |
| OpenRouter `:free` models | Free tier | `base_url: https://openrouter.ai/api/v1` |
| Groq | Free tier | very fast inference |
| Google AI Studio | Free tier | OpenAI-compatible endpoint available |
| llama.cpp / vLLM server | Free, local | any GGUF / served model |

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

## Configuration

Precedence: CLI flags > environment variables (`AETHER_PROVIDER`, `AETHER_BASE_URL`, `AETHER_API_KEY`, `AETHER_MODEL`, `AETHER_MAX_ITERATIONS`, `AETHER_AUTO_APPROVE`, `AETHER_WORKSPACE`) > `config.yaml` > defaults. See `config.example.yaml`.

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
  agent.py        # the act-observe-think loop, stuck detection, REPL continuity
  cli.py          # one-shot + interactive mode
  config.py       # YAML + env + CLI flag merging
  llm.py          # OpenAI-compatible and Ollama backends, retries
  memory.py       # session JSONL transcripts + notes.md
  planner.py      # checklist generation
  tools/          # base registry + all built-in tools
```

## Add your own tool

```python
# aether/tools/my_tool.py
from .base import Tool

class SendEmail(Tool):
    name = "send_email"
    description = "Send an email via SMTP."
    parameters = {
        "type": "object",
        "properties": {"to": {"type": "string"}, "body": {"type": "string"}},
        "required": ["to", "body"],
    }
    def run(self, args: dict) -> str:
        ...  # return a short string; it goes straight back to the model
```

Register it in `aether/tools/__init__.py` inside `build_default_tools()`. That is the whole extension contract.

## License

MIT - see [LICENSE](LICENSE).
