"""Score how accurately each model reads the test labels, and how fast.

For every label in samples/labels/answer_key.json, each model reads the image
several times. Each field is compared to the answer key *exactly* (whitespace
aside): the reader's job is faithful transcription, and the matching rules decide
what differences are acceptable.

Usage:
    python scripts/eval_extraction.py                       # all default models, 3 runs each
    python scripts/eval_extraction.py --models claude-sonnet-5-5 --runs 1

Writes a markdown report to docs/eval_results.md.
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.extraction import ClaudeExtractor  # noqa: E402
from app.images import prepare_image  # noqa: E402

LABEL_DIR = ROOT / "samples" / "labels"
REPORT_PATH = ROOT / "docs" / "eval_results.md"
DEFAULT_MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]
TEXT_FIELDS = [
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "bottler_name_address",
    "country_of_origin",
    "government_warning_text",
]


def same_text(expected: str | None, found: str | None) -> bool:
    if not expected:
        return not found
    return found is not None and " ".join(expected.split()) == " ".join(found.split())


async def run_model(model: str, labels: dict, images: dict, runs: int, client) -> list[dict]:
    extractor = ClaudeExtractor(client, model, get_settings().extraction_effort)
    rows = []
    for filename, key in labels.items():
        for run in range(runs):
            started = time.perf_counter()
            try:
                label = await extractor.extract(images[filename])
                error = None
            except Exception as exc:  # record and keep going; one failure shouldn't sink the eval
                label, error = None, str(exc)
            seconds = time.perf_counter() - started
            row = {"model": model, "label": filename, "run": run, "seconds": seconds, "error": error}
            if label:
                row["fields"] = {f: same_text(key[f], getattr(label, f)) for f in TEXT_FIELDS}
                row["found"] = {f: getattr(label, f) for f in TEXT_FIELDS}
                row["bold"] = label.warning_header_appears_bold
                row["legible"] = label.image_legible
            rows.append(row)
        print(f"  {model}: {filename} done", flush=True)
    return rows


def summarize(rows: list[dict], labels: dict, models: list[str]) -> str:
    out = ["# Extraction accuracy eval", ""]
    out.append(
        f"{len(labels)} synthetic labels (see `scripts/generate_labels.py`), "
        f"{len(rows) // (len(labels) * len(models))} run(s) per label per model. "
        "A field counts as correct only if transcribed exactly (whitespace aside). "
        "Latency is the model call alone; the app adds roughly 0.1–0.2s."
    )
    out += ["", "## Summary", ""]
    out.append("| Model | Fields exact | Warning text exact | Bold header correct | Median s | p90 s | Max s | Over 5s | Errors |")
    out.append("|---|---|---|---|---|---|---|---|---|")

    by_model = defaultdict(list)
    for r in rows:
        by_model[r["model"]].append(r)

    for model in models:
        mrows = by_model[model]
        ok = [r for r in mrows if not r["error"]]
        field_hits = sum(sum(r["fields"].values()) for r in ok)
        field_total = sum(len(r["fields"]) for r in ok)
        warn_hits = sum(r["fields"]["government_warning_text"] for r in ok)
        bold_hits = sum(r["bold"] == labels[r["label"]]["warning_header_appears_bold"] for r in ok)
        times = sorted(r["seconds"] for r in mrows)
        p90 = times[max(0, int(round(0.9 * len(times))) - 1)]
        over = sum(t > 5 for t in times)
        out.append(
            f"| {model} | {field_hits}/{field_total} ({100 * field_hits / max(field_total, 1):.0f}%) "
            f"| {warn_hits}/{len(ok)} | {bold_hits}/{len(ok)} "
            f"| {statistics.median(times):.1f} | {p90:.1f} | {times[-1]:.1f} | {over}/{len(times)} "
            f"| {len(mrows) - len(ok)} |"
        )

    out += ["", "## Misses by label", ""]
    out.append("Each entry: model, run → field: what it read (expected in the answer key).")
    out.append("")
    for filename, key in labels.items():
        misses = []
        for r in rows:
            if r["label"] != filename:
                continue
            if r["error"]:
                misses.append(f"- {r['model']} run {r['run']}: error: {r['error']}")
                continue
            for f, correct in r["fields"].items():
                if not correct:
                    misses.append(f"- {r['model']} run {r['run']} → `{f}`: {r['found'][f]!r} (expected {key[f]!r})")
            if r["bold"] != key["warning_header_appears_bold"]:
                misses.append(
                    f"- {r['model']} run {r['run']} → bold header: {r['bold']} (expected {key['warning_header_appears_bold']})"
                )
        if misses:
            out.append(f"### {filename}: {key['description']}")
            out += misses + [""]
    return "\n".join(out) + "\n"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--report", type=Path, default=REPORT_PATH, help="where to write the markdown report")
    args = parser.parse_args()

    labels = json.loads((LABEL_DIR / "answer_key.json").read_text())
    images = {name: prepare_image((LABEL_DIR / name).read_bytes()) for name in labels}
    client = anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key, timeout=30, max_retries=1)

    # Models run side by side; labels within a model run one at a time so latency stays realistic.
    results = await asyncio.gather(*(run_model(m, labels, images, args.runs, client) for m in args.models))
    rows = [r for model_rows in results for r in model_rows]

    args.report.write_text(summarize(rows, labels, args.models))
    print(f"\nReport written to {args.report}")


if __name__ == "__main__":
    asyncio.run(main())
