#!/usr/bin/env bash
# One shot smoke test for the AirLLM benchmark on a Mac (Apple silicon, MLX).
# Prints hardware and disk info, installs the airllm extra into the project venv
# and runs a tiny Llama architecture model for one prompt.
#
#   scripts/airllm_smoke.sh [model]     default: TinyLlama/TinyLlama-1.1B-Chat-v1.0
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODEL="${1:-TinyLlama/TinyLlama-1.1B-Chat-v1.0}"

echo "== Hardware (for the README) =="
if [[ "$(uname -s)" == "Darwin" ]]; then
  echo "Chip   : $(sysctl -n machdep.cpu.brand_string)"
  echo "Memory : $(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 )) GB"
  echo "macOS  : $(sw_vers -productVersion)"
else
  echo "Not macOS, the AirLLM path will use torch."
fi
echo
echo "== Free disk space (model download and layer split need roughly 2x the model size) =="
df -h "$HOME" | tail -1
echo "HF cache: $(du -sh "${HF_HOME:-$HOME/.cache/huggingface}" 2>/dev/null | cut -f1 || echo none)"
echo

[[ -d .venv ]] || uv venv
echo "== Installing dependencies (uv sync --extra airllm) =="
uv sync --extra airllm
echo
echo "== Versions =="
uv run python - <<'PY'
import sys
print("python", sys.version.split()[0])
for name in ("airllm", "torch", "transformers", "mlx"):
    try:
        from importlib.metadata import version
        print(name, version(name))
    except Exception as e:
        print(name, "NOT INSTALLED:", e)
PY
echo
echo "== Smoke test: $MODEL =="
uv run python src/bench_airllm.py --model "$MODEL" --runs 1 --max-new-tokens 8 --only short-01
echo
echo "Smoke test finished. Raw result: results/raw/airllm_${MODEL//\//_}.json"
