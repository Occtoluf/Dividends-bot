from src.search.normalize import normalize, translit, variants


def test_normalize_strips_and_lowers():
    assert normalize("  Полюс  ") == "полюс"
    assert normalize("PLZL") == "plzl"


def test_normalize_collapses_non_alnum():
    assert normalize("MMK-ао") == "mmk ао"


def test_translit_ru_to_en():
    assert translit("полюс") == "polyus"
    assert translit("сбер") == "sber"


def test_variants_include_translit():
    vs = variants("Полюс")
    assert "полюс" in vs
    assert "polyus" in vs


def test_variants_of_latin_input_deduplicated():
    vs = variants("PLZL")
    assert vs == ["plzl"]
