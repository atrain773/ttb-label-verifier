import asyncio
import io
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import batch
from app.extraction import ExtractionError, get_batch_extractor
from app.main import app
from app.models import ApplicationData, ExtractedLabel
from app.warning import STANDARD_WARNING

HEADER = "filename,brand_name,class_type,alcohol_content,net_contents\n"
GOOD = "Old Tom Distillery,Kentucky Straight Bourbon Whiskey,45%,750 mL\n"

LABEL = ExtractedLabel(
    image_legible=True,
    brand_name="OLD TOM DISTILLERY",
    class_type="Kentucky Straight Bourbon Whiskey",
    alcohol_content="45% Alc./Vol. (90 Proof)",
    net_contents="750 mL",
    bottler_name_address="Bottled by Old Tom Distillery, Bardstown, KY",
    government_warning_text=STANDARD_WARNING,
    warning_header_appears_bold=True,
)


def png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(buf, format="PNG")
    return buf.getvalue()


class FakeExtractor:
    """Returns a label per image; the image bytes pick which via a lookup on the job."""

    def __init__(self, labels: list[ExtractedLabel | Exception]):
        self._labels = iter(labels)
        self.max_in_flight = 0
        self._in_flight = 0

    async def extract(self, image_jpeg: bytes) -> ExtractedLabel:
        self._in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self._in_flight)
        await asyncio.sleep(0.01)
        self._in_flight -= 1
        item = next(self._labels)
        if isinstance(item, Exception):
            raise item
        return item


# --- CSV parsing -------------------------------------------------------------


def test_parse_valid_csv_with_excel_bom_and_spaced_headers():
    csv_bytes = ("﻿Filename,Brand Name,Class/Type,Alcohol Content,Net Contents\nA.png," + GOOD).encode()
    apps = batch.parse_applications(csv_bytes)
    assert isinstance(apps["a.png"], ApplicationData)
    assert apps["a.png"].brand_name == "Old Tom Distillery"


def test_missing_column_is_a_clear_error():
    with pytest.raises(batch.BatchInputError, match="net_contents"):
        batch.parse_applications(b"filename,brand_name,class_type,alcohol_content\na.png,x,y,45%\n")


def test_duplicate_filename_is_an_error():
    with pytest.raises(batch.BatchInputError, match="more than once"):
        batch.parse_applications((HEADER + "a.png," + GOOD + "A.PNG," + GOOD).encode())


def test_row_with_empty_required_field_becomes_row_error_not_batch_error():
    apps = batch.parse_applications((HEADER + "a.png," + GOOD + "b.png,,Gin,40%,750 mL\n").encode())
    assert isinstance(apps["a.png"], ApplicationData)
    assert "brand_name" in apps["b.png"]


def test_blank_lines_are_ignored():
    apps = batch.parse_applications((HEADER + "a.png," + GOOD + ",,,,\n").encode())
    assert list(apps) == ["a.png"]


# --- Pairing rows with images -------------------------------------------------


def test_build_rows_matches_case_insensitively_and_flags_orphans():
    apps = batch.parse_applications((HEADER + "a.png," + GOOD + "b.png," + GOOD).encode())
    rows = batch.build_rows(apps, {"A.PNG": b"jpeg", "extra.png": b"jpeg"})
    by_name = {r.filename: r for r in rows}
    assert by_name["A.PNG"].state == "waiting"
    assert by_name["b.png"].error == "No image uploaded with this filename."
    assert by_name["extra.png"].error == "No CSV row for this image."


def test_unreadable_image_becomes_row_error():
    apps = batch.parse_applications((HEADER + "a.png," + GOOD).encode())
    rows = batch.build_rows(apps, {"a.png": "That file is not a picture we can open."})
    assert rows[0].state == "error" and "not a picture" in rows[0].error


# --- Running a job ------------------------------------------------------------


def test_run_job_checks_rows_in_parallel_within_limit_and_isolates_failures():
    apps = batch.parse_applications((HEADER + "".join(f"{i}.png," + GOOD for i in range(6))).encode())
    rows = batch.build_rows(apps, {f"{i}.png": b"jpeg" for i in range(6)})
    wrong_abv = LABEL.model_copy(update={"alcohol_content": "40% Alc./Vol."})
    extractor = FakeExtractor([LABEL, wrong_abv, ExtractionError("The label reader is busy."), LABEL, LABEL, LABEL])
    job = batch.create_job(rows)

    asyncio.run(batch.run_job(job, extractor, concurrency=3))

    assert job.done and job.finished is not None
    assert 1 < extractor.max_in_flight <= 3
    counts = job.counts()
    assert (counts["pass"], counts["fail"], counts["error"]) == (4, 1, 1)
    assert all(r.image_jpeg is None for r in job.rows)  # memory released


def test_results_csv_lists_reasons_for_problems():
    apps = batch.parse_applications((HEADER + "a.png," + GOOD + "b.png," + GOOD).encode())
    job = batch.create_job(batch.build_rows(apps, {"a.png": b"jpeg", "b.png": b"jpeg"}))
    wrong_abv = LABEL.model_copy(update={"alcohol_content": "40% Alc./Vol."})
    asyncio.run(batch.run_job(job, FakeExtractor([LABEL, wrong_abv]), concurrency=1))

    out = batch.results_csv(job)
    assert "a.png,Pass," in out
    assert "b.png,Fail,Alcohol content: Label says 40%" in out


# --- Routes -------------------------------------------------------------------


@pytest.fixture
def client():
    with TestClient(app) as c:  # context manager keeps one event loop for background tasks
        yield c
    app.dependency_overrides.clear()


def wait_until_done(client, job_url: str, timeout: float = 5.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        html = client.get(job_url + "/table").text
        if "data-done=\"true\"" in html:
            return html
        time.sleep(0.05)
    raise AssertionError("batch did not finish")


def test_batch_end_to_end(client):
    wrong_abv = LABEL.model_copy(update={"alcohol_content": "40% Alc./Vol."})
    app.dependency_overrides[get_batch_extractor] = lambda: FakeExtractor([LABEL, wrong_abv])
    files = [
        ("applications_csv", ("apps.csv", (HEADER + "a.png," + GOOD + "b.png," + GOOD).encode(), "text/csv")),
        ("label_images", ("a.png", png_bytes(), "image/png")),
        ("label_images", ("b.png", png_bytes(), "image/png")),
    ]
    response = client.post("/batch", files=files, follow_redirects=False)
    assert response.status_code == 303
    job_url = response.headers["location"]

    html = wait_until_done(client, job_url)
    assert "All 2 labels checked" in html
    assert "1 Fail" in html and "1 Pass" in html

    results = client.get(job_url + "/results.csv")
    assert results.headers["content-type"].startswith("text/csv")
    assert "b.png,Fail" in results.text


def test_bad_csv_reshows_form_with_error(client):
    files = [
        ("applications_csv", ("apps.csv", b"name,brand\nx,y\n", "text/csv")),
        ("label_images", ("a.png", png_bytes(), "image/png")),
    ]
    response = client.post("/batch", files=files)
    assert response.status_code == 422
    assert "missing these columns" in response.text


def test_unknown_job_is_404(client):
    assert client.get("/batch/doesnotexist").status_code == 404


def test_template_download(client):
    response = client.get("/batch/template.csv")
    assert response.text.startswith("filename,brand_name")
