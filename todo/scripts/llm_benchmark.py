import time
import os
import openai

# Configuration
API_BASE = os.getenv("LITELLM_API_BASE", "http://homelab-nuc.lan:4000/v1")
API_KEY = os.getenv("LITELLM_MASTER_KEY")

if not API_KEY:
    print("Error: LITELLM_MASTER_KEY environment variable is not set.")
    exit(1)

MODELS = ["GPT-OSS-20B-vLLM", "GPT-OSS-20B-F16"]

client = openai.OpenAI(api_key=API_KEY, base_url=API_BASE)

def generate_prompt(target_tokens, seed_word="test"):
    target_chars = target_tokens * 4
    seed_text = f"The quick brown {seed_word} jumps over the lazy dog. " * 10
    repeats = (target_chars // len(seed_text)) + 1
    return seed_text * repeats

def benchmark_model(model_name, prompt, warmup=False):
    if not warmup:
        print(f"\n--- Benchmarking {model_name} ---")
    
    start_time = time.time()
    ttft = None
    first_token_time = None
    total_tokens = 0
    full_content = ""
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            max_tokens=100
        )
        
        for chunk in response:
            delta = chunk.choices[0].delta
            content = getattr(delta, 'content', None) or getattr(delta, 'reasoning_content', None)
            
            if content:
                if "loading" in content.lower() and len(content) < 50:
                     continue

                if ttft is None:
                    first_token_time = time.time()
                    ttft = first_token_time - start_time
                    if not warmup:
                        # print(f"[{model_name}] TTFT: {ttft*1000:.2f} ms")
                        pass
                
                full_content += content
                total_tokens += 1

        end_time = time.time()
        total_time = end_time - start_time
        generation_time = end_time - first_token_time if first_token_time else 0
        
        prompt_tokens = len(prompt) / 4
        prefill_tps = prompt_tokens / ttft if (ttft and ttft > 0) else 0
        decode_tps = total_tokens / generation_time if (generation_time and generation_time > 0) else 0
        
        if not warmup:
            print(f"[{model_name}] Prefill: {prefill_tps:.2f} t/s | Decode: {decode_tps:.2f} t/s | TTFT: {ttft*1000:.2f} ms")
        
        return {
            "model": model_name,
            "ttft_ms": ttft * 1000 if ttft else 0,
            "prefill_tps": prefill_tps,
            "decode_tps": decode_tps,
            "total_s": total_time
        }
    except Exception as e:
        if not warmup:
            print(f"[{model_name}] Error: {e}")
        return None

if __name__ == "__main__":
    TARGET_PROMPT_TOKENS = 8000
    NUM_REQUESTS = 5
    
    print(f"Comparing models at {API_BASE} with {NUM_REQUESTS} iterations (approx {TARGET_PROMPT_TOKENS} tokens)..\n")
    
    final_results = {}

    for model in MODELS:
        print(f"=== Testing {model} ===")
        model_results = []
        
        print(f"Warming up {model}...")
        warmup_prompt = generate_prompt(TARGET_PROMPT_TOKENS, "warmup")
        benchmark_model(model, warmup_prompt, warmup=True)
        
        for i in range(NUM_REQUESTS):
            prompt = generate_prompt(TARGET_PROMPT_TOKENS, f"iter_{i}")
            print(f"Iteration {i+1}/{NUM_REQUESTS}...")
            res = benchmark_model(model, prompt)
            if res:
                model_results.append(res)
        
        if model_results:
            avg_ttft = sum(r['ttft_ms'] for r in model_results) / len(model_results)
            avg_prefill = sum(r['prefill_tps'] for r in model_results) / len(model_results)
            avg_decode = sum(r['decode_tps'] for r in model_results) / len(model_results)
            avg_total = sum(r['total_s'] for r in model_results) / len(model_results)
            
            final_results[model] = {
                "avg_ttft": avg_ttft,
                "avg_prefill": avg_prefill,
                "avg_decode": avg_decode,
                "avg_total": avg_total
            }

    print("\n" + "="*85)
    print(f"{ 'Model':<20} | { 'Avg TTFT':<10} | { 'Prefill T/s':<12} | { 'Decode T/s':<12} | { 'Total (s)':<10}")
    print("-" * 85)
    for model in MODELS:
        if model in final_results:
            r = final_results[model]
            print(f"{model:<20} | {r['avg_ttft']:<10.2f} | {r['avg_prefill']:<12.2f} | {r['avg_decode']:<12.2f} | {r['avg_total']:<10.2f}")
    print("="*85)
