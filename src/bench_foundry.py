"""Benchmark a Microsoft Foundry deployment with streaming. Auth via Entra ID (az login).

The OpenAI client is created with max_retries=0 so that silent SDK retries after HTTP 429
cannot inflate the measured latency. A throttled request is waited out (retry-after header)
outside the timed section and counted in the `throttled` column.

Examples:
  gpt-5-mini  : bench_foundry.py --deployment bench-model
  Llama 3.3   : bench_foundry.py --deployment bench-llama --api v1 --reasoning-effort omit --temperature 0
"""
import argparse
import os
import time

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from openai import AzureOpenAI, OpenAI, RateLimitError

from common import load_prompts, save_raw

load_dotenv()


def build_client(args):
    scope = os.getenv("FOUNDRY_TOKEN_SCOPE", "https://cognitiveservices.azure.com/.default")
    provider = get_bearer_token_provider(DefaultAzureCredential(), scope)
    endpoint = os.environ["FOUNDRY_ENDPOINT"]
    if args.api == "v1":
        return OpenAI(base_url=endpoint.rstrip("/") + "/openai/v1/", api_key=provider, max_retries=0)
    return AzureOpenAI(azure_endpoint=endpoint, azure_ad_token_provider=provider,
                       api_version=os.getenv("FOUNDRY_API_VERSION", "2025-04-01-preview"), max_retries=0)


def run_once(client, args, prompt: str, max_tokens: int):
    """Returns (measurement dict, number of throttled attempts before success)."""
    kwargs = dict(model=args.deployment, messages=[{"role": "user", "content": prompt}],
                  stream=True, stream_options={"include_usage": True})
    kwargs[args.token_param] = max_tokens
    if args.reasoning_effort.lower() not in ("", "omit"):
        kwargs["reasoning_effort"] = args.reasoning_effort
    if args.temperature is not None:
        kwargs["temperature"] = args.temperature

    throttled = 0
    for _ in range(10):
        start = time.perf_counter()
        try:
            stream = client.chat.completions.create(**kwargs)
            first, chunks, usage, model_name = None, 0, None, args.deployment
            for chunk in stream:
                if getattr(chunk, "model", None):
                    model_name = chunk.model
                if chunk.usage:
                    usage = chunk.usage
                if chunk.choices and chunk.choices[0].delta.content:
                    if first is None:
                        first = time.perf_counter() - start
                    chunks += 1
            total = time.perf_counter() - start
        except RateLimitError as e:
            throttled += 1
            wait = float(e.response.headers.get("retry-after", 5)) + 0.5
            print(f"  throttled (429), waiting {wait:.1f}s", flush=True)
            time.sleep(wait)
            continue

        pdet = getattr(usage, "prompt_tokens_details", None) if usage else None
        cdet = getattr(usage, "completion_tokens_details", None) if usage else None
        out_tokens = usage.completion_tokens if usage else chunks
        return {
            "model": model_name,
            "ttft_s": first, "total_s": total, "output_tokens": out_tokens,
            "input_tokens": usage.prompt_tokens if usage else None,
            "cached_tokens": (getattr(pdet, "cached_tokens", 0) or 0) if pdet else 0,
            "reasoning_tokens": (getattr(cdet, "reasoning_tokens", 0) or 0) if cdet else 0,
            "tokens_per_s": out_tokens / total if total else 0.0,
        }, throttled
    raise RuntimeError("still throttled after 10 attempts, increase the deployment capacity")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deployment", default=os.getenv("FOUNDRY_DEPLOYMENT"))
    ap.add_argument("--api", choices=["azure", "v1"], default="azure",
                    help="azure: AzureOpenAI client. v1: OpenAI client on /openai/v1/, needed for non OpenAI models such as Llama")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--max-new-tokens", type=int, default=128)
    ap.add_argument("--token-param", choices=["max_completion_tokens", "max_tokens"], default="max_completion_tokens")
    ap.add_argument("--only", help="comma separated prompt ids, e.g. short-01,medium-01,long-01")
    ap.add_argument("--sleep", type=float, default=0.0, help="seconds to pause between requests")
    ap.add_argument("--temperature", type=float, default=None, help="omit for models that do not support it, use 0 for Llama")
    ap.add_argument("--reasoning-effort", default="minimal",
                    help="GPT 5 models are reasoning models, minimal keeps reasoning tokens out of the latency numbers. Use omit for other models.")
    args = ap.parse_args()

    client = build_client(args)

    # Warmup: first request pays for token acquisition and connection setup.
    run_once(client, args, "Say OK.", 16)

    prompts = load_prompts()
    if args.only:
        wanted = set(args.only.split(","))
        prompts = [p for p in prompts if p["id"] in wanted]

    rows = []
    for item in prompts:
        for run in range(args.runs):
            result, throttled = run_once(client, args, item["prompt"], args.max_new_tokens)
            rows.append({"backend": "foundry", "deployment": args.deployment, "max_new_tokens": args.max_new_tokens,
                         "prompt_id": item["id"], "length": item["length"], "run": run,
                         "throttled": throttled, **result})
            print(f"{item['id']} run {run}: ttft={result['ttft_s']:.2f}s total={result['total_s']:.2f}s "
                  f"tokens={result['output_tokens']} throttled={throttled}", flush=True)
            if args.sleep:
                time.sleep(args.sleep)

    total_throttled = sum(r["throttled"] for r in rows)
    print("saved", save_raw(f"foundry_{args.deployment}", rows), f"| throttled attempts: {total_throttled}")


if __name__ == "__main__":
    main()
