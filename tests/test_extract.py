from app.text_utils import extract_methods, normalize_abstract


def test_normalize_abstract_removes_html():
    raw = "<jats:p>We propose a method.</jats:p>"
    assert normalize_abstract(raw) == "We propose a method."


def test_extract_methods_filters_key_sentences():
    text = "We propose a lightweight framework for ranking. Results are strong. The method uses benchmark datasets."
    methods = extract_methods(text)
    assert len(methods) == 2
    assert "framework" in methods[0].lower()
