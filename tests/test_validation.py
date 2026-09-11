import pandas as pd

from gui.validation import EXPECTED_COLUMNS, validate, describe_missing


def test_validate_none_df_is_blocking():
    resultado = validate(None)
    assert resultado.sheet_ok is False
    assert resultado.can_continue is False
    assert resultado.missing_columns == []


def test_validate_sheet_with_no_columns_is_blocking():
    df = pd.DataFrame()
    resultado = validate(df)
    assert resultado.sheet_ok is False
    assert resultado.can_continue is False


def test_validate_complete_file_has_no_missing_columns():
    df = pd.DataFrame({col: [] for col in EXPECTED_COLUMNS})
    resultado = validate(df)
    assert resultado.sheet_ok is True
    assert resultado.can_continue is True
    assert resultado.missing_columns == []


def test_validate_zero_data_rows_with_headers_is_accepted():
    # Caso límite de spec.md: encabezados válidos + 0 filas de datos -> se acepta.
    df = pd.DataFrame(columns=EXPECTED_COLUMNS)
    resultado = validate(df)
    assert resultado.sheet_ok is True


def test_validate_missing_some_columns_lists_them_in_expected_order():
    df = pd.DataFrame({"RADICADO IUS": [], "MAGISTRADO": []})
    resultado = validate(df)
    assert resultado.sheet_ok is True
    assert resultado.can_continue is True
    assert resultado.missing_columns == [
        "NOMBRES_APELLIDOS", "IDENTIFICACIÓN", "FECHA", "REPARTO",
        "CLASIFICACIÓN DEL RADICADO", "FUNCIONARIO A CARGO", "No",
    ]


def test_describe_missing_returns_one_description_per_column_in_order():
    descripciones = describe_missing(["FECHA", "No"])
    assert len(descripciones) == 2
    assert "FECHA" in descripciones[0]
    assert "radicados IUS duplicados" in descripciones[1]
