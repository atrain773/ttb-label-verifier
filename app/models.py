"""Data shapes shared across the app: what the applicant claims, what the label shows, and the verdict."""

from enum import Enum

from pydantic import BaseModel, Field, ValidationError, field_validator


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    REVIEW = "review"  # the tool is not confident; a human must look


REQUIRED_FIELD_NAMES = {
    "brand_name": "Brand name",
    "class_type": "Class / type",
    "alcohol_content": "Alcohol content",
    "net_contents": "Net contents",
}


class ApplicationData(BaseModel):
    """What the producer submitted on the COLA application."""

    brand_name: str
    class_type: str
    alcohol_content: str
    net_contents: str
    bottler_name_address: str = ""
    country_of_origin: str = ""

    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator(*REQUIRED_FIELD_NAMES)
    @classmethod
    def _must_have_content(cls, value: str) -> str:
        # Blank or punctuation-only input can't be compared to anything meaningful.
        if not any(ch.isalnum() for ch in value):
            raise ValueError("must contain letters or numbers")
        return value


def missing_fields_message(error: ValidationError) -> str:
    """Turn a validation error into a sentence naming the form fields to fix."""
    names = [REQUIRED_FIELD_NAMES.get(str(e["loc"][0]), str(e["loc"][0])) for e in error.errors() if e["loc"]]
    return "Please fill in: " + ", ".join(dict.fromkeys(names)) + "."


class ExtractedLabel(BaseModel):
    """What the vision model read off the label image. None means 'not found on the label'."""

    image_legible: bool = Field(
        description="False if glare, blur, angle, or resolution prevents reading the label reliably."
    )
    brand_name: str | None = None
    class_type: str | None = None
    alcohol_content: str | None = None
    net_contents: str | None = None
    bottler_name_address: str | None = None
    country_of_origin: str | None = None
    government_warning_text: str | None = Field(
        default=None,
        description="Full warning statement transcribed exactly, preserving capitalization and punctuation.",
    )
    warning_header_appears_bold: bool | None = Field(
        default=None,
        description="Whether the words 'GOVERNMENT WARNING:' appear in bold type. None if unsure.",
    )
    notes: str | None = Field(
        default=None,
        description="Short note about anything that made the label hard to read.",
    )


class FieldResult(BaseModel):
    field: str  # human-readable name, e.g. "Brand name"
    status: Status
    expected: str | None
    found: str | None
    reason: str  # plain-English explanation an agent (or the applicant) can act on


class VerificationResult(BaseModel):
    status: Status
    fields: list[FieldResult]
    summary: str
    elapsed_seconds: float
