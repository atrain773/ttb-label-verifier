"""Batch verification: many labels plus one CSV of application values, checked in parallel.

Jobs live in memory only (the prototype stores nothing). Each row is processed
independently, so one bad image or API hiccup affects that row, not the batch.
"""

import asyncio
import csv
import io
import time
import uuid
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.extraction import ExtractionError, Extractor
from app.models import ApplicationData, Status, VerificationResult
from app.verify import verify_label

MAX_BATCH_FILES = 300
JOB_TTL_SECONDS = 2 * 60 * 60

REQUIRED_COLUMNS = ["filename", "brand_name", "class_type", "alcohol_content", "net_contents"]
OPTIONAL_COLUMNS = ["bottler_name_address", "country_of_origin"]
TEMPLATE_CSV = ",".join(REQUIRED_COLUMNS + OPTIONAL_COLUMNS) + "\n"


class BatchInputError(ValueError):
    """Raised with a message that is safe to show the user."""


@dataclass
class BatchRow:
    filename: str
    application: ApplicationData | None
    image_jpeg: bytes | None
    state: str = "waiting"  # waiting | checking | done | error
    result: VerificationResult | None = None
    error: str | None = None

    @property
    def display_status(self) -> str:
        """One of pass / fail / review / error / waiting / checking, used for colors and counts."""
        if self.state == "done" and self.result:
            return self.result.status.value
        return self.state


@dataclass
class BatchJob:
    id: str
    rows: list[BatchRow]
    created: float = field(default_factory=time.time)
    started: float = field(default_factory=time.perf_counter)
    finished: float | None = None
    task: asyncio.Task | None = None  # held so the background run isn't garbage-collected

    @property
    def done(self) -> bool:
        return all(r.state in ("done", "error") for r in self.rows)

    def counts(self) -> dict[str, int]:
        counts = {k: 0 for k in ("pass", "fail", "review", "error", "waiting", "checking")}
        for row in self.rows:
            counts[row.display_status] += 1
        return counts

    @property
    def elapsed_seconds(self) -> float:
        end = self.finished if self.finished is not None else time.perf_counter()
        return round(end - self.started, 1)


_jobs: dict[str, BatchJob] = {}


def _normalize_header(name: str) -> str:
    return "_".join(name.strip().lower().replace("/", " ").split())


def parse_applications(csv_bytes: bytes) -> dict[str, ApplicationData | str]:
    """Map lowercase filename -> application, or -> an error message for a bad row."""
    try:
        text = csv_bytes.decode("utf-8-sig")  # Excel adds a byte-order mark
    except UnicodeDecodeError:
        raise BatchInputError("The CSV file could not be read. Please save it as CSV (UTF-8).")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise BatchInputError("The CSV file is empty.")
    reader.fieldnames = [_normalize_header(h) for h in reader.fieldnames]
    missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
    if missing:
        raise BatchInputError(
            f"The CSV is missing these columns: {', '.join(missing)}. Download the template to see the expected layout."
        )

    applications: dict[str, ApplicationData | str] = {}
    for line_number, raw in enumerate(reader, start=2):
        row = {k: (v or "").strip() for k, v in raw.items() if k}
        if not any(row.values()):
            continue  # blank line
        filename = row.get("filename", "")
        if not filename:
            raise BatchInputError(f"Row {line_number} of the CSV has no filename.")
        key = filename.lower()
        if key in applications:
            raise BatchInputError(f'"{filename}" appears more than once in the CSV.')
        empty = [c for c in REQUIRED_COLUMNS[1:] if not row.get(c)]
        if empty:
            applications[key] = f"CSV row {line_number} is missing: {', '.join(empty)}."
            continue
        try:
            applications[key] = ApplicationData(**{c: row.get(c, "") for c in REQUIRED_COLUMNS[1:] + OPTIONAL_COLUMNS})
        except ValidationError:
            applications[key] = f"CSV row {line_number} could not be read."
    if not applications:
        raise BatchInputError("The CSV has no rows.")
    return applications


def build_rows(
    applications: dict[str, ApplicationData | str],
    images: dict[str, bytes | str],
) -> list[BatchRow]:
    """Pair CSV rows with uploaded images by filename (case-insensitive).

    `images` maps original filename -> prepared JPEG, or -> an error message if the
    image could not be opened. Unmatched rows and images become error rows.
    """
    images_by_key = {name.lower(): (name, data) for name, data in images.items()}
    rows: list[BatchRow] = []

    for key, application in applications.items():
        name, image = images_by_key.pop(key, (key, None))
        row = BatchRow(
            filename=name,
            application=application if isinstance(application, ApplicationData) else None,
            image_jpeg=image if isinstance(image, bytes) else None,
        )
        if isinstance(application, str):
            row.state, row.error = "error", application
        elif image is None:
            row.state, row.error = "error", "No image uploaded with this filename."
        elif isinstance(image, str):
            row.state, row.error = "error", image
        rows.append(row)

    for name, _ in images_by_key.values():
        rows.append(
            BatchRow(filename=name, application=None, image_jpeg=None, state="error", error="No CSV row for this image.")
        )
    return rows


def create_job(rows: list[BatchRow]) -> BatchJob:
    _expire_old_jobs()
    job = BatchJob(id=uuid.uuid4().hex[:12], rows=rows)
    _jobs[job.id] = job
    return job


def get_job(job_id: str) -> BatchJob | None:
    return _jobs.get(job_id)


def _expire_old_jobs() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    for job_id in [j.id for j in _jobs.values() if j.created < cutoff]:
        del _jobs[job_id]


async def run_job(job: BatchJob, extractor: Extractor, concurrency: int) -> None:
    """Check every pending row, at most `concurrency` at a time. Never raises."""
    limit = asyncio.Semaphore(concurrency)

    async def check(row: BatchRow) -> None:
        async with limit:
            row.state = "checking"
            try:
                row.result = await verify_label(row.application, row.image_jpeg, extractor)
                row.state = "done"
            except ExtractionError as exc:
                row.state, row.error = "error", str(exc)
            except Exception:  # one unexpected failure must not stall the batch
                row.state, row.error = "error", "Unexpected problem checking this label. Please check it singly."
            finally:
                row.image_jpeg = None  # free memory as soon as the row is finished

    await asyncio.gather(*(check(r) for r in job.rows if r.state == "waiting"))
    job.finished = time.perf_counter()


def results_csv(job: BatchJob) -> str:
    """One row per label: verdict plus the reason for every field that did not pass."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["filename", "verdict", "problems"])
    labels = {"pass": "Pass", "fail": "Fail", "review": "Needs review", "error": "Error"}
    for row in job.rows:
        status = row.display_status
        if row.result:
            problems = "; ".join(
                f"{f.field}: {f.reason}" for f in row.result.fields if f.status != Status.PASS
            )
            if not row.result.fields or status == "review" and not problems:
                problems = row.result.summary
        else:
            problems = row.error or ""
        writer.writerow([row.filename, labels.get(status, status), problems])
    return out.getvalue()
