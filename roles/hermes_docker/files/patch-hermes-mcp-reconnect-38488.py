#!/usr/bin/env python3
"""Patch Hermes MCP reconnect loop for NousResearch/hermes-agent#38488.

This runs at Docker image build time. It intentionally fails loudly if the
installed Hermes source no longer matches the expected pre-fix shape, so we do
not silently build an image without the reconnect fix.
"""
from __future__ import annotations

from pathlib import Path
import importlib.util
import sys

ROOT = Path("/opt/hermes")

RESET_ANCHOR = """                # Reset the session reference; _run_http/_run_stdio will
                # repopulate it on successful re-entry.
                self.session = None
                # Keep _ready set across reconnects so tool handlers can
"""

RESET_REPLACEMENT = """                # Reset the session reference; _run_http/_run_stdio will
                # repopulate it on successful re-entry.
                self.session = None
                # Successful transport cycle — a future outage should get a
                # fresh fast-retry budget, not inherit counters from a prior
                # incident.  (#38488)
                retries = 0
                backoff = 1.0
                # Keep _ready set across reconnects so tool handlers can
"""

GIVE_UP_BLOCK = """                retries += 1
                if retries > _MAX_RECONNECT_RETRIES:
                    logger.warning(
                        "MCP server '%s' failed after %d reconnection attempts, "
                        "giving up: %s",
                        self.name, _MAX_RECONNECT_RETRIES, exc,
                    )
                    return

                logger.warning(
"""

SLOW_REPROBE_BLOCK = """                retries += 1
                if retries > _MAX_RECONNECT_RETRIES:
                    # Fast-retry budget exhausted.  Do NOT permanently give
                    # up — a backend that comes back later (e.g. after a
                    # power blip / reboot longer than the ~30s fast budget)
                    # should self-heal the same way LLM API calls do.
                    # Drop into a slow re-probe loop with a long fixed
                    # backoff until either the transport reconnects or the
                    # gateway shuts the server down.  (#38488)
                    slow_backoff = _MAX_BACKOFF_SECONDS
                    if retries == _MAX_RECONNECT_RETRIES + 1:
                        logger.warning(
                            "MCP server '%s' exhausted fast reconnect budget "
                            "after %d attempts; entering slow re-probe "
                            "(every %.0fs) until reachable: %s",
                            self.name, _MAX_RECONNECT_RETRIES,
                            slow_backoff, exc,
                        )
                    else:
                        logger.debug(
                            "MCP server '%s' slow re-probe attempt %d failed, "
                            "retrying in %.0fs: %s",
                            self.name, retries, slow_backoff, exc,
                        )
                    await asyncio.sleep(slow_backoff)
                    if self._shutdown_event.is_set():
                        return
                    continue

                logger.warning(
"""

SLOW_LOOP_MARKERS = (
    "entering slow re-probe",
    "slow background retry",
    "slow re-probe attempt",
    "exhausted fast reconnect budget",
)

RESET_MARKERS = (
    "fresh fast-retry budget",
    "not inherit counters from a prior",
)


def is_hermes_mcp_tool(path: Path) -> bool:
    if not path.exists() or path.parts[-2:] != ("tools", "mcp_tool.py"):
        return False
    text = path.read_text(encoding="utf-8")
    return "class MCPServerTask" in text and "_MAX_RECONNECT_RETRIES" in text


def find_mcp_tool() -> Path:
    # Prefer the exact module Python would import inside the image's venv. This
    # avoids ambiguity if both source and site-packages copies exist.
    try:
        spec = importlib.util.find_spec("tools.mcp_tool")
    except ModuleNotFoundError:
        spec = None
    if spec and spec.origin:
        imported_path = Path(spec.origin)
        if is_hermes_mcp_tool(imported_path):
            return imported_path

    candidates = []
    for path in ROOT.rglob("mcp_tool.py"):
        if is_hermes_mcp_tool(path):
            candidates.append(path)

    if not candidates:
        raise RuntimeError(f"Could not find Hermes tools/mcp_tool.py below {ROOT}")
    if len(candidates) > 1:
        joined = "\n  ".join(str(p) for p in candidates)
        raise RuntimeError(
            "Found multiple Hermes mcp_tool.py candidates and could not resolve "
            f"the import target:\n  {joined}"
        )
    return candidates[0]


def main() -> int:
    path = find_mcp_tool()
    text = path.read_text(encoding="utf-8")
    original = text
    changes: list[str] = []

    if not any(marker in text for marker in RESET_MARKERS):
        if RESET_ANCHOR not in text:
            if "retries = 0\n                backoff = 1.0" not in text:
                raise RuntimeError(
                    f"{path}: could not find successful-cycle reset insertion point"
                )
        else:
            text = text.replace(RESET_ANCHOR, RESET_REPLACEMENT, 1)
            changes.append("reset retry budget after successful transport cycle")

    if not any(marker in text for marker in SLOW_LOOP_MARKERS):
        if GIVE_UP_BLOCK not in text:
            raise RuntimeError(
                f"{path}: could not find old bounded reconnect give-up block; "
                "upstream may have changed, verify #38488 fix manually"
            )
        text = text.replace(GIVE_UP_BLOCK, SLOW_REPROBE_BLOCK, 1)
        changes.append("replace permanent give-up with slow re-probe loop")

    if text != original:
        path.write_text(text, encoding="utf-8")
        print(f"Patched {path}:")
        for change in changes:
            print(f" - {change}")
    else:
        print(f"{path} already contains Hermes MCP reconnect fix; no changes needed")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - build-time diagnostic
        print(f"ERROR: failed to patch Hermes MCP reconnect loop: {exc}", file=sys.stderr)
        raise SystemExit(1)
