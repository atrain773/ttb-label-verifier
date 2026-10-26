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

**Cold start on the free plan.** The prototype runs on Render's free plan, which puts the app to sleep after about 15 minutes without traffic. The first visit after that can take 30–60 seconds while it wakes up; after that, label checks return in a few seconds. If the first page load is slow, wait for it once and continue.

## Path to production

These are deliberately out of scope for the prototype, but the design leaves room for them:

- **Always-on hosting.** A paid plan (Render Starter, or an Azure App Service tier in TTB's own tenant) removes the cold start so the first check of the day is as fast as the rest.
