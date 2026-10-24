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

## Deploy

The app deploys to [Render](https://render.com) from `render.yaml`. Set `ANTHROPIC_API_KEY` in the Render dashboard.
