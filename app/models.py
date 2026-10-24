"""Data shapes shared across the app: what the applicant claims, what the label shows, and the verdict."""

from enum import Enum

from pydantic import BaseModel, Field


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    REVIEW = "review"  # the tool is not confident; a human must look


class ApplicationData(BaseModel):
    """What the producer submitted on the COLA application."""

    brand_name: str
    class_type: str
    alcohol_content: str
    net_contents: str
    bottler_name_address: str = ""
    country_of_origin: str = ""


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
