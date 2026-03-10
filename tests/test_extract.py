from app.text_utils import build_summary, extract_methods, normalize_abstract, sanitize_filename


def test_normalize_abstract_removes_html():
    raw = "<jats:p>We propose a method.</jats:p>"
    assert normalize_abstract(raw) == "We propose a method."


def test_extract_methods_filters_key_sentences():
    text = "We propose a lightweight framework for ranking. Results are strong. The method uses benchmark datasets."
    methods = extract_methods(text)
    assert len(methods) == 2
    assert "framework" in methods[0].lower()


def test_build_summary_contains_overview_and_method():
    summary = build_summary("This work studies classification.", ["We propose a new approach."])
    assert "研究概览" in summary
    assert "方法要点" in summary


def test_sanitize_filename_removes_invalid_chars():
    assert sanitize_filename('a:b/c*?"d') == "a_b_c_d"
