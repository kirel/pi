#!/usr/bin/env python3
"""Live check: uv run --with websockets scripts/test_asr_stream.py AUDIO.wav.

Set LITELLM_API_KEY; input must be 16 kHz mono PCM16 WAV with speech.
"""

import argparse
import asyncio
import base64
import json
import os
import time
import wave

import websockets


async def check(url, path):
    with wave.open(path, "rb") as audio:
        assert (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) == (
            16000, 1, 2
        ), "Expected 16 kHz mono PCM16 WAV"
        pcm = audio.readframes(audio.getnframes())
    key = os.environ.get("LITELLM_API_KEY")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    async with websockets.connect(
        url, additional_headers=headers, ping_interval=None, close_timeout=3
    ) as ws:
        started = time.monotonic()
        committed = False
        partials = []

        async def receive():
            async for message in ws:
                event = json.loads(message)
                kind = event.get("type", "")
                assert kind != "error", event
                if kind.endswith(".delta") and event.get("delta") and not committed:
                    partials.append(event["delta"])
                print(f"{time.monotonic() - started:.2f}s {message}", flush=True)
                if kind.endswith(".completed"):
                    assert event.get("transcript", "").strip(), "Empty transcript"
                    return
            raise AssertionError("Connection closed before completed event")

        receiver = asyncio.create_task(receive())
        # One second of audio per frame, paced like a live microphone.
        for offset in range(0, len(pcm), 32000):
            await ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(pcm[offset:offset + 32000]).decode(),
            }))
            await asyncio.sleep(1)
        committed = True
        await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
        await asyncio.wait_for(receiver, timeout=30)
        assert partials, "No text arrived before commit"
        print(f"PASS: {len(partials)} partial events before commit")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio")
    parser.add_argument("--url", default="wss://litellm.kirelabs.org/v1/realtime?model=home-asr-stream")
    args = parser.parse_args()
    asyncio.run(check(args.url, args.audio))
