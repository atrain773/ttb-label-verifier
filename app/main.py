"""FastAPI entry point: routes and app wiring only. Business logic lives in its own modules."""

import asyncio
import base64
import time
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import batch
from app.config import get_settings
from app.extraction import ExtractionError, Extractor, get_batch_extractor, get_extractor
from app.images import ImageError, prepare_image, read_upload
from app.models import ApplicationData, missing_fields_message
from app.verify import verify_label

BASE_DIR = Path(__file__).resolve().parent

# Interactive API docs are off: this is an agent-facing web app, not a public API.
app = FastAPI(title="TTB Label Verifier", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
# Changes on every deploy, so browsers fetch the new stylesheet instead of a cached old one.
templates.env.globals["asset_version"] = str(int(time.time()))

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # Inline scripts are small and our own; images include the inline preview of the uploaded label.
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; script-src 'self' 'unsafe-inline'; "
        "style-src 'self'; frame-ancestors 'none'; form-action 'self'"
    ),
}


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    return response


def _error_page(request: Request, status_code: int, message: str):
    return templates.TemplateResponse(
        request, "error.html", {"status_code": status_code, "message": message}, status_code=status_code
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_page(request: Request, exc: StarletteHTTPException):
    """Agents should see a readable page with a way back, never raw JSON."""
    message = exc.detail if exc.status_code == 404 and exc.detail != "Not Found" else None
    if message is None:
        message = "That page doesn't exist." if exc.status_code == 404 else "Something went wrong."
    return _error_page(request, exc.status_code, message)


@app.exception_handler(RequestValidationError)
async def request_error_page(request: Request, exc: RequestValidationError):
    return _error_page(request, 422, "Some required information was missing. Please go back and fill in every field.")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"form": {}, "error": None})


@app.post("/verify", response_class=HTMLResponse)
async def verify(
    request: Request,
    label_image: UploadFile,
    brand_name: str = Form(...),
    class_type: str = Form(...),
    alcohol_content: str = Form(...),
    net_contents: str = Form(...),
    bottler_name_address: str = Form(""),
    country_of_origin: str = Form(""),
    extractor: Extractor = Depends(get_extractor),
):
    form = {
        "brand_name": brand_name,
        "class_type": class_type,
        "alcohol_content": alcohol_content,
        "net_contents": net_contents,
        "bottler_name_address": bottler_name_address,
        "country_of_origin": country_of_origin,
    }

    def form_error(message: str):
        # Re-show the form with the agent's typing preserved, so they only fix what's wrong.
        return templates.TemplateResponse(request, "index.html", {"form": form, "error": message}, status_code=422)

    try:
        app_data = ApplicationData(**form)
    except ValidationError as exc:
        return form_error(missing_fields_message(exc))

    started = time.perf_counter()
    try:
        # Resizing is CPU work; run it off the event loop so other agents' requests keep moving.
        image_jpeg = await run_in_threadpool(prepare_image, await read_upload(label_image))
        result = await verify_label(app_data, image_jpeg, extractor, started=started)
    except (ImageError, ExtractionError) as exc:
        return form_error(str(exc))

    # The image is shown back inline and never written to disk (prototype: no data retention).
    image_data_url = "data:image/jpeg;base64," + base64.b64encode(image_jpeg).decode("ascii")
    return templates.TemplateResponse(
        request,
        "result.html",
        {"result": result, "image_data_url": image_data_url, "filename": label_image.filename},
    )


@app.get("/batch", response_class=HTMLResponse)
def batch_form(request: Request):
    return templates.TemplateResponse(request, "batch.html", {"error": None, "max_files": batch.MAX_BATCH_FILES})


@app.get("/batch/template.csv")
def batch_template():
    return Response(
        batch.TEMPLATE_CSV,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="batch_template.csv"'},
    )


@app.post("/batch", response_class=HTMLResponse)
async def batch_start(
    request: Request,
    applications_csv: UploadFile,
    label_images: list[UploadFile] = File(...),
    extractor: Extractor = Depends(get_batch_extractor),
):
    def form_error(message: str):
        return templates.TemplateResponse(
            request,
            "batch.html",
            {"error": message, "max_files": batch.MAX_BATCH_FILES},
            status_code=422,
        )

    images = [f for f in label_images if f.filename]
    if not images:
        return form_error("No label pictures were chosen.")
    if len(images) > batch.MAX_BATCH_FILES:
        return form_error(f"Please upload at most {batch.MAX_BATCH_FILES} pictures at a time.")

    try:
        applications = batch.parse_applications(await applications_csv.read())
    except batch.BatchInputError as exc:
        return form_error(str(exc))

    # Shrink each image as it arrives so a few hundred phone photos never sit in memory at full size.
    prepared: dict[str, bytes | str] = {}
    for upload in images:
        if upload.filename in prepared:
            # Two pictures with one name can't both match a CSV row; flag it rather than silently keep one.
            prepared[upload.filename] = "Two pictures share this filename. Rename one and check it separately."
            continue
        try:
            prepared[upload.filename] = await run_in_threadpool(prepare_image, await read_upload(upload))
        except ImageError as exc:
            prepared[upload.filename] = str(exc)

    job = batch.create_job(batch.build_rows(applications, prepared))
    job.task = asyncio.create_task(batch.run_job(job, extractor, get_settings().batch_concurrency))
    return RedirectResponse(f"/batch/{job.id}", status_code=303)


def _get_job_or_404(job_id: str) -> batch.BatchJob:
    job = batch.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="This batch was not found. Results are kept for 2 hours.")
    return job


@app.get("/batch/{job_id}", response_class=HTMLResponse)
def batch_status(request: Request, job_id: str):
    return templates.TemplateResponse(request, "batch_job.html", {"job": _get_job_or_404(job_id)})


@app.get("/batch/{job_id}/table", response_class=HTMLResponse)
def batch_table(request: Request, job_id: str):
    """Fragment the results page polls to update in place."""
    return templates.TemplateResponse(request, "_batch_table.html", {"job": _get_job_or_404(job_id)})


@app.get("/batch/{job_id}/results.csv")
def batch_results_csv(job_id: str):
    job = _get_job_or_404(job_id)
    return PlainTextResponse(
        batch.results_csv(job),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="label_results_{job_id}.csv"'},
    )


@app.get("/healthz")
def healthz():
    """Liveness check used by Render (and any future load balancer)."""
    return {"status": "ok"}
