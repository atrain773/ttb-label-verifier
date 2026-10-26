"""End-to-end route tests with a fake extractor, so they run offline and free."""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.extraction import ExtractionError, UnconfiguredExtractor, get_extractor
from app.main import app
from app.models import ExtractedLabel
from app.warning import STANDARD_WARNING

GOOD_LABEL = ExtractedLabel(
    image_legible=True,
    brand_name="OLD TOM DISTILLERY",
    class_type="Kentucky Straight Bourbon Whiskey",
    alcohol_content="45% Alc./Vol. (90 Proof)",
    net_contents="750 mL",
    government_warning_text=STANDARD_WARNING,
    warning_header_appears_bold=True,
)

FORM = {
    "brand_name": "Old Tom Distillery",
    "class_type": "Kentucky Straight Bourbon Whiskey",
    "alcohol_content": "45%",
    "net_contents": "750 mL",
}


class FakeExtractor:
    def __init__(self, label: ExtractedLabel | None = None, error: str | None = None):
        self.label, self.error = label, error

    async def extract(self, image_jpeg: bytes) -> ExtractedLabel:
        if self.error:
            raise ExtractionError(self.error)
        return self.label


def png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


def use_extractor(extractor):
    app.dependency_overrides[get_extractor] = lambda: extractor


def post(client, form=FORM, image=None):
    files = {"label_image": ("label.png", image if image is not None else png_bytes(), "image/png")}
    return client.post("/verify", data=form, files=files)


def test_matching_label_passes(client):
    use_extractor(FakeExtractor(GOOD_LABEL))
    response = post(client)
    assert response.status_code == 200
    assert "<h1>Pass</h1>" in response.text


def test_wrong_abv_fails(client):
    use_extractor(FakeExtractor(GOOD_LABEL.model_copy(update={"alcohol_content": "40% Alc./Vol."})))
    response = post(client)
    assert "<h1>Fail</h1>" in response.text
    assert "Label says 40%" in response.text


def test_title_case_warning_fails_whole_label(client):
    bad = STANDARD_WARNING.replace("GOVERNMENT WARNING:", "Government Warning:")
    use_extractor(FakeExtractor(GOOD_LABEL.model_copy(update={"government_warning_text": bad})))
    response = post(client)
    assert "<h1>Fail</h1>" in response.text
    assert "all capital letters" in response.text


def test_illegible_image_needs_review(client):
    use_extractor(FakeExtractor(GOOD_LABEL.model_copy(update={"image_legible": False, "notes": "Heavy glare."})))
    response = post(client)
    assert "<h1>Needs review</h1>" in response.text
    assert "Heavy glare." in response.text


def test_non_image_upload_shows_friendly_error_and_keeps_input(client):
    use_extractor(FakeExtractor(GOOD_LABEL))
    response = post(client, image=b"not an image")
    assert response.status_code == 422
    assert "not a picture we can open" in response.text
    assert 'value="Old Tom Distillery"' in response.text


def test_missing_api_key_shows_friendly_error(client):
    use_extractor(UnconfiguredExtractor())
    response = post(client)
    assert response.status_code == 422
    assert "not configured" in response.text


def test_extraction_failure_shows_friendly_error(client):
    use_extractor(FakeExtractor(error="Reading the label took too long. Please try again."))
    response = post(client)
    assert response.status_code == 422
    assert "took too long" in response.text
