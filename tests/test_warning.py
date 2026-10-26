from app.models import Status
from app.warning import REQUIRED_BODY, STANDARD_WARNING, check_government_warning


def test_exact_warning_with_bold_header_passes():
    assert check_government_warning(STANDARD_WARNING, header_bold=True).status == Status.PASS


def test_line_breaks_in_label_text_are_ignored():
    wrapped = STANDARD_WARNING.replace(" women", "\nwomen").replace(" (2)", "\n(2)")
    assert check_government_warning(wrapped, header_bold=True).status == Status.PASS


def test_missing_warning_fails():
    result = check_government_warning(None, header_bold=None)
    assert result.status == Status.FAIL
    assert "not found" in result.reason


def test_title_case_header_fails():
    # Jenny's example: 'Government Warning' instead of all caps is a rejection.
    result = check_government_warning(f"Government Warning: {REQUIRED_BODY}", header_bold=True)
    assert result.status == Status.FAIL
    assert "all capital letters" in result.reason


def test_non_bold_header_fails():
    result = check_government_warning(STANDARD_WARNING, header_bold=False)
    assert result.status == Status.FAIL
    assert "bold" in result.reason


def test_unknown_bold_needs_review_not_pass():
    result = check_government_warning(STANDARD_WARNING, header_bold=None)
    assert result.status == Status.REVIEW


def test_reworded_body_fails_and_names_the_change():
    reworded = STANDARD_WARNING.replace("may cause health problems", "can cause health issues")
    result = check_government_warning(reworded, header_bold=True)
    assert result.status == Status.FAIL
    assert '"can"' in result.reason and '"may"' in result.reason
    assert 'issues' in result.reason and 'problems' in result.reason  # every change, not just the first


def test_lowercased_body_word_fails():
    altered = STANDARD_WARNING.replace("Surgeon General", "surgeon general")
    assert check_government_warning(altered, header_bold=True).status == Status.FAIL


def test_missing_sentence_fails():
    truncated = STANDARD_WARNING.split(" (2)")[0]
    result = check_government_warning(truncated, header_bold=True)
    assert result.status == Status.FAIL
    assert "missing" in result.reason


def test_missing_header_fails():
    result = check_government_warning(REQUIRED_BODY, header_bold=None)
    assert result.status == Status.FAIL
    assert "must begin with" in result.reason


def test_multiple_problems_are_all_reported():
    result = check_government_warning(f"Government Warning: {REQUIRED_BODY}", header_bold=False)
    assert "capital" in result.reason and "bold" in result.reason
