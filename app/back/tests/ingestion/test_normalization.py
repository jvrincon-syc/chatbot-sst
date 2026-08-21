from ingestion.normalization.text import normalize_indexable_text, normalize_text
from ingestion.schemas.common import RemovedSpan


def test_normalization_preserves_dates_codes_percentages_and_identifiers() -> None:
    raw = "El formato FR-SST-01 vence el 23/10/2025 y aplica al 100% de CC 123456.\n"

    normalized = normalize_text(raw)

    assert "FR-SST-01" in normalized
    assert "23/10/2025" in normalized
    assert "100%" in normalized
    assert "123456" in normalized


def test_normalization_reconstructs_words_split_by_line_break() -> None:
    raw = "La preven-\ncion se documenta con espacios   duplicados."

    normalized = normalize_text(raw)

    assert "prevencion" in normalized
    assert "espacios duplicados" in normalized


def test_normalization_elimina_control_chars_y_colapsa_saltos_excesivos() -> None:
    raw = "Titulo\x00\t \n\n\nContenido\x1f final"

    normalized = normalize_text(raw)

    assert normalized == "Titulo\n\nContenido final"


def test_normalize_indexable_text_remueve_solo_la_primera_ocurrencia_del_span() -> None:
    text = "Encabezado repetido\nContenido util\nEncabezado repetido"

    normalized = normalize_indexable_text(
        text,
        removed_spans=[RemovedSpan(text="Encabezado repetido", reason="boilerplate")],
    )

    assert normalized == "Contenido util\nEncabezado repetido"
