"""Keyword matching engine tests: word boundaries, accents, case, ES+EN."""

from app.ingest.matching import find_matching_keyword, fold_text, matches_keyword


class TestFoldText:
    def test_strips_accents_and_casefolds(self) -> None:
        assert fold_text("Tecnología BÜAP") == "tecnologia buap"

    def test_english_unchanged(self) -> None:
        assert fold_text("Brand-Cool") == "brand-cool"


class TestMatchesKeyword:
    def test_exact_word(self) -> None:
        assert matches_keyword("La BUAP anunció", "BUAP")

    def test_case_insensitive(self) -> None:
        assert matches_keyword("buap publicó resultados", "BUAP")

    def test_accent_insensitive(self) -> None:
        # keyword with accent, text without (and vice versa)
        assert matches_keyword("Tecnologico de Monterrey gala", "Tecnológico")
        assert matches_keyword("Tecnológico gala", "tecnologico")

    def test_word_boundary_no_substring(self) -> None:
        assert not matches_keyword("BUAPatito es un proyecto", "BUAP")
        assert not matches_keyword("foxxo no es la tienda", "oxxo")

    def test_word_boundary_after_punctuation(self) -> None:
        assert matches_keyword("gana BUAP, el concurso", "BUAP")

    def test_multi_word_keyword(self) -> None:
        assert matches_keyword("La Benemérita Universidad Autónoma de Puebla gana", "benemérita universidad")
        # internal whitespace run differs
        assert matches_keyword("la BENEMÉRITA    UNIVERSIDAD gana", "benemérita universidad")

    def test_multi_word_keyword_must_be_contiguous(self) -> None:
        assert not matches_keyword("benemérita gran universidad", "benemérita universidad")

    def test_english_keyword(self) -> None:
        assert matches_keyword("ACME Corp releases new product", "acme corp")

    def test_blank_never_matches(self) -> None:
        assert not matches_keyword("anything at all", "   ")
        assert not matches_keyword("", "BUAP")


class TestFindMatchingKeyword:
    def test_returns_first_match_in_order(self) -> None:
        text = "BUAP y OXXO firman convenio"
        assert find_matching_keyword(text, ["oxxo", "buap"]) == "oxxo"

    def test_returns_none_when_no_match(self) -> None:
        assert find_matching_keyword("no brands here", ["buap", "oxxo"]) is None

    def test_checks_all_keywords(self) -> None:
        assert find_matching_keyword("me encanta OXXO", ["buap", "oxxo"]) == "oxxo"
