"""Orchestration: read the label, compare each field, roll up one overall verdict."""

import time

from app.extraction import Extractor
from app.matching import compare_abv, compare_net_contents, compare_text
from app.models import ApplicationData, ExtractedLabel, FieldResult, Status, VerificationResult
from app.warning import check_government_warning

_SUMMARIES = {
    Status.PASS: "Everything we checked matches the application.",
    Status.FAIL: "One or more items do not match. See the red rows below.",
    Status.REVIEW: "Some items need a person to look. See the yellow rows below.",
}


def compare_fields(app_data: ApplicationData, label: ExtractedLabel) -> list[FieldResult]:
    results = [
        compare_text("Brand name", app_data.brand_name, label.brand_name),
        compare_text("Class / type", app_data.class_type, label.class_type),
        compare_abv(app_data.alcohol_content, label.alcohol_content),
        compare_net_contents(app_data.net_contents, label.net_contents),
    ]
    results.append(check_bottler(app_data.bottler_name_address, label.bottler_name_address))
    # Optional on the form: only checked when the applicant supplied it.
    if app_data.country_of_origin.strip():
        results.append(compare_text("Country of origin", app_data.country_of_origin, label.country_of_origin))
    # Mandatory on every label, checked against the legal text rather than the application.
    results.append(
        check_government_warning(
            label.government_warning_text,
            label.warning_header_appears_bold,
            label.warning_text_much_smaller,
        )
    )
    return results


def check_bottler(expected: str, found: str | None) -> FieldResult:
    """Every label must name its bottler/producer/importer, whether or not the agent typed one in."""
    field = "Bottler name and address"
    if expected.strip():
        return compare_text(field, expected, found)
    if not found:
        return FieldResult(
            field=field,
            status=Status.FAIL,
            expected="Required on every label",
            found=None,
            reason="The bottler or producer's name and address is required on the label but was not found.",
        )
    return FieldResult(
        field=field,
        status=Status.PASS,
        expected="Required on every label",
        found=found,
        reason="Present on the label. Not entered on the form, so not compared.",
    )


def overall_status(fields: list[FieldResult], image_legible: bool) -> Status:
    statuses = {f.status for f in fields}
    if Status.FAIL in statuses:
        return Status.FAIL
    if Status.REVIEW in statuses or not image_legible:
        return Status.REVIEW
    return Status.PASS


async def verify_label(
    app_data: ApplicationData,
    image_jpeg: bytes,
    extractor: Extractor,
    started: float | None = None,
) -> VerificationResult:
    """`started` lets the caller include upload handling in the reported time the agent sees."""
    started = started if started is not None else time.perf_counter()
    label = await extractor.extract(image_jpeg)
    fields = compare_fields(app_data, label)
    status = overall_status(fields, label.image_legible)

    summary = _SUMMARIES[status]
    if not label.image_legible:
        detail = f" {label.notes}" if label.notes else ""
        if status == Status.FAIL:
            summary += f" The picture was also hard to read, so confirm the red rows by eye.{detail}"
        else:
            summary = f"The picture is hard to read, so a person should check it.{detail}"

    return VerificationResult(
        status=status,
        fields=fields,
        summary=summary.strip(),
        elapsed_seconds=round(time.perf_counter() - started, 1),
    )
