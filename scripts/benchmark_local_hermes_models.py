#!/usr/bin/env python3
"""Benchmark routed models through the real Local Hermes API-server agent.

Run this inside the ``hermes-local`` container so ``API_SERVER_KEY`` can be
used without copying it out of the container. Results contain timings, token
counts, tool names, and short output previews, but never credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MODEL_ROUTES = {
    "muse-low": {
        "route": "hermes-bench-muse-low",
        "phoenix_model": "Muse-Glimmer-30B-low",
    },
    "qwen-nothink": {
        "route": "hermes-bench-qwen-nothink",
        "phoenix_model": "Qwen3.8-27B-Instruct-nothink",
    },
}

READ_ONLY_INSTRUCTIONS = """\
Dies ist ein kontrollierter, nebenwirkungsfreier Benchmark. Arbeite strikt
lesend. Du darfst Informationen abfragen und recherchieren, aber keine Geräte
steuern, keine Listen, Dateien, Erinnerungen oder Einstellungen verändern und
nichts veröffentlichen. Falls eine Aufgabe eine Änderung erfordern würde,
erkläre knapp, dass du sie im Benchmark nicht ausführst. Antworte auf Deutsch,
präzise und ohne den Benchmark-Hintergrund zu kommentieren.
"""


@dataclass(frozen=True)
class Workload:
    name: str
    category: str
    prompt: str
    expected_tool_fragments: tuple[str, ...] = ()


WORKLOADS = (
    Workload(
        name="ha_openings",
        category="home_assistant_read",
        prompt=(
            "Prüfe über Home Assistant, ob derzeit Fenster oder Außentüren als "
            "offen gemeldet sind. Nenne nur die offenen mit ihrem Anzeigenamen; "
            "wenn keine offen sind, sage das in einem Satz."
        ),
        expected_tool_fragments=("home", "ha_", "mcp"),
    ),
    Workload(
        name="ha_climate",
        category="home_assistant_read",
        prompt=(
            "Lies über Home Assistant die derzeit verfügbaren Temperaturwerte "
            "für Wohnräume aus. Gib eine knappe Liste aus Anzeigename und Wert "
            "aus und erfinde keine fehlenden Messwerte."
        ),
        expected_tool_fragments=("home", "ha_", "mcp"),
    ),
    Workload(
        name="shopping_read",
        category="shopping_read",
        prompt=(
            "Lies die aktuelle Einkaufsliste ausschließlich lesend aus. Nenne "
            "höchstens die ersten fünf offenen Einträge; wenn sie leer ist, sage "
            "das knapp. Füge nichts hinzu und hake nichts ab."
        ),
        expected_tool_fragments=("todoist", "mcp", "task"),
    ),
    Workload(
        name="web_current",
        category="web_research",
        prompt=(
            "Recherchiere im Web die aktuell stabile Home-Assistant-Core-Version "
            "und nenne Versionsnummer sowie Veröffentlichungsdatum mit einer "
            "knappen Quellenangabe."
        ),
        expected_tool_fragments=("web_search", "web_extract", "browser"),
    ),
    Workload(
        name="concise_planning",
        category="reasoning_no_tool",
        prompt=(
            "Ein Haushalt möchte den Stromverbrauch senken, ohne Komfort zu "
            "verlieren. Formuliere genau drei priorisierte, praktisch umsetzbare "
            "Vorschläge mit jeweils höchstens einem Satz."
        ),
    ),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


class HermesClient:
    def __init__(self, endpoint: str, api_key: str, timeout: int) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def request_json(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        headers = dict(self.headers)
        if extra_headers:
            headers.update(extra_headers)
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"{self.endpoint}{path}", data=data, headers=headers, method=method
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.load(response)

    def run(
        self,
        route: str,
        workload: Workload,
        session_id: str,
    ) -> dict[str, Any]:
        started_wall = utc_now()
        started = time.monotonic()
        submitted = self.request_json(
            "POST",
            "/v1/runs",
            {
                "model": route,
                "input": workload.prompt,
                "instructions": READ_ONLY_INSTRUCTIONS,
                "session_id": session_id,
            },
            {"X-Hermes-Session-Key": session_id},
        )
        run_id = submitted["run_id"]
        request = urllib.request.Request(
            f"{self.endpoint}/v1/runs/{run_id}/events",
            headers=self.headers,
            method="GET",
        )

        events: list[dict[str, Any]] = []
        first_delta_seconds: float | None = None
        terminal: dict[str, Any] | None = None
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                events.append(event)
                if event.get("event") == "message.delta" and first_delta_seconds is None:
                    first_delta_seconds = time.monotonic() - started
                if event.get("event") in {
                    "run.completed",
                    "run.failed",
                    "run.cancelled",
                }:
                    terminal = event

        elapsed_seconds = time.monotonic() - started
        if terminal is None:
            terminal = self.request_json("GET", f"/v1/runs/{run_id}")

        tool_events = [event for event in events if event.get("event") == "tool.completed"]
        tool_names = [str(event.get("tool", "")) for event in tool_events]
        tool_names_lower = [name.lower() for name in tool_names]
        expected_tool_met = not workload.expected_tool_fragments or any(
            fragment in tool_name
            for fragment in workload.expected_tool_fragments
            for tool_name in tool_names_lower
        )
        output = str(terminal.get("output", ""))
        status = str(terminal.get("event", terminal.get("status", "unknown"))).removeprefix(
            "run."
        )
        usage = terminal.get("usage") or {}

        return {
            "run_id": run_id,
            "session_id": session_id,
            "started_at": started_wall,
            "ended_at": utc_now(),
            "status": status,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "first_delta_seconds": (
                round(first_delta_seconds, 3) if first_delta_seconds is not None else None
            ),
            "input_tokens": int(usage.get("input_tokens", 0) or 0),
            "output_tokens": int(usage.get("output_tokens", 0) or 0),
            "total_tokens": int(usage.get("total_tokens", 0) or 0),
            "tool_calls": len(tool_events),
            "tool_errors": sum(bool(event.get("error")) for event in tool_events),
            "tool_seconds": round(
                sum(float(event.get("duration", 0) or 0) for event in tool_events), 3
            ),
            "tool_names": tool_names,
            "expected_tool_met": expected_tool_met,
            "output_chars": len(output),
            "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
            "output_preview": output[:400].replace("\n", " "),
            "passed": (
                status == "completed"
                and bool(output.strip())
                and not any(bool(event.get("error")) for event in tool_events)
                and expected_tool_met
            ),
        }


def summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for model_key in MODEL_ROUTES:
        selected = [run for run in runs if run["model_key"] == model_key and not run["warmup"]]
        elapsed = [float(run["elapsed_seconds"]) for run in selected]
        ttft = [
            float(run["first_delta_seconds"])
            for run in selected
            if run["first_delta_seconds"] is not None
        ]
        summary[model_key] = {
            "runs": len(selected),
            "passed": sum(bool(run["passed"]) for run in selected),
            "pass_rate": round(
                sum(bool(run["passed"]) for run in selected) / len(selected), 3
            )
            if selected
            else None,
            "latency_seconds_median": round(statistics.median(elapsed), 3) if elapsed else None,
            "latency_seconds_p95": round(percentile(elapsed, 0.95), 3) if elapsed else None,
            "first_delta_seconds_median": round(statistics.median(ttft), 3) if ttft else None,
            "input_tokens_total": sum(int(run["input_tokens"]) for run in selected),
            "output_tokens_total": sum(int(run["output_tokens"]) for run in selected),
            "tool_calls": sum(int(run["tool_calls"]) for run in selected),
            "tool_errors": sum(int(run["tool_errors"]) for run in selected),
        }
    return summary


def write_checkpoint(output_path: Path, result: dict[str, Any]) -> None:
    """Atomically retain every completed run, including interrupted campaigns."""
    result["updated_at"] = utc_now()
    result["summary"] = summarize(result["runs"])
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    temporary_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    temporary_path.replace(output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint", default=os.getenv("HERMES_API_ENDPOINT", "http://127.0.0.1:8642")
    )
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument(
        "--models",
        nargs="+",
        choices=tuple(MODEL_ROUTES),
        default=list(MODEL_ROUTES),
    )
    parser.add_argument(
        "--workloads",
        nargs="+",
        choices=tuple(workload.name for workload in WORKLOADS),
    )
    parser.add_argument("--skip-warmup", action="store_true")
    parser.add_argument(
        "--acknowledge-isolation",
        action="store_true",
        help=(
            "confirm that self-improvement nudges are disabled and the API-server "
            "tool surface has been restricted for this benchmark"
        ),
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.repetitions < 1:
        raise SystemExit("--repetitions must be at least 1")
    if not args.acknowledge_isolation:
        raise SystemExit(
            "Refusing to run without --acknowledge-isolation; apply the temporary "
            "Hermes benchmark controls documented in "
            "docs/local-hermes-model-benchmark-2026-08-15.md first"
        )
    api_key = os.getenv("HERMES_API_KEY") or os.getenv("API_SERVER_KEY")
    if not api_key:
        raise SystemExit("Set HERMES_API_KEY or run inside the hermes-local container")

    selected_workloads = [
        workload
        for workload in WORKLOADS
        if args.workloads is None or workload.name in args.workloads
    ]
    run_group = f"local-hermes-ab-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    output_path = args.output or Path(f"/tmp/{run_group}.json")
    client = HermesClient(args.endpoint, api_key, args.timeout)
    result: dict[str, Any] = {
        "schema_version": 1,
        "run_group": run_group,
        "started_at": utc_now(),
        "endpoint": args.endpoint,
        "phoenix": {
            "base_url": "https://phoenix.kirelabs.org",
            "project": "default",
            "team_filter": "metadata.user_api_key_team_id:hermes-ailab",
        },
        "models": {key: MODEL_ROUTES[key] for key in args.models},
        "repetitions": args.repetitions,
        "workloads": [workload.name for workload in selected_workloads],
        "controls": {
            "read_only_instructions": True,
            "operator_acknowledged_runtime_isolation": True,
        },
        "completed": False,
        "runs": [],
    }
    write_checkpoint(output_path, result)

    for model_key in args.models:
        route = MODEL_ROUTES[model_key]["route"]
        if not args.skip_warmup:
            warmup = Workload(
                name="warmup",
                category="warmup",
                prompt="Antworte ausschließlich mit: BEREIT",
            )
            print(f"[{model_key}] warmup", flush=True)
            run = client.run(route, warmup, f"{run_group}-{model_key}-warmup")
            run.update({"model_key": model_key, "route": route, "workload": "warmup", "warmup": True})
            result["runs"].append(run)
            write_checkpoint(output_path, result)

        for repetition in range(1, args.repetitions + 1):
            for workload in selected_workloads:
                print(
                    f"[{model_key}] {workload.name} repetition={repetition}", flush=True
                )
                session_id = (
                    f"{run_group}-{model_key}-{workload.name}-{repetition}"
                )
                try:
                    run = client.run(route, workload, session_id)
                except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                    run = {
                        "session_id": session_id,
                        "started_at": utc_now(),
                        "ended_at": utc_now(),
                        "status": "client_error",
                        "error": str(exc),
                        "elapsed_seconds": 0,
                        "first_delta_seconds": None,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "total_tokens": 0,
                        "tool_calls": 0,
                        "tool_errors": 0,
                        "tool_seconds": 0,
                        "tool_names": [],
                        "expected_tool_met": False,
                        "output_chars": 0,
                        "output_sha256": "",
                        "output_preview": "",
                        "passed": False,
                    }
                run.update(
                    {
                        "model_key": model_key,
                        "route": route,
                        "workload": workload.name,
                        "category": workload.category,
                        "repetition": repetition,
                        "warmup": False,
                    }
                )
                result["runs"].append(run)
                write_checkpoint(output_path, result)
                print(
                    f"  status={run['status']} passed={run['passed']} "
                    f"elapsed={run['elapsed_seconds']}s tools={run['tool_names']}",
                    flush=True,
                )

    result["ended_at"] = utc_now()
    result["completed"] = True
    write_checkpoint(output_path, result)
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False))
    print(f"result={output_path}")
    return 0 if all(item["pass_rate"] == 1 for item in result["summary"].values()) else 2


if __name__ == "__main__":
    sys.exit(main())
