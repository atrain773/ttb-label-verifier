# Approach, tools, and assumptions

A one-page summary. Full detail, measurements, and setup are in the [README](../README.md).

## Approach

**The AI reads the label; plain code makes the decision.** A vision model transcribes each field exactly as printed. Deterministic rules then compare those fields with the application and give every field **Pass**, **Fail**, or **Needs Review**, with a plain-English reason. This keeps verdicts fast, repeatable, unit-tested, and explainable. It also limits what a manipulated label can do: label text that tried to instruct the AI still failed in testing.

**A wrong approval costs more than a wrong rejection.** A label passes only when every check is confident. Anything uncertain (an unreadable photo, a near-miss brand name, a warning that may not be bold or looks too small) goes to a person as **Needs Review**. The tool never rejects on its own; the agent decides.

**Each rule follows a stakeholder:**
- **Dave:** brand and other text fields ignore capitalization and punctuation, so `STONE'S THROW` matches `Stone's Throw`.
- **Jenny:** the government warning must match 27 CFR 16.21 word for word, with `GOVERNMENT WARNING:` in bold capitals. A warning that looks much smaller than the rest of the label is sent for review.
- **Number fields:** ABV is compared as a number (and proof must equal 2× ABV). Net contents are converted between units (750 mL = 75 cL = 25.4 fl oz).
- **Required elements:** a label with no bottler name and address fails.

**Two ways to work:**
- **One label:** answers in 2–4 seconds against Sarah's 5-second bar.
- **Batch, for importers' 200–300-label submissions:** a CSV plus images, checked in parallel, with results filling in live and a downloadable results CSV. On the live site, 80 labels took 39 seconds.

**The model was chosen by measurement, not assumption.** On 17 generated test labels with a known answer key (wrong ABV, title-case or non-bold warning, tiny warning, missing fields, blur, glare, rotation, and more), Claude Sonnet 5.5 was the only model with no misses and no run over 5 seconds. Haiku approved a non-bold warning, and Opus was too slow at times.

## Tools used

| Tool | Why |
|---|---|
| **Python 3.12 + FastAPI** | Async handling for parallel batch checks; typed request validation |
| **Server-rendered HTML (Jinja2)**, no front-end framework | Large text, one button per screen, works in any agency browser |
| **Claude Sonnet 5.5** (Anthropic API) | Vision with structured output: returns a validated object, not text to parse |
| **Pydantic** | One schema shared by the model output, the rules, and the tests |
| **Pillow** | Validates uploads, corrects phone-photo rotation, shrinks images for speed |
| **pytest + GitHub Actions** | 81 offline tests (fake label reader, no API cost) on every pull request |
| **Render** | Hosting that redeploys automatically on every merge |

## Assumptions

- **Agents type the application values.** There is no COLA integration (per Marcus), so the form, or a CSV for batches, stands in for the application record.
- **Distilled spirits first.** Fields follow the spirits example in the brief. Beer and wine exemptions (e.g. ABV optional for some wines) are not modelled.
- **The application is the source of truth** for every field except the government warning, which is checked against the law.
- **Formatting differences are acceptable; wording differences are not**, except in the warning, where everything must match.
- **ABV must match the application exactly.** TTB tolerances apply to the product's actual alcohol content, not to the label vs. the application.
- **No data is stored.** Images are handled in memory and discarded (per Marcus); batch results are kept in memory for 2 hours.

## Main trade-offs

- **Cloud AI vs. TTB's firewall.** The reader calls Anthropic's API, which Marcus's network may block. It sits behind one swappable interface so an Azure-hosted or in-network model can replace it.
- **Generated test labels.** They prove the rules and compare models, but real bottle photos are harder; real labels are the next step for the eval set.
- **Type size is judged, not measured.** Millimetres can't be measured reliably from a photo, so a small-looking warning goes to a person rather than passing or failing.
- **Prototype hosting.** The free plan sleeps when idle (first load 30–60 seconds), and there is no login yet. See the README's *Path to production*.
