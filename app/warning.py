"""Government Health Warning check (27 CFR part 16).

Unlike other fields, the warning is checked against fixed legal text, not the
application, and it must be exact: 'GOVERNMENT WARNING:' in capital letters and
bold, followed by the statutory wording.
"""

from difflib import SequenceMatcher

from app.models import FieldResult, Status

REQUIRED_HEADER = "GOVERNMENT WARNING:"
REQUIRED_BODY = (
    "(1) According to the Surgeon General, women should not drink alcoholic beverages during "
    "pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs "
    "your ability to drive a car or operate machinery, and may cause health problems."
)
STANDARD_WARNING = f"{REQUIRED_HEADER} {REQUIRED_BODY}"

FIELD = "Government warning"
# Shown in the "Application" column; the full legal text would swamp the results table.
EXPECTED_LABEL = "Standard federal wording (27 CFR 16.21), header in bold capitals"


def _collapse(text: str) -> str:
    return " ".join(text.split())


MAX_DIFFERENCES_LISTED = 3


def describe_difference(expected: str, found: str) -> str:
    """List the wording differences in words an agent can act on (or paste into a rejection)."""
    exp_words, found_words = expected.split(), found.split()
    changes = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, exp_words, found_words, autojunk=False).get_opcodes():
        required = " ".join(exp_words[i1:i2])
        printed = " ".join(found_words[j1:j2])
        if tag == "replace":
            changes.append(f'Label says "{printed}" where the law requires "{required}".')
        elif tag == "delete":
            changes.append(f'Label is missing "{required}".')
        elif tag == "insert":
            changes.append(f'Label adds "{printed}", which is not in the required text.')
    if not changes:
        return "Wording differs from the required text."
    extra = len(changes) - MAX_DIFFERENCES_LISTED
    listed = " ".join(changes[:MAX_DIFFERENCES_LISTED])
    return listed + (f" ({extra} more difference{'s' if extra > 1 else ''}.)" if extra > 0 else "")


def check_government_warning(
    text: str | None,
    header_bold: bool | None,
    much_smaller: bool | None = None,
) -> FieldResult:
    if not text:
        return FieldResult(
            field=FIELD,
            status=Status.FAIL,
            expected=EXPECTED_LABEL,
            found=None,
            reason="Government warning not found on the label.",
        )

    found = _collapse(text)
    problems: list[str] = []
    needs_review: list[str] = []

    # Header: exact capitals. 'Government Warning:' is a rejection, not a style choice.
    if not found.startswith(REQUIRED_HEADER):
        if found.upper().startswith(REQUIRED_HEADER):
            problems.append('"GOVERNMENT WARNING:" must be in all capital letters.')
        else:
            problems.append('The warning must begin with "GOVERNMENT WARNING:".')

    # Body: word-for-word. Compare case-sensitively; only whitespace is forgiven.
    header_len = len(REQUIRED_HEADER)
    body = found[header_len:].strip() if found.upper().startswith(REQUIRED_HEADER) else found
    if body != REQUIRED_BODY:
        problems.append(describe_difference(REQUIRED_BODY, body))

    # Bold: the reader may be unsure; unsure means a person checks, never an automatic pass.
    if header_bold is False:
        problems.append('"GOVERNMENT WARNING:" must be in bold type.')
    elif header_bold is None:
        needs_review.append('Could not confirm that "GOVERNMENT WARNING:" is bold. Please check by eye.')

    # Type size: millimetres can't be measured reliably from a photo, so a warning that looks
    # much smaller than the rest of the label goes to a person rather than passing or failing.
    if much_smaller:
        needs_review.append(
            "The warning text looks much smaller than the rest of the label. "
            "Check it meets the minimum type size for this container (27 CFR 16.22)."
        )

    if problems:
        status, reasons = Status.FAIL, problems + needs_review
    elif needs_review:
        status, reasons = Status.REVIEW, needs_review
    else:
        status, reasons = Status.PASS, ["Exact required wording, capitals, and bold header."]

    return FieldResult(field=FIELD, status=status, expected=EXPECTED_LABEL, found=text, reason=" ".join(reasons))
