from app.models import Status
from app.verify import check_bottler


def test_missing_bottler_fails_even_when_not_entered_on_form():
    result = check_bottler("", None)
    assert result.status == Status.FAIL
    assert "required on the label" in result.reason


def test_present_bottler_passes_when_not_entered():
    result = check_bottler("", "Bottled by Old Tom Distillery, Bardstown, KY")
    assert result.status == Status.PASS
    assert "not compared" in result.reason


def test_entered_bottler_is_compared():
    assert check_bottler("Old Tom Distillery, Bardstown, KY", "OLD TOM DISTILLERY, BARDSTOWN, KY").status == Status.PASS
    assert check_bottler("Old Tom Distillery, Bardstown, KY", None).status == Status.FAIL
