from services.screenshot_service import _fuzzy_match_score, _normalize_text


def test_normalize_text_collapses_spacing_and_case():
    assert _normalize_text("  Hello   WORLD \n") == "hello world"


def test_fuzzy_match_score_prefers_related_text():
    related = _fuzzy_match_score("Install dependencies with pip", "pip install dependencies")
    unrelated = _fuzzy_match_score("Install dependencies with pip", "sunset beach travel vlog")
    assert related > unrelated
