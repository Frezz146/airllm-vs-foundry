# Running a 70B model on a laptop with AirLLM: what it costs in time, and where Microsoft Foundry fits

## TL;DR

AirLLM lets you run a 70 billion parameter model on a 64 GB MacBook by loading one layer at a time from disk. It works. It is also about 900 times slower than the same model deployed in Microsoft Foundry: 0.044 tokens per second locally versus roughly 40 tokens per second in the cloud. That makes AirLLM a great tool for offline experiments and a poor one for anything interactive. This post shows the measurements, the pitfalls I ran into on the Foundry side, and a simple rule for choosing between both.

All code, raw data and the Bicep template are in the repo: https://github.com/Frezz146/airllm-vs-foundry

## The idea behind AirLLM

A large language model is a stack of layers. Normally all of them must fit into memory (or GPU memory) at once. A 70B model in bf16 needs about 140 GB, far more than a laptop has.

AirLLM avoids this by keeping only one layer in memory. For every token it reads the first layer from disk, computes, throws it away, reads the next one, and so on until all 80 layers are done. Then the next token starts again. Memory is no longer the limit, disk speed is.

## The setup

I wanted a fair comparison, so both sides run the same model: Llama 3.3 70B Instruct.

- **Local:** MacBook Pro 16 inch with Apple silicon (M5 Max, 64 GB RAM, 2 TB SSD), AirLLM on the MLX backend, model from an ungated Hugging Face mirror.
- **Cloud:** Microsoft Foundry, Global Standard deployment in Sweden Central, Entra ID authentication only, deployed with Bicep and a small shell script that can also tear everything down again.
- **Workload:** three prompts (short, medium and long), 16 new tokens each, temperature 0. Foundry got 5 runs per prompt, AirLLM 2 because every run takes six minutes.

My first attempt used an 8B model. It fits into RAM, so AirLLM was never really tested. That comparison told me very little, which is why I repeated it with a model that is larger than the machine.

## The results

| Metric (median) | AirLLM, local | Foundry |
|---|---|---|
| Time to first token | 22.7 to 23.3 s | 0.34 to 0.36 s |
| Total time for 16 tokens | about 361 s | about 0.4 s |
| Throughput | 0.044 tokens/s | about 40 tokens/s |
| One time setup | 79 min (download and layer split) | a few minutes (deployment) |
| Cost | electricity and hardware | 0.71 USD per 1M input and output tokens |

A few things stand out:

- **Every token costs a full pass over the model.** About 20 seconds per token matches 140 GB read from the SSD at roughly 7 GB/s. The chip is not the bottleneck, the disk is.
- **Prompt length barely matters** for short prompts, because the cost is dominated by loading the layers.
- **A 200 token answer would take more than an hour** locally. In Foundry it takes a few seconds.
- **The cloud side is cheap.** Llama 3.3 70B in the Global Standard deployment costs 0.71 USD per million input and output tokens (Azure Retail Prices API, Sweden Central, checked on 6 October 2026). My 15 benchmark requests with about 59 input and 16 output tokens cost less than a tenth of a cent in total. Generating one million tokens locally at 0.044 tokens per second would take about 260 days.

## What I learned on the Foundry side

The benchmark itself taught me more than the numbers. Four pitfalls are worth knowing:

1. **Silent retries distort latency.** With a deployment capacity of 10 (in an earlier test run with gpt-5-mini), my first run showed a time to first token of about 5.4 seconds. The cause was throttling (HTTP 429) combined with automatic retries in the SDK, which hide the problem inside the timing. I now disable SDK retries in the benchmark, wait for the retry hint outside the timed section and count throttled attempts separately.
2. **Check quota before you deploy.** The Llama 3.3 70B quota in my subscription was 20 (thousand tokens per minute). My first deployment asked for 50 and the what-if validation rejected it. Running what-if before every deployment saved me from a half-created resource.
3. **The catalog and your account can disagree.** The model catalog listed version 10. My account offered versions 1 to 5 and 9. Ask the account itself with `az cognitiveservices account list-models` instead of trusting the web page.
4. **Not every model takes the same parameters.** Reasoning models such as gpt-5-mini need `max_completion_tokens` and a reasoning effort setting. For Llama through the OpenAI compatible v1 endpoint I used a different set. Always check what the specific deployment accepts.

## Which one should you use?

| Situation | AirLLM | Foundry |
|---|---|---|
| Offline prototype, no cloud allowed | works, slowly | not possible |
| Overnight batch with short outputs | possible if time is free | faster and cheap per token |
| Interactive chat or an agent | not usable | suitable |
| Many parallel users | one request at a time | scales with quota |
| Data must not leave the machine | fits | needs region choice and network isolation |
| Model larger than your memory | the real use case | managed models only |

My rule of thumb: use AirLLM when the constraint is "this must run here" and time does not matter. Use Foundry as soon as a human waits for the answer or more than one request arrives at a time.

## macOS, NVIDIA and what changes

I ran everything on a MacBook with Apple silicon, so AirLLM used its MLX backend. That has a few consequences:

- On macOS only Llama architecture models work, which is why Llama was the natural choice for both sides.
- There is no stop token handling, answers can repeat until the token limit is reached. It does not affect the timing.
- The first run downloads the model and splits it into one file per layer. For 70B that took 79 minutes and needs about twice the model size in free disk space, roughly 285 GB.

On a machine with an NVIDIA GPU the local numbers will look different, for example with the torch backend or 4 bit compression. I would still expect the same conclusion. The gap to the cloud is about 900 times, so even a setup that is ten times faster would be about 90 times slower than the Foundry deployment, and every token still needs a full pass over the layers from disk. This is an expectation based on the size of the gap, I did not measure it on NVIDIA hardware.

## Limits of this benchmark

- Small sample: 2 AirLLM runs per prompt and only 16 tokens. Read the numbers as an order of magnitude.
- The throughput figure for Foundry includes the startup time because only 16 tokens were generated. The pure generation rate is higher, but the order of magnitude stays the same.
- The OS file cache was not cleared, although a 140 GB model on a 64 GB machine limits that effect.
- One region and one time of day. Foundry latency can vary with load.
- The local side has no price tag here. Electricity and hardware wear are not included, and cloud prices can change.

## Try it yourself

```bash
git clone https://github.com/Frezz146/airllm-vs-foundry
cd airllm-vs-foundry
scripts/foundry.sh deploy -m Llama-3.3-70B-Instruct --model-format Meta --model-version 9 -d bench-llama --capacity 20
# run the benchmarks, then clean up
scripts/foundry.sh destroy
```

The destroy command removes the resource group and purges the soft deleted account, so nothing keeps costing money.
