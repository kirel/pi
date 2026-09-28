#!/usr/bin/env python3
"""Bounded direct-serving comparison; no credentials or real household prompts.

Run on the GPU host with --url pointing to an already running backend.
Writes JSONL measurements to stdout. Does not start/stop services or clear caches.
"""
import argparse
import concurrent.futures
import json
import random
import time
import urllib.request


def call(url, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url + path, data=data,
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=600)


def metric(url):
    with call(url, "/metrics") as response:
        lines = response.read().decode().splitlines()
    names = ("prefix_cache_hits_total", "prompt_tokens_total",
             "request_prefill_time_seconds_sum", "num_requests_running")
    values = {}
    for line in lines:
        if line.startswith("#"):
            continue
        key = line.split("{")[0].split()[0].removeprefix("vllm:")
        if key in names:
            values[key] = values.get(key, 0) + float(line.rsplit(" ", 1)[1])
    return values


def generate(url, model, tokens, output):
    start = time.monotonic()
    first = None
    usage = None
    payload = dict(model=model, prompt=tokens, max_tokens=output, temperature=0,
                   top_p=1, top_k=-1, presence_penalty=0, frequency_penalty=0,
                   repetition_penalty=1,
                   ignore_eos=True, stream=True, stream_options={"include_usage": True})
    with call(url, "/v1/completions", payload) as response:
        for line in response:
            if not line.startswith(b"data: ") or line.strip() == b"data: [DONE]":
                continue
            event = json.loads(line[6:])
            if "error" in event:
                raise RuntimeError(event["error"])
            if first is None and any(c.get("text") for c in event.get("choices", [])):
                first = time.monotonic()
            if event.get("usage"):
                usage = event["usage"]
    end = time.monotonic()
    if first is None or not usage or usage["completion_tokens"] != output:
        raise RuntimeError(f"Incomplete measurement: {usage}")
    return dict(prompt_tokens=usage["prompt_tokens"], output_tokens=output,
                ttft_s=first-start, elapsed_s=end-start,
                input_tokens_per_ttft_s=usage["prompt_tokens"]/(first-start),
                decode_tokens_s=(output-1)/(end-first))


def prompt(url, model, length, seed):
    rng = random.Random(seed)
    text = f"Unique benchmark {rng.getrandbits(128):032x}\n"
    text += "\n".join(f"item_{i}: value={rng.randrange(1000000)}; category={rng.choice(['alpha','beta','gamma'])}"
                      for i in range(length // 8 + 100))
    with call(url, "/tokenize", {"model": model, "prompt": text}) as response:
        tokens = json.load(response)["tokens"]
    assert len(tokens) >= length, (len(tokens), length)
    return tokens[:length]


def emit(value):
    print(json.dumps(value), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--long", action="store_true")
    args = parser.parse_args()
    generate(args.url, args.model, prompt(args.url, args.model, 512, 1), 16)
    cases = [(f"prefill-{length}-{rep}", length, 32, 1, 1000+length+rep)
             for length in (8192, 32768, 65536) for rep in range(3)]
    cases += [("decode-c1", 2048, 256, 1, 80001),
              ("decode-c3", 2048, 256, 3, 80002)]
    if args.long:
        cases += [("prefill-near-full", 260000, 32, 1, 99999)]
    for name, length, output, concurrency, seed in cases:
        prompts = [prompt(args.url, args.model, length, seed+i*1234567)
                   for i in range(concurrency)]
        before = metric(args.url)
        if before.get("num_requests_running", 0):
            raise RuntimeError("Backend busy before measurement")
        start = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            results = list(pool.map(lambda p: generate(args.url, args.model, p, output), prompts))
        elapsed = time.monotonic()-start
        after = metric(args.url)
        emit(dict(label=args.label, case=name, results=results,
                  aggregate_output_tokens_per_wall_s=concurrency*output/elapsed,
                  metrics_delta={k: after[k]-before.get(k, 0) for k in after}))
        if name == "prefill-32768-0":
            before = metric(args.url)
            result = generate(args.url, args.model, prompts[0], output)
            after = metric(args.url)
            emit(dict(label=args.label, case="warm-prefix-32768", results=[result],
                      metrics_delta={k: after[k]-before.get(k, 0) for k in after}))


if __name__ == "__main__":
    main()
