#!/usr/bin/env python3
"""Read-only n8n snapshot vs official Todoist MCP benchmark. Tokens stay in memory.

LITELLM_API_KEY from environment; n8n bearer token from stdin.
No task contents are written to stdout. Run on the Hermes host for its route.
"""
import concurrent.futures
import json
import os
import statistics
import sys
import time
import urllib.request

PROJECT = "6Jhc7FCRmrMQPgW7"


class MCP:
    def __init__(self, url, token):
        self.url = url
        self.headers = {
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

    def rpc(self, method, params):
        request = urllib.request.Request(self.url, headers=self.headers, data=json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode())
        with urllib.request.urlopen(request, timeout=90) as response:
            session = response.headers.get("Mcp-Session-Id")
            if session:
                self.headers["Mcp-Session-Id"] = session
            raw = response.read().decode()
        # SSE may begin with a keepalive comment rather than event:/data:.
        events = [json.loads(line[5:]) for line in raw.splitlines() if line.startswith("data:")]
        data = next((event for event in events if event.get("id") == 1), None)
        if data is None:
            data = json.loads(raw)
        assert "error" not in data, "MCP protocol error"
        return data["result"]

    def call(self, name, arguments):
        result = self.rpc("tools/call", {"name": name, "arguments": arguments})
        assert not result.get("isError"), "MCP tool failed"
        data = result.get("structuredContent")
        if data is None:
            data = json.loads(result["content"][0]["text"])
        return data, len(json.dumps(result).encode())


def normalized(snapshot):
    # Compare shopping-relevant values, not just counts. Do not print private data.
    return {
        "tasks": sorted(tuple(t.get(k) or "" for k in
                              ("id", "content", "description", "projectId", "sectionId"))
                        for t in snapshot["tasks"]),
        "sections": sorted((s["id"], s["name"]) for s in snapshot["sections"]),
    }


def main():
    official = MCP("https://litellm.kirelabs.org/mcp/", os.environ["LITELLM_API_KEY"])
    n8n = MCP("https://n8n.kirelabs.org/mcp/shopping-experiment", sys.stdin.read().strip())
    for client in (official, n8n):
        client.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                  "clientInfo": {"name": "shopping-benchmark", "version": "1"}})

    def tasks():
        output, size, calls, seen = [], 0, 0, set()
        args = {"projectId": PROJECT, "responsibleUserFiltering": "all", "limit": 100}
        while True:
            page, length = official.call("todoist-find-tasks", args)
            size += length
            calls += 1
            output.extend(page["tasks"])
            if not page["hasMore"]:
                return output, size, calls
            cursor = page.get("nextCursor")
            assert cursor and cursor not in seen, "Missing/repeated pagination cursor"
            seen.add(cursor)
            args["cursor"] = cursor

    def sections():
        page, size = official.call("todoist-find-sections", {"projectId": PROJECT})
        return page["sections"], size, 1

    def baseline(parallel=False):
        if parallel:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                a, b = pool.submit(tasks), pool.submit(sections)
                a, b = a.result(), b.result()
        else:
            a, b = tasks(), sections()
        return {"tasks": a[0], "sections": b[0]}, a[1] + b[1], a[2] + b[2]

    def snapshot():
        data, size = n8n.call("shopping_snapshot", {})
        if isinstance(data, list):
            assert len(data) == 1
            data = data[0]
        assert data["complete"] is True, "Incomplete n8n pagination"
        assert data["projectId"] == PROJECT
        return data, size, 1

    methods = {"n8n_direct": snapshot, "official_sequential_via_litellm": baseline,
               "official_parallel_via_litellm": lambda: baseline(True)}
    rows, reference = [], None
    # First cycle recorded as warm-up; rotate order thereafter to reduce order bias.
    for cycle in range(8):
        names = list(methods)
        names = names[cycle % 3:] + names[:cycle % 3]
        for name in names:
            start = time.perf_counter()
            data, size, calls = methods[name]()
            elapsed = time.perf_counter() - start
            values = normalized(data)
            if reference is None:
                reference = values
            assert values == reference, "Results differ or shopping list changed during benchmark"
            row = {"cycle": cycle, "method": name, "seconds": elapsed,
                   "response_json_bytes": size, "calls": calls,
                   "tasks": len(data["tasks"]), "sections": len(data["sections"])}
            rows.append(row)
            print(json.dumps(row), flush=True)
    summary = {name: {"median_seconds": statistics.median(
        r["seconds"] for r in rows if r["method"] == name and r["cycle"] > 0),
        "measured_runs": 7} for name in methods}
    print(json.dumps({"summary": summary, "all_results_equivalent": True}), flush=True)


if __name__ == "__main__":
    main()
