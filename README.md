# airllm-vs-foundry

Companion repo to the post on [blog.frezz-tech.de](https://blog.frezz-tech.de/). It compares running Llama 3.3 70B locally with [AirLLM](https://github.com/lyogavin/airllm) (layer streaming from disk) against the same model deployed in Microsoft Foundry.

> Independent project, not affiliated with Microsoft. Results are personal measurements on the hardware listed below.

## Question

When is running a model that is larger than your memory with AirLLM good enough, and when is a managed Foundry deployment the better answer?

## Result in short

Llama 3.3 70B, 16 new tokens, medians over short, medium and long prompts:

| | AirLLM (Apple silicon, MLX) | Foundry (Global Standard) |
|---|---|---|
| Time to first token | 22.7 to 23.3 s | 0.34 to 0.36 s |
| Total time for 16 tokens | about 361 s | about 0.4 s |
| Throughput | 0.044 tokens/s | about 40 tokens/s |
| Cost | not measured (energy and hardware) | 0.71 USD per 1M input and output tokens |

Details, setup and a scenario matrix are in [docs/decision_matrix.md](docs/decision_matrix.md), the chart is [docs/benchmark_70b.png](docs/benchmark_70b.png), the draft of the post is [docs/blog_post.md](docs/blog_post.md).

## Quick start

Python 3.12 is pinned in `.python-version`. The `airllm` extra (torch, transformers) often lags behind new Python releases, so always work inside the project venv created by uv.

```bash
uv venv                       # creates .venv with Python 3.12
uv sync --extra airllm
cp .env.example .env          # no API keys needed, Foundry uses Entra ID
az login

# 1. Foundry side: check availability, deploy (updates .env), benchmark
scripts/foundry.sh models Llama
scripts/foundry.sh deploy -m Llama-3.3-70B-Instruct --model-format Meta --model-version 9 -d bench-llama --capacity 20
uv run python src/bench_foundry.py --deployment bench-llama --api v1 \
  --reasoning-effort omit --temperature 0 --max-new-tokens 16 --runs 5 --sleep 3 \
  --only short-01,medium-01,long-01
# HTTP 400 about max_completion_tokens? Add: --token-param max_tokens

# 2. AirLLM side: download and split once, then measure
uv run python src/bench_airllm.py --model unsloth/Llama-3.3-70B-Instruct --prepare-only
caffeinate -i uv run python src/bench_airllm.py --model unsloth/Llama-3.3-70B-Instruct \
  --runs 2 --max-new-tokens 16 --only short-01,medium-01,long-01

# 3. Report (writes results/summary_70b.csv and docs/benchmark_70b.png)
uv run python src/report.py --filter 70B --name 70b

# 4. Clean up Azure
scripts/foundry.sh destroy
```

Check the available versions and quota in your own account first. In my subscription the catalog listed version 10, the account offered versions 1 to 5 and 9, and the quota for Llama 3.3 70B was 20 (thousand tokens per minute).

## Foundry resources

`scripts/foundry.sh` creates and removes everything the benchmark needs. It uses your current `az login` context, shows a what-if and asks before applying. Defaults: region `swedencentral`, resource group and account names with the prefix `frezz`, authentication with Entra ID only. `destroy` only touches resource groups that carry the tag `purpose=airllm-vs-foundry` and purges the soft deleted Foundry resource. If you lack Owner rights on the resource group, deploy with `--no-role` and assign "Cognitive Services OpenAI User" yourself. Run `scripts/foundry.sh --help` for all options.

For the cost line in the report set `FOUNDRY_PRICE_CURRENCY`, the two prices and `FOUNDRY_PRICE_MODEL` in `.env`. The values in `.env.example` are the Llama 3.3 70B Global Standard prices from the Azure Retail Prices API for Sweden Central, checked on 2026-10-06. Prices can change.

## Method

- Fixed prompt set in `prompts/prompts.jsonl`, the benchmark uses one short, one medium and one long prompt.
- Foundry: 5 runs per prompt, SDK retries disabled, throttled attempts (HTTP 429) are waited out of the timed section and counted separately, one warmup request, streaming with Entra ID.
- AirLLM: 2 runs per prompt because one run takes about six minutes. AirLLM does not stream, so time to first token is approximated with a 1 token generation.
- Both sides generate 16 tokens with the same model. Foundry uses temperature 0.
- Metrics: time to first token, total time, output tokens per second, cost per run. Raw data is in `results/raw`.

## macOS specifics and other hardware

I tested on a MacBook with Apple silicon, so the AirLLM numbers come from the MLX backend:

- On macOS `AutoModel` always selects the MLX Llama implementation, so only Llama architecture models work there.
- `generate()` returns text, so output tokens are counted by re-encoding. There is no stop token handling, answers can repeat until the token limit is reached.
- The first run downloads and splits the model into one file per layer. For 70B that took 79 minutes and needs roughly twice the model size in free disk space (about 285 GB).

On a machine with an NVIDIA GPU the AirLLM numbers will look different, for example through the torch backend or 4 bit compression. The conclusion should not change, because the gap to the cloud is about 900 times. Even a setup that is ten times faster would still be about 90 times slower than the Foundry deployment, and every generated token still requires a full pass over the layers from disk. That is an expectation based on the size of the gap, I did not measure it on NVIDIA hardware.

## Limits

- Small sample: 2 AirLLM runs per prompt and only 16 new tokens. Read the numbers as an order of magnitude.
- With 16 tokens the Foundry throughput includes the startup time and is lower than the pure generation rate.
- The OS file cache was not cleared. The model (140 GB) is larger than the RAM (64 GB), which limits the effect.
- One region, one time of day. Foundry latency can vary with load.
- Prompts are short. For long contexts the AirLLM share of compute grows.
- The comparison is about operating characteristics, not answer quality.
- The local side has no price tag. Electricity and hardware wear are not included.

## Hardware used

- MacBook Pro 16 inch, Apple M5 Max, 64 GB unified memory, 2 TB internal SSD, macOS Tahoe 26.6.2
- AirLLM with MLX, Python 3.12
- Model: `unsloth/Llama-3.3-70B-Instruct` (ungated mirror of the Meta release), bf16

Measurements from other hardware are welcome as pull requests or issues.

## License

MIT
