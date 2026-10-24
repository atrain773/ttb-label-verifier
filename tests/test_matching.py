import pytest

from app.matching import compare_abv, compare_net_contents, compare_text, parse_abv, parse_volume_ml
from app.models import Status


class TestCompareText:
    def test_exact_match_passes(self):
        assert compare_text("Brand name", "OLD TOM DISTILLERY", "OLD TOM DISTILLERY").status == Status.PASS

    def test_case_and_apostrophe_differences_pass(self):
        # Dave's example: obviously the same brand.
        result = compare_text("Brand name", "Stone's Throw", "STONE’S THROW")
        assert result.status == Status.PASS
        assert "capitalization" in result.reason

    def test_near_miss_goes_to_review(self):
        assert compare_text("Brand name", "Old Tom Distillery", "Old Tom Distilery").status == Status.REVIEW

    def test_substring_goes_to_review(self):
        assert compare_text("Brand name", "Old Tom", "Old Tom Distillery").status == Status.REVIEW

    def test_different_brand_fails(self):
        assert compare_text("Brand name", "Old Tom Distillery", "Blue Ridge Spirits").status == Status.FAIL

    def test_missing_on_label_fails(self):
        result = compare_text("Brand name", "Old Tom Distillery", None)
        assert result.status == Status.FAIL
        assert result.reason == "Not found on the label."


class TestAbv:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("45% Alc./Vol. (90 Proof)", (45.0, 90.0)),
            ("40% ABV", (40.0, None)),
            ("45", (45.0, None)),
            ("90 Proof", (45.0, 90.0)),
            ("12.5% alc/vol", (12.5, None)),
        ],
    )
    def test_parse(self, text, expected):
        assert parse_abv(text) == expected

    def test_same_abv_different_format_passes(self):
        assert compare_abv("45%", "45% Alc./Vol. (90 Proof)").status == Status.PASS

    def test_wrong_abv_fails(self):
        result = compare_abv("45% Alc./Vol.", "40% Alc./Vol.")
        assert result.status == Status.FAIL
        assert "40%" in result.reason

    def test_inconsistent_proof_fails(self):
        result = compare_abv("45%", "45% Alc./Vol. (80 Proof)")
        assert result.status == Status.FAIL
        assert "proof" in result.reason.lower()

    def test_unreadable_goes_to_review(self):
        assert compare_abv("45%", "forty-five percent").status == Status.REVIEW


class TestNetContents:
    @pytest.mark.parametrize(
        "text, ml",
        [("750 mL", 750), ("750ml", 750), ("75 cl", 750), ("1.75 L", 1750), ("1 Liter", 1000), ("750 ML.", 750)],
    )
    def test_parse(self, text, ml):
        assert parse_volume_ml(text) == pytest.approx(ml)

    def test_fluid_ounces(self):
        assert parse_volume_ml("25.4 fl. oz.") == pytest.approx(751.2, rel=0.001)

    def test_unit_conversion_passes(self):
        assert compare_net_contents("750 mL", "75 cL").status == Status.PASS
        assert compare_net_contents("750 mL", "25.4 FL OZ").status == Status.PASS

    def test_different_volume_fails(self):
        assert compare_net_contents("750 mL", "700 mL").status == Status.FAIL

    def test_missing_fails(self):
        assert compare_net_contents("750 mL", None).status == Status.FAIL
