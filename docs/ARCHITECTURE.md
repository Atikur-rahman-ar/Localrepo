# Aether architecture

## The loop

```
                +---------------------+
   user task -> | planner.py          |  optional checklist (max 10 steps)
                +---------------------+
                          |
                          v
   +--------------------------------------------------------------+
   |                     agent.py : _loop()                       |
   |                                                              |
   |   +----------------+      tool_calls                        |
   |   | llm.py         | --------------------------+            |
   |   | (OpenAI-compat |                           |            |
   |   |  or Ollama)    | <-------------------------+            |
   |   +----------------+      results appended            |            |
   |          ^                                            v            |
   |          |                               +------------------------+ |
   |          +-------------------------------| tools/ ToolRegistry    | |
   |        next iteration                    | shell, files, web, py, | |
   |                                          | memory (19 built-ins)  | |
   |                                          +------------------------+ |
   |                                                              |
   |   no tool_calls -> final answer                              |
   |   identical action x3 -> strategy-change nudge               |
   |   max_iterations hit -> hard stop                            |
   |   every step -> on_event(dict) -> Web UI (SSE) / observers   |
   |   stop_flag set  -> halt before next turn or tool call       |
   +--------------------------------------------------------------+
                          |
                          v
                final summary + JSONL transcript + notes.md updates
```

## Message format

Internally the conversation is a list of normalised messages:

```json
{"role": "system",    "content": "..."}
{"role": "user",      "content": "..."}
{"role": "assistant", "content": "...", "tool_calls": [{"id": "...", "name": "...", "arguments": "{...}"}]}
{"role": "tool",      "tool_call_id": "...", "content": "result string"}
```

`llm.py` converts this to the exact wire format of the chosen provider
(OpenAI-compatible `chat/completions` or Ollama `api/chat`), so the agent
logic never cares which backend is plugged in.

## Module responsibilities

| Module | Responsibility |
| --- | --- |
| `config.py` | merge YAML file, environment variables and CLI flags into one `Config` |
| `llm.py` | provider backends, request retries (3x backoff), format normalisation |
| `planner.py` | best-effort checklist generation; failure never blocks execution |
| `agent.py` | the act-observe-think loop, stuck detection, REPL continuity |
| `tools/base.py` | `Tool` contract + `ToolRegistry` (schema export, JSON-arg parsing, error wrapping, output truncation) |
| `tools/shell.py` | shell execution, hard blocklist, confirmation tier |
| `tools/files.py` | workspace-sandboxed read/write/edit/list |
| `tools/web.py` | keyless DuckDuckGo search + page fetching |
| `tools/net.py` | generic HTTP API calls + workspace-sandboxed file downloads |
| `tools/knowledge.py` | keyless Wikipedia, arXiv and GitHub public-API search |
| `tools/data.py` | SQLite queries (read-only by default) + PNG chart rendering (matplotlib optional) |
| `tools/productivity.py` | `send_email` (SMTP, env credentials, dry-run) + `create_calendar_event` (RFC 5545 `.ics` writer) |
| `tools/loader.py` | imports `*.py` plugins from `custom_tools_dir` and registers every `Tool` subclass found |
| `python_exec.py` | subprocess Python execution with timeout |
| `memory.py` | JSONL session transcripts + `notes.md` long-term memory |
| `cli.py` | argument parsing, one-shot mode, interactive REPL |
| `web/server.py` | Flask app factory: run manager (one thread per run), REST API, SSE event stream, optional `AETHER_WEB_TOKEN` auth |
| `web/static/index.html` | single-file dashboard (no build step, no CDN): live event feed, history, composer, stop button |

## Design decisions

- **Filesystem as database.** Notes are Markdown, transcripts are JSONL. No
  server, no lock-in, everything is greppable and versionable.
- **Truncate, don't drop.** Tool output is capped (`max_tool_output`) and the
  model is told how much was dropped, so it can re-read with line ranges
  instead of failing silently.
- **Failures go back to the model.** Tool exceptions are formatted as `ERROR:`
  strings and returned as tool results. The model sees them and adapts - that
  is the whole point of an autonomous loop.
- **Stuck detection is cheap.** Three identical (tool, canonical-args) actions
  in a row inject a system nudge. No extra LLM calls, no judge model.
- **Safety is layered, not absolute.** A hard blocklist for catastrophic
  commands (never runs, even with `--auto`), a confirmation tier for impactful
  ones, and free rein otherwise. This keeps full-auto mode survivable.
- **Observation must not break execution.** The loop emits events through one
  optional callback wrapped in a bare `except`; a crashing observer or Web UI
  can never take down an agent run. The Web UI thread is also fully detached:
  a run outlives its dashboard tab and can be replayed from the event log.

## Extending

Subclass `Tool`, set `name` / `description` / `parameters`, implement
`run(args) -> str`. Drop the file into a folder and point `custom_tools_dir`
(or `AETHER_CUSTOM_TOOLS`) at it - the loader registers every `Tool` subclass
it finds. Anything that can be expressed as a Python function returning a
string can become a tool.

## Limitations

- Vision/image inputs are not wired up (text-only conversation history).
- No parallel tool execution within one step (calls in one assistant turn run
  sequentially, in order).
- The Web UI streams with Flask's built-in server and one thread per run; it is
  meant for a single local user. Do not expose it to the public internet, and
  set `AETHER_WEB_TOKEN` if it runs on a shared machine.
- `run` stop is cooperative: it takes effect before the next model turn or tool
  call, not mid-execution of a running shell command.
- DuckDuckGo HTML parsing is best-effort; if their markup changes, search
  results degrade to a hint rather than crashing the loop.
- `render_chart` needs optional `pip install matplotlib` and the Web UI needs
  `flask`; every other built-in tool runs on the standard library plus
  `requests`.
- Anonymous API quotas apply to `search_github` (~10 searches/min) and
  occasionally to `search_wikipedia`; both return a clear retry-hint error
  instead of crashing the loop.
