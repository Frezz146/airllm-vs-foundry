# Results and decision matrix

Measured on 2026-10-06. Raw data in `results/raw`, aggregate in `results/summary_70b.csv`, chart in `docs/images/benchmark_70b.png`.

## Setup

| | AirLLM | Foundry |
|---|---|---|
| Model | `unsloth/Llama-3.3-70B-Instruct`, bf16, about 140 GB | `Llama-3.3-70B-Instruct` version 9, Global Standard, Sweden Central, quota 20 |
| Runtime | MLX on MacBook Pro 16 inch, Apple M5 Max, 64 GB, 2 TB SSD, macOS 26.6.2 | Entra ID auth, streaming, temperature 0 |
| New tokens | 16 | 16 |
| Runs | 2 per prompt, 3 prompts (short, medium, long) | 5 per prompt, 3 prompts |

## Measured (median)

| Metric | AirLLM | Foundry |
|---|---|---|
| Time to first token | 22.7 to 23.3 s | 0.34 to 0.36 s |
| Total time for 16 tokens | 359 to 362 s | 0.39 to 0.40 s |
| Throughput | 0.044 tokens/s | 40 to 41 tokens/s (includes startup, 16 tokens only) |
| Throttled attempts (429) | not applicable | 0 |
| Cost | not measured (energy and hardware) | 0.71 USD per 1M input and output tokens, 0.000053 USD per request here (59 input and 16 output tokens) |
| One time setup | 79 min (download and layer split) | deployment with Bicep |

Notes: each token needs one pass over all 80 layers (about 20 s, roughly 7 GB/s from the SSD), so prompt length has almost no effect for short prompts. Price source: Azure Retail Prices API for Sweden Central, Global Standard, checked on 2026-10-06 (Data Zone 0.781 USD, Regional 0.859 USD per 1M tokens). Cached input is not priced for Llama.

## Scope and transfer to other hardware

Measured on Apple silicon with the MLX backend, so the AirLLM figures are specific to this machine. On an NVIDIA GPU they will differ. The conclusion should not, because the gap is about 900 times: a setup that is ten times faster would still be about 90 times slower than Foundry. This is an expectation, not a measurement.

## Scenarios (assessment, not measured)

| Scenario | AirLLM | Foundry |
|---|---|---|
| Offline prototype, no cloud allowed | works, slowly | not possible |
| Overnight batch with short outputs | possible if time is free | faster and cheap per token |
| Interactive chat or an agent | not usable | suitable |
| Many parallel users | serves one request at a time | scales with quota |
| Strict data residency | data stays on the machine | region choice and network isolation needed |
| Model larger than available memory | the actual use case of AirLLM | managed models only |
| Rare use, lowest fixed cost | no cloud cost, high waiting time | pay per token |
