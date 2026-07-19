#!/usr/bin/env python3
"""Patch Hermes Telegram polling instrumentation for slotted HTTPXRequest.

python-telegram-bot's HTTPXRequest uses ``__slots__``, so assigning a wrapped
``do_request`` method to one instance raises ``AttributeError: ... is
read-only``.  Use a layout-compatible per-instance subclass instead.

This runs at Docker image build time and fails loudly if the upstream source
no longer has the expected pre-fix shape.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys


ROOT = Path(os.environ.get("HERMES_ROOT", "/opt/hermes"))
ADAPTER = ROOT / "plugins" / "platforms" / "telegram" / "adapter.py"

OLD_METHOD = '''    def _instrument_polling_request(self, request):
        """Wrap one dedicated PTB getUpdates request with progress tracking."""
        do_request = request.do_request

        async def _do_request(*args, **kwargs):
            generation = _POLLING_GENERATION_CONTEXT.get()
            result = await do_request(*args, **kwargs)
            status_code, payload = result
            if generation is not None and 200 <= status_code < 300:
                try:
                    # Use the request's own parser so health observation agrees
                    # exactly with PTB's authoritative response handling (e.g.
                    # UTF-8 replacement decoding and BOM rejection).
                    envelope = request.parse_json_payload(payload)
                except Exception:
                    # Instrumentation is observational: PTB still parses the
                    # untouched payload and owns the resulting exception.
                    pass
                else:
                    if (
                        isinstance(envelope, dict)
                        and envelope.get("ok") is True
                        and "result" in envelope
                    ):
                        self._record_polling_progress(generation)
            return result

        request.do_request = _do_request
        return request
'''

NEW_METHOD = '''    def _instrument_polling_request(self, request):
        """Wrap one dedicated PTB getUpdates request with progress tracking."""
        # HTTPXRequest uses __slots__, so assigning request.do_request on one
        # instance raises AttributeError. A subclass with no additional slots
        # has the same object layout and can be installed on just this polling
        # request without affecting the general Telegram request instance.
        adapter = self
        base_request_class = type(request)

        class _InstrumentedPollingRequest(base_request_class):
            __slots__ = ()

            async def do_request(instrumented_request, *args, **kwargs):
                generation = _POLLING_GENERATION_CONTEXT.get()
                result = await super().do_request(*args, **kwargs)
                status_code, payload = result
                if generation is not None and 200 <= status_code < 300:
                    try:
                        # Use the request's own parser so health observation
                        # agrees exactly with PTB's authoritative response
                        # handling (e.g. replacement decoding and BOM checks).
                        envelope = instrumented_request.parse_json_payload(payload)
                    except Exception:
                        # Instrumentation is observational: PTB still parses
                        # the untouched payload and owns any resulting error.
                        pass
                    else:
                        if (
                            isinstance(envelope, dict)
                            and envelope.get("ok") is True
                            and "result" in envelope
                        ):
                            adapter._record_polling_progress(generation)
                return result

        request.__class__ = _InstrumentedPollingRequest
        return request
'''

FIX_MARKERS = (
    "class _InstrumentedPollingRequest(",
    "request.__class__ = _InstrumentedPollingRequest",
)


def main() -> int:
    if not ADAPTER.is_file():
        raise RuntimeError(f"Telegram adapter not found: {ADAPTER}")

    text = ADAPTER.read_text(encoding="utf-8")
    if all(marker in text for marker in FIX_MARKERS):
        print(f"{ADAPTER} already contains the HTTPXRequest slots fix")
        return 0
    if OLD_METHOD not in text:
        raise RuntimeError(
            f"{ADAPTER}: expected vulnerable polling instrumentation not found; "
            "upstream may have changed, verify the Telegram fix manually"
        )

    ADAPTER.write_text(text.replace(OLD_METHOD, NEW_METHOD, 1), encoding="utf-8")
    print(f"Patched {ADAPTER}: use a slotted per-instance polling request subclass")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - build-time diagnostic
        print(f"ERROR: failed to patch Hermes Telegram adapter: {exc}", file=sys.stderr)
        raise SystemExit(1)
