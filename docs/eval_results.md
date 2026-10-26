# Extraction accuracy eval

16 synthetic labels (see `scripts/generate_labels.py`), 3 run(s) per label per model. A field counts as correct only if transcribed exactly (whitespace aside). Latency is the model call alone; the app adds roughly 0.1–0.2s.

## Summary

| Model | Fields exact | Warning text exact | Bold header correct | Median s | p90 s | Max s | Over 5s | Errors |
|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 | 336/336 (100%) | 48/48 | 45/48 | 2.0 | 2.8 | 6.9 | 2/48 | 0 |
| claude-sonnet-5-5 | 336/336 (100%) | 48/48 | 48/48 | 2.7 | 4.0 | 4.6 | 0/48 | 0 |
| claude-opus-5-5 | 336/336 (100%) | 48/48 | 48/48 | 3.7 | 4.6 | 7.5 | 2/48 | 0 |

## Misses by label

Each entry: model, run → field: what it read (expected in the answer key).

### 05_warning_not_bold.png: Warning header not bold.
- claude-haiku-5-5 run 0 → bold header: True (expected False)
- claude-haiku-5-5 run 1 → bold header: True (expected False)
- claude-haiku-5-5 run 2 → bold header: True (expected False)

