"""FastAPI entry point: routes and app wiring only. Business logic lives in its own modules."""

import base64
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.extraction import ExtractionError, Extractor, get_extractor
from app.images import ImageError, prepare_image
from app.models import ApplicationData
from app.verify import verify_label

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="TTB Label Verifier")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


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
    app_data = ApplicationData(
        brand_name=brand_name,
        class_type=class_type,
        alcohol_content=alcohol_content,
        net_contents=net_contents,
        bottler_name_address=bottler_name_address,
        country_of_origin=country_of_origin,
    )

    started = time.perf_counter()
    try:
        image_jpeg = prepare_image(await label_image.read())
        result = await verify_label(app_data, image_jpeg, extractor, started=started)
    except (ImageError, ExtractionError) as exc:
        # Re-show the form with the agent's typing preserved, so they only fix what's wrong.
        return templates.TemplateResponse(
            request,
            "index.html",
            {"form": app_data.model_dump(), "error": str(exc)},
            status_code=422,
        )

    # The image is shown back inline and never written to disk (prototype: no data retention).
    image_data_url = "data:image/jpeg;base64," + base64.b64encode(image_jpeg).decode("ascii")
    return templates.TemplateResponse(
        request,
        "result.html",
        {"result": result, "image_data_url": image_data_url, "filename": label_image.filename},
    )


@app.get("/healthz")
def healthz():
    """Liveness check used by Render (and any future load balancer)."""
    return {"status": "ok"}
