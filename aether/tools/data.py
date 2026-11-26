"""Data tools: local SQLite queries and chart rendering (matplotlib optional)."""

from __future__ import annotations

import sqlite3

from .base import Tool
from .files import _WorkspaceTool

MAX_ROWS = 50


class RunSqlite(_WorkspaceTool):
    name = "run_sqlite"
    description = (
        "Execute ONE SQL statement against a local SQLite database file. "
        "Read-only by default; pass mode='write' for INSERT/UPDATE/DELETE/DDL. "
        "SELECT results come back as a Markdown table (first 50 rows)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the .db/.sqlite file (inside the workspace)."},
            "sql": {"type": "string", "description": "A single SQL statement."},
            "params": {"type": "array", "description": "Optional positional SQL parameters."},
            "mode": {"type": "string", "description": "'read' (default) or 'write'."},
        },
        "required": ["path", "sql"],
    }

    def run(self, args: dict) -> str:
        path = self._resolve(str(args.get("path", "")))
        sql = str(args.get("sql", "")).strip()
        if not sql:
            return "ERROR: 'sql' is required."
        if not path.exists():
            return f"ERROR: {path} does not exist (run_sqlite never creates databases)."

        write = str(args.get("mode") or "read").lower() == "write"
        params = args.get("params")
        if params is not None and not isinstance(params, list):
            return "ERROR: 'params' must be an array of positional values."

        try:
            if write:
                conn = sqlite3.connect(str(path))
            else:
                conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            try:
                cur = conn.execute(sql, params or [])
                rows = cur.fetchmany(MAX_ROWS + 1)
            finally:
                conn.close()
        except sqlite3.Error as exc:
            hint = ""
            if not write and any(
                kw in sql[:12].upper() for kw in ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER")
            ):
                hint = " (pass mode='write' to modify the database)"
            return f"ERROR: {exc}{hint}"

        if cur.description is None:  # non-SELECT statement
            return f"OK. Rows affected: {cur.rowcount}."

        columns = [d[0] for d in cur.description]
        truncated = len(rows) > MAX_ROWS
        rows = rows[:MAX_ROWS]

        def cell(value) -> str:
            return str(value).replace("|", "\\|").replace("\n", " ")

        out = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
        out += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
        note = f"\n({cur.rowcount if cur.rowcount >= 0 else len(rows)} rows"
        note += f", showing first {len(rows)}{'; use LIMIT/OFFSET for more' if truncated else ''})"
        return "\n".join(out) + note


class RenderChart(_WorkspaceTool):
    name = "render_chart"
    description = (
        "Render a chart (line, bar, scatter, pie or histogram) from arrays of "
        "data and save it as a PNG inside the workspace. Multi-series works by "
        "passing 'y' as an array of arrays plus optional 'series_names'. "
        "Requires matplotlib (pip install matplotlib); a clear error is "
        "returned if it is missing."
    )
    parameters = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "description": "'line' (default), 'bar', 'scatter', 'pie' or 'hist'."},
            "title": {"type": "string"},
            "x": {
                "type": "array",
                "description": "X values, categories or pie labels. Optional for line/hist.",
            },
            "y": {
                "type": "array",
                "description": "Y values; pass an array of arrays for multi-series line/bar/hist.",
            },
            "x_label": {"type": "string"},
            "y_label": {"type": "string"},
            "series_names": {"type": "array", "description": "Legend labels for multi-series charts."},
            "path": {"type": "string", "description": "Output PNG path (default 'chart.png')."},
        },
        "required": ["y"],
    }

    def run(self, args: dict) -> str:
        try:
            import matplotlib
        except ImportError:
            return (
                "ERROR: matplotlib is not installed. Install it with "
                "'pip install matplotlib' and retry, or use execute_python."
            )
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        chart_type = str(args.get("type") or "line").lower()
        if chart_type not in ("line", "bar", "scatter", "pie", "hist"):
            return f"ERROR: unknown chart type '{chart_type}'."

        y = args.get("y")
        if not isinstance(y, list) or not y:
            return "ERROR: 'y' must be a non-empty array."
        x = args.get("x") or []
        if not isinstance(x, list):
            return "ERROR: 'x' must be an array."

        multi = isinstance(y[0], list)
        series = y if multi else [y]
        names = list(args.get("series_names") or []) or [
            f"series {i + 1}" for i in range(len(series))
        ]

        if chart_type in ("scatter", "pie") and multi:
            return f"ERROR: '{chart_type}' supports a single series (pass y as one flat array)."
        if chart_type == "scatter" and (not x or len(x) != len(series[0])):
            return "ERROR: scatter needs 'x' with the same length as 'y'."

        plt.rcParams["axes.unicode_minus"] = False
        fig, ax = plt.subplots(figsize=(8, 5), layout="constrained")

        if chart_type == "line":
            for ys, nm in zip(series, names):
                xs = x if x and len(x) == len(ys) else range(1, len(ys) + 1)
                ax.plot(xs, ys, marker="o", markersize=3, label=nm)
            if len(series) > 1:
                ax.legend()
            ax.grid(alpha=0.3)
        elif chart_type == "bar":
            n = len(series)
            width = 0.8 / n
            xs = list(range(len(series[0])))
            for i, (ys, nm) in enumerate(zip(series, names)):
                pos = [v + (i - (n - 1) / 2) * width for v in xs]
                ax.bar(pos, ys, width=width, label=nm)
            ax.set_xticks(xs)
            ax.set_xticklabels([str(v) for v in x] if len(x) == len(xs) else xs)
            if len(series) > 1:
                ax.legend()
            ax.grid(alpha=0.3, axis="y")
        elif chart_type == "scatter":
            ax.scatter(x, series[0], s=24)
            ax.grid(alpha=0.3)
        elif chart_type == "pie":
            ax.pie(
                series[0],
                labels=[str(v) for v in x] if x else None,
                autopct="%1.1f%%",
                startangle=90,
            )
        else:  # hist
            for ys, nm in zip(series, names):
                ax.hist(ys, bins=min(20, max(5, len(ys) // 2 or 5)), alpha=0.6, label=nm)
            if multi:
                ax.legend()
            ax.grid(alpha=0.3, axis="y")

        ax.set_title(str(args.get("title") or ""))
        if args.get("x_label") and chart_type != "pie":
            ax.set_xlabel(str(args["x_label"]))
        if args.get("y_label") and chart_type != "pie":
            ax.set_ylabel(str(args["y_label"]))

        out_raw = str(args.get("path") or "chart.png").strip() or "chart.png"
        out = self._resolve(out_raw)
        if out.suffix.lower() != ".png":
            out = out.with_suffix(".png")
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=150)
        plt.close(fig)

        label = f"{len(series)} series" if multi else f"{len(series[0])} points"
        return f"Saved {chart_type} chart ({label}) to {out} ({out.stat().st_size} bytes)."
