# TTB Label Verifier

A prototype that helps TTB compliance agents check alcohol label artwork against the application data. It reports each field as **Pass**, **Fail**, or **Needs Review**.

> Status: work in progress. Features land one pull request at a time. See [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md) for the original assignment.

## Run locally

Requires Python 3.10+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # then add your ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

Open http://localhost:8000.

## Test

```bash
pytest
```

## Accuracy and model choice

The vision model only **reads** the label. Every pass/fail decision is plain code (`app/matching.py`, `app/warning.py`). So the question for model choice is how faithfully and how fast it transcribes.

We measured this with an evaluation set: 16 generated labels with a known answer key (`scripts/generate_labels.py`). They include compliance defects (wrong ABV, proof ≠ 2× ABV, title-case warning, non-bold warning header, reworded warning, missing net contents) and photo defects (blur, rotation, glare, low resolution, dim lighting). Each model read every label 3 times:

| Model | Fields read exactly | Bold header correct | Median | Slowest | Over 5s |
|---|---|---|---|---|---|
| Haiku 5.5 | 100% | 45/48 | 2.0s | 6.9s | 2/48 |
| **Sonnet 5.5** (chosen) | 100% | **48/48** | 2.7s | **4.6s** | **0/48** |
| Opus 5.5 | 100% | 48/48 | 3.7s | 7.5s | 2/48 |

- **Haiku** called a non-bold warning header "bold" every time, which would approve a label that should be rejected.
- **Opus** was as accurate as Sonnet but broke the 5-second requirement on some runs.
- **Sonnet** was the only model with no misses and no run over 5 seconds.

Full report: [docs/eval_results.md](docs/eval_results.md). Re-run it with `python scripts/generate_labels.py && python scripts/eval_extraction.py` (about 150 API calls, under $1).

**Limitation:** these labels are computer-generated, so all three models transcribed 100% of the text. Real bottle photos are harder. The next step is to add real, agent-supplied labels to the answer key. The model is a single setting (`EXTRACTION_MODEL`), so switching costs nothing if real labels change the ranking.

## Deploy

The app deploys to [Render](https://render.com) from `render.yaml`. Set `ANTHROPIC_API_KEY` in the Render dashboard.

**Cold start on the free plan.** The prototype runs on Render's free plan, which puts the app to sleep after about 15 minutes without traffic. The first visit after that can take 30–60 seconds while it wakes up; after that, label checks return in a few seconds. If the first page load is slow, wait for it once and continue.

## Path to production

These are deliberately out of scope for the prototype, but the design leaves room for them:

- **Always-on hosting.** A paid plan (Render Starter, or an Azure App Service tier in TTB's own tenant) removes the cold start so the first check of the day is as fast as the rest.
