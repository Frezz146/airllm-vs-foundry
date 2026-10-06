"""Benchmark AirLLM.

Linux with CUDA: standard AirLLM path with torch tensors.
macOS (Apple silicon): AutoModel always returns the MLX Llama implementation, so only Llama
architecture models work. generate() takes an mx.array and returns the decoded text.

AirLLM does not stream. Time to first token is approximated with a 1 token generation,
total time comes from a full generation.
"""
import argparse
import os
import sys
import time

from dotenv import load_dotenv

from common import load_prompts, save_raw

load_dotenv()
IS_MAC = sys.platform == "darwin"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.getenv("AIRLLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct"))
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--max-new-tokens", type=int, default=32)
    ap.add_argument("--only", help="comma separated prompt ids, e.g. short-01,medium-01,long-01")
    ap.add_argument("--prepare-only", action="store_true",
                    help="download and split the model, then exit (no measurement, so it can run while the machine is busy)")
    ap.add_argument("--compression", choices=["4bit", "8bit"], default=None)
    ap.add_argument("--delete-original", action="store_true",
                    help="delete the downloaded original after splitting to save disk space")
    ap.add_argument("--device", default="cuda", help="cuda or cpu, ignored on macOS")
    args = ap.parse_args()

    from airllm import AutoModel

    kwargs = {}
    if args.compression:
        kwargs["compression"] = args.compression
    if args.delete_original:
        kwargs["delete_original"] = True
    if os.getenv("HF_TOKEN"):
        kwargs["hf_token"] = os.getenv("HF_TOKEN")

    load_start = time.perf_counter()
    model = AutoModel.from_pretrained(args.model, **kwargs)
    load_seconds = time.perf_counter() - load_start
    print(f"model ready after {load_seconds:.0f}s (includes download and layer splitting on first run)")
    if args.prepare_only:
        print("prepared, nothing measured")
        return

    if IS_MAC:
        import mlx.core as mx

        def generate(text: str, new_tokens: int):
            tokens = model.tokenizer([text], return_tensors="np", return_attention_mask=False,
                                     truncation=True, max_length=512, padding=False)
            start = time.perf_counter()
            out = model.generate(mx.array(tokens["input_ids"]), max_new_tokens=new_tokens)
            elapsed = time.perf_counter() - start
            # generate() returns text, count tokens by re-encoding (approximation)
            produced = len(model.tokenizer(out, add_special_tokens=False)["input_ids"])
            return elapsed, produced, out
    else:
        def generate(text: str, new_tokens: int):
            tokens = model.tokenizer([text], return_tensors="pt", return_attention_mask=False,
                                     truncation=True, max_length=512, padding=False)
            ids = tokens["input_ids"]
            ids = ids.cuda() if args.device == "cuda" else ids
            start = time.perf_counter()
            out = model.generate(ids, max_new_tokens=new_tokens, use_cache=True, return_dict_in_generate=True)
            elapsed = time.perf_counter() - start
            text = model.tokenizer.decode(out.sequences[0][ids.shape[1]:])
            return elapsed, out.sequences.shape[1] - ids.shape[1], text

    prompts = load_prompts()
    if args.only:
        wanted = set(args.only.split(","))
        prompts = [p for p in prompts if p["id"] in wanted]

    rows = []
    for item in prompts:
        for run in range(args.runs):
            ttft, _, _ = generate(item["prompt"], 1)
            total, produced, text = generate(item["prompt"], args.max_new_tokens)
            rows.append({
                "backend": "airllm", "model": args.model, "compression": args.compression,
                "platform": "macos-mlx" if IS_MAC else "linux-torch",
                "max_new_tokens": args.max_new_tokens,
                "prompt_id": item["id"], "length": item["length"], "run": run,
                "ttft_s": ttft, "total_s": total, "output_tokens": produced,
                "tokens_per_s": produced / total if total else 0.0,
                "model_load_s": load_seconds,
                "output_preview": text[:200],
            })
            print(f"{item['id']} run {run}: ttft={ttft:.1f}s total={total:.1f}s tokens={produced}", flush=True)

    print("saved", save_raw(f"airllm_{args.model.replace('/', '_')}", rows))


if __name__ == "__main__":
    main()
