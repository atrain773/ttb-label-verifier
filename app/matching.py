"""Deterministic field comparison rules.

The vision model only *reads* the label. Every pass/fail decision is made here,
in plain code, so results are fast, repeatable, testable, and explainable.

Guiding principle: a wrong approval is worse than a wrong rejection, so anything
short of a confident match becomes FAIL or REVIEW, never PASS.
"""

import re
import unicodedata
from difflib import SequenceMatcher

from app.models import FieldResult, Status

# Close-but-not-equal text at or above this similarity goes to a human instead of failing outright.
REVIEW_SIMILARITY = 0.85

_QUOTE_MAP = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "`": "'"})


def normalize_text(value: str) -> str:
    """Fold case, quotes, punctuation, and whitespace so 'STONE'S THROW' == 'Stone's Throw'."""
    value = unicodedata.normalize("NFKC", value).translate(_QUOTE_MAP).casefold()
    value = re.sub(r"[^\w\s]", " ", value)
    return " ".join(value.split())


def _not_found(field: str, expected: str) -> FieldResult:
    return FieldResult(
        field=field,
        status=Status.FAIL,
        expected=expected,
        found=None,
        reason="Not found on the label.",
    )


def compare_text(field: str, expected: str, found: str | None) -> FieldResult:
    """Text fields (brand, class/type, bottler, country): tolerant of case and punctuation only."""
    if not found:
        return _not_found(field, expected)

    if expected.strip() == found.strip():
        return FieldResult(field=field, status=Status.PASS, expected=expected, found=found, reason="Exact match.")

    norm_expected, norm_found = normalize_text(expected), normalize_text(found)
    if norm_expected == norm_found:
        return FieldResult(
            field=field,
            status=Status.PASS,
            expected=expected,
            found=found,
            reason="Matches. Differs only in capitalization or punctuation.",
        )

    similarity = SequenceMatcher(None, norm_expected, norm_found).ratio()
    if similarity >= REVIEW_SIMILARITY or norm_expected in norm_found or norm_found in norm_expected:
        return FieldResult(
            field=field,
            status=Status.REVIEW,
            expected=expected,
            found=found,
            reason="Close but not identical. Please compare by eye.",
        )

    return FieldResult(
        field=field,
        status=Status.FAIL,
        expected=expected,
        found=found,
        reason="Does not match the application.",
    )


# --- Alcohol content -------------------------------------------------------

_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_PROOF_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:°\s*)?proof", re.IGNORECASE)
_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")


def parse_abv(value: str) -> tuple[float | None, float | None]:
    """Return (abv_percent, proof) from strings like '45% Alc./Vol. (90 Proof)'."""
    percent = _PERCENT_RE.search(value)
    proof = _PROOF_RE.search(value)
    abv = float(percent.group(1)) if percent else None
    proof_value = float(proof.group(1)) if proof else None
    if abv is None and proof_value is None:
        # Bare number typed into the application form, e.g. "45".
        bare = _NUMBER_RE.search(value)
        abv = float(bare.group(1)) if bare else None
    if abv is None and proof_value is not None:
        abv = proof_value / 2
    return abv, proof_value


def compare_abv(expected: str, found: str | None) -> FieldResult:
    field = "Alcohol content"
    if not found:
        return _not_found(field, expected)

    expected_abv, _ = parse_abv(expected)
    found_abv, found_proof = parse_abv(found)

    if expected_abv is None or found_abv is None:
        return FieldResult(
            field=field,
            status=Status.REVIEW,
            expected=expected,
            found=found,
            reason="Could not read a number from the alcohol content. Please check by eye.",
        )

    if found_proof is not None and abs(found_proof - 2 * found_abv) > 0.1:
        return FieldResult(
            field=field,
            status=Status.FAIL,
            expected=expected,
            found=found,
            reason=f"Label proof ({found_proof:g}) is not twice the ABV ({found_abv:g}%).",
        )

    if abs(expected_abv - found_abv) < 0.01:
        return FieldResult(field=field, status=Status.PASS, expected=expected, found=found, reason="ABV matches.")

    return FieldResult(
        field=field,
        status=Status.FAIL,
        expected=expected,
        found=found,
        reason=f"Label says {found_abv:g}% but the application says {expected_abv:g}%.",
    )


# --- Net contents ----------------------------------------------------------

_ML_PER_UNIT = {
    "ml": 1.0,
    "cl": 10.0,
    "l": 1000.0,
    "floz": 29.5735,
}
_UNIT_ALIASES = {
    "ml": "ml", "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml",
    "cl": "cl", "centiliter": "cl", "centiliters": "cl",
    "l": "l", "liter": "l", "liters": "l", "litre": "l", "litres": "l", "ltr": "l",
    "floz": "floz", "fluidounce": "floz", "fluidounces": "floz", "oz": "floz",
}
_VOLUME_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*([a-z][a-z.\s]*)", re.IGNORECASE)

# Relative tolerance for unit conversions (e.g. 25.4 fl oz vs 750 mL is ~0.2% apart).
VOLUME_TOLERANCE = 0.005


def parse_volume_ml(value: str) -> float | None:
    """Convert '750 mL', '75 cl', '1.75 L', '25.4 fl. oz.' to millilitres."""
    for number, unit_text in _VOLUME_RE.findall(value):
        unit_key = re.sub(r"[.\s]", "", unit_text.lower())
        # Take the longest alias the unit text starts with ("fl oz" before "l").
        for alias in sorted(_UNIT_ALIASES, key=len, reverse=True):
            if unit_key.startswith(alias):
                return float(number.replace(",", ".")) * _ML_PER_UNIT[_UNIT_ALIASES[alias]]
    return None


def compare_net_contents(expected: str, found: str | None) -> FieldResult:
    field = "Net contents"
    if not found:
        return _not_found(field, expected)

    expected_ml, found_ml = parse_volume_ml(expected), parse_volume_ml(found)
    if expected_ml is None or found_ml is None:
        return FieldResult(
            field=field,
            status=Status.REVIEW,
            expected=expected,
            found=found,
            reason="Could not read a volume and unit. Please check by eye.",
        )

    if abs(expected_ml - found_ml) <= VOLUME_TOLERANCE * expected_ml:
        return FieldResult(field=field, status=Status.PASS, expected=expected, found=found, reason="Volume matches.")

    return FieldResult(
        field=field,
        status=Status.FAIL,
        expected=expected,
        found=found,
        reason=f"Label volume ({found_ml:g} mL) differs from the application ({expected_ml:g} mL).",
    )
