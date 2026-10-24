"""Label reading: turn a label image into structured fields.

The Extractor protocol keeps the vision provider swappable. Today it is Claude
via the Anthropic API; in a firewalled federal network it could be Azure-hosted
or a local OCR model without touching the matching logic.
"""

import base64
from typing import Protocol

import anthropic

from app.config import get_settings
from app.models import ExtractedLabel

EXTRACTION_PROMPT = """You are reading an alcohol beverage label for a TTB compliance check.

Transcribe each field EXACTLY as printed on the label: keep the original capitalization,
punctuation, and spelling. Do not correct, normalize, or guess. If a field is not on the
label, return null for it.

Fields:
- brand_name: the brand name.
- class_type: the class/type designation (e.g. "Kentucky Straight Bourbon Whiskey").
- alcohol_content: the full alcohol statement (e.g. "45% Alc./Vol. (90 Proof)").
- net_contents: the volume statement (e.g. "750 mL").
- bottler_name_address: the bottler/producer/importer name and address line.
- country_of_origin: the country of origin statement, if any.
- government_warning_text: the entire health warning statement, word for word, with its
  exact capitalization (e.g. whether it starts "GOVERNMENT WARNING:" or "Government Warning:").
- warning_header_appears_bold: whether the "GOVERNMENT WARNING:" words are in bold type
  (null if you cannot tell).
- image_legible: false if glare, blur, angle, or low resolution stops you from reading
  the label reliably.
- notes: briefly describe any part you could not read clearly."""


class ExtractionError(RuntimeError):
    """Raised with a message that is safe to show the user."""


class Extractor(Protocol):
    async def extract(self, image_jpeg: bytes) -> ExtractedLabel: ...


class ClaudeExtractor:
    def __init__(self, client: anthropic.AsyncAnthropic, model: str, effort: str):
        self._client = client
        self._model = model
        self._effort = effort

    async def extract(self, image_jpeg: bytes) -> ExtractedLabel:
        image_b64 = base64.standard_b64encode(image_jpeg).decode("ascii")
        try:
            response = await self._client.messages.parse(
                model=self._model,
                max_tokens=4000,
                output_config={"effort": self._effort},
                output_format=ExtractedLabel,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64},
                            },
                            {"type": "text", "text": EXTRACTION_PROMPT},
                        ],
                    }
                ],
            )
        except anthropic.APITimeoutError:
            raise ExtractionError("Reading the label took too long. Please try again.")
        except anthropic.RateLimitError:
            raise ExtractionError("The label reader is busy right now. Please wait a moment and try again.")
        except anthropic.AuthenticationError:
            raise ExtractionError("The label reader is not configured (missing or invalid API key).")
        except anthropic.APIConnectionError:
            raise ExtractionError("Could not reach the label reader. Check the network connection.")
        except anthropic.APIStatusError:
            raise ExtractionError("The label reader had a problem. Please try again.")

        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise ExtractionError("The label could not be read automatically. Please review it by eye.")
        return response.parsed_output


class UnconfiguredExtractor:
    """Stands in when no API key is set, so the app explains the problem instead of crashing."""

    async def extract(self, image_jpeg: bytes) -> ExtractedLabel:
        raise ExtractionError("The label reader is not configured (no API key set). Contact your administrator.")


_extractor: Extractor | None = None


def get_extractor() -> Extractor:
    """FastAPI dependency. One shared client so connections are reused across requests."""
    global _extractor
    if _extractor is None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            return UnconfiguredExtractor()  # not cached: picks up the key once it is set
        client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.extraction_timeout_seconds,
            max_retries=1,
        )
        _extractor = ClaudeExtractor(client, settings.extraction_model, settings.extraction_effort)
    return _extractor
