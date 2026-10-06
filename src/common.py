import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_prompts(path: Path | None = None) -> list[dict]:
    path = path or ROOT / "prompts" / "prompts.jsonl"
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def save_raw(name: str, rows: list[dict]) -> Path:
    out = ROOT / "results" / "raw" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def median(values: list[float]) -> float:
    return statistics.median(values) if values else float("nan")
