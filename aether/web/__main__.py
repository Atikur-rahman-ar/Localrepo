"""Entry point: python -m aether.web

Starts the local dashboard. The base provider/model/workspace come from
config.yaml / environment / CLI flags exactly like `python -m aether`;
each run can override provider, base_url, model and max_iterations from
the UI. API keys are never entered in the browser - set AETHER_API_KEY
in the environment instead.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aether.web", description="Aether live Web UI (local dashboard)"
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--config", help="path to config.yaml")
    parser.add_argument("--provider", choices=["openai_compatible", "ollama", "mock"])
    parser.add_argument("--base-url", help="API root for openai_compatible")
    parser.add_argument("--model")
    parser.add_argument("--workspace", help="directory the agent operates in")
    parser.add_argument("--max-iterations", type=int)
    parser.add_argument("--max-delegate-depth", type=int,
                        help="sub-agent nesting via delegate_task (0 disables)")
    parser.add_argument("--delegate-max-iterations", type=int)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    try:
        from .server import create_app
    except ImportError:
        print(
            "The Web UI needs Flask. Install it with:\n"
            "  pip install flask\n"
            "or, if you installed Aether from PyPI:\n"
            "  pip install 'aether-agent-framework[web]'",
            file=sys.stderr,
        )
        return 1

    app = create_app(
        args.config,
        provider=args.provider,
        base_url=args.base_url,
        model=args.model,
        workspace=args.workspace,
        max_iterations=args.max_iterations,
        max_delegate_depth=args.max_delegate_depth,
        delegate_max_iterations=args.delegate_max_iterations,
    )
    print(f"Aether Web UI on http://{args.host}:{args.port}  (Ctrl-C to quit)")
    app.run(host=args.host, port=args.port, threaded=True, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
