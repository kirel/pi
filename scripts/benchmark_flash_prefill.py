#!/usr/bin/env python3
"""Sequential cold-chat prefill/decode comparison using one shared synthetic corpus.

The first arm prepares exact raw-text token counts using its /tokenize endpoint.
Every arm reports actual chat-template token counts and streaming TTFT separately
from the engine's prompt timings. Does not start or stop backends.
"""
import argparse
import json
from pathlib import Path
import time
import urllib.request

import benchmark_qwen_serving as existing


def request(url, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    return urllib.request.urlopen(urllib.request.Request(
        url + path, data=data, headers={"Content-Type": "application/json"}), timeout=1200)


def generate(url, model, case, decode_tokens=0, reasoning_effort="none", allow_cache=False):
    instruction = ("\nIgnore the records. Write a detailed German article of at least 2000 words "
                   "explaining how to plan, perform and verify database backups. Use continuous "
                   "prose with concrete examples. Start directly with the article and continue "
                   "until the topic is fully explained.") if decode_tokens else \
        "\nIgnore the records. What is 19 + 23? Answer only 42."
    payload = dict(model=model, messages=[
        {"role": "system", "content": f"Independent benchmark {case['seed']:032x}. Follow the final instruction."},
        {"role": "user", "content": case["text"] + instruction},
    ], max_tokens=decode_tokens or (2048 if reasoning_effort != "none" else 32), temperature=0, top_p=1, top_k=0, min_p=0,
        presence_penalty=0, frequency_penalty=0, repetition_penalty=1,
        reasoning_effort=reasoning_effort, chat_template_kwargs={"enable_thinking": reasoning_effort != "none"},
        cache_prompt=False, stream=True, stream_options={"include_usage": True})
    start, first, usage, timings = time.monotonic(), None, None, None
    content, reasoning, finish_reason, first_visible = "", "", None, None
    with request(url, "/v1/chat/completions", payload) as response:
        for line in response:
            if not line.startswith(b"data: ") or line.strip() == b"data: [DONE]":
                continue
            event = json.loads(line[6:])
            if "error" in event:
                raise RuntimeError(event["error"])
            for choice in event.get("choices", []):
                finish_reason = choice.get("finish_reason") or finish_reason
                delta = choice.get("delta", {})
                text = delta.get("content") or ""
                thought = delta.get("reasoning_content") or ""
                if (first is None and (text or thought)) or (first_visible is None and text):
                    now = time.monotonic()
                    if first is None:
                        first = now
                    if first_visible is None and text:
                        first_visible = now
                content += text
                reasoning += thought
            usage = event.get("usage") or usage
            timings = event.get("timings") or timings
    end = time.monotonic()
    if first is None or not usage or usage.get("completion_tokens", 0) <= 0:
        raise RuntimeError(f"Incomplete or incorrect answer: {usage}, {content!r}")
    if decode_tokens:
        if usage["completion_tokens"] != decode_tokens or len(content.split()) < 100 or finish_reason != "length":
            raise RuntimeError(f"Incomplete decode workload: {usage}, finish={finish_reason}, {content[:120]!r}")
    elif content.strip() != "42":
        raise RuntimeError(f"Incorrect answer: {content!r}")
    cached = usage.get("prompt_tokens_details", {}).get("cached_tokens")
    if cached is None and timings:
        cached = timings.get("cache_n")
    if not allow_cache and cached is not None and cached > 32:
        raise RuntimeError(f"Cold prompt reused {cached} tokens")
    return dict(raw_text_tokens=case["length"], prompt_tokens=usage["prompt_tokens"],
                output_tokens=usage["completion_tokens"], cached_tokens=cached,
                ttft_s=first-start, elapsed_s=end-start,
                decode_s=end-first,
                output_tokens_per_decode_s=(usage["completion_tokens"]-1)/(end-first),
                finish_reason=finish_reason,
                input_tokens_per_ttft_s=usage["prompt_tokens"]/(first-start),
                first_visible_s=None if first_visible is None else first_visible-start,
                reasoning_effort=reasoning_effort, reasoning=reasoning,
                reasoning_tokens=usage.get("completion_tokens_details", {}).get("reasoning_tokens"),
                usage=usage, timings=timings, answer=content, started_at=time.time()-(end-start))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--corpus", type=Path, required=True)
    p.add_argument("--lengths", default="4096,16384,32768,65536,128000")
    p.add_argument("--repetitions", type=int, default=3)
    p.add_argument("--prepare-only", action="store_true")
    p.add_argument("--decode-tokens", type=int, default=0,
                   help="Measure sustained prose generation; require this many output tokens")
    p.add_argument("--reasoning-effort", choices=["none", "low"], default="none")
    a = p.parse_args()
    if not a.corpus.exists():
        cases = []
        for length in map(int, a.lengths.split(",")):
            # ponytail: one near-full sample; repeat it separately to estimate variance.
            for rep in range(1 if length >= 128000 else a.repetitions):
                seed = 1000 + length + rep
                tokens = existing.prompt(a.url, a.model, length, seed, tokenizer_field="content")
                with request(a.url, "/detokenize", {"tokens": tokens}) as r:
                    text = json.load(r)["content"]
                cases.append(dict(length=length, rep=rep, seed=seed, text=text))
        a.corpus.write_text(json.dumps(cases))
    cases = [c for c in json.loads(a.corpus.read_text()) if c["length"] in set(map(int, a.lengths.split(",")))]
    if a.prepare_only:
        print(f"Prepared {len(cases)} shared prompts", flush=True)
        return
    warmup = dict(length=0, seed=987654321, text="Warmup.")
    generate(a.url, a.model, warmup, a.decode_tokens, a.reasoning_effort)
    for case in [c for c in cases if c["length"] == 65536][:(1 if a.decode_tokens else 2)]:
        generate(a.url, a.model, {**case, "seed": case["seed"] + 1000000}, a.decode_tokens, a.reasoning_effort)
    for case in cases:
        try:
            result = generate(a.url, a.model, case, a.decode_tokens, a.reasoning_effort)
        except Exception as exc:
            print(json.dumps(dict(label=a.label, length=case["length"], rep=case["rep"],
                                  error=str(exc))), flush=True)
            raise
        print(json.dumps(dict(label=a.label, length=case["length"], rep=case["rep"],
                              seed=case["seed"], result=result)), flush=True)


if __name__ == "__main__":
    main()
