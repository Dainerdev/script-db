import pandas as pd

from gui.validation import EXPECTED_COLUMNS, validate, describe_missing
from src.text_keys import COLUMN_TYPES


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
    # Spec 002, RF-53: se suman las columnas estandarizadas que no estaban en RF-3.
    assert resultado.missing_columns == [
        "NOMBRES_APELLIDOS", "IDENTIFICACIÓN", "FECHA", "REPARTO",
        "CLASIFICACIÓN DEL RADICADO", "FUNCIONARIO A CARGO", "No",
        "TIPO DE EXPEDIENTE", "DELEGADA", "SALA", "SOLICITUD", "DECISIÓN", "PERTENECE",
    ]


def test_describe_missing_returns_one_description_per_column_in_order():
    descripciones = describe_missing(["FECHA", "No"])
    assert len(descripciones) == 2
    assert "FECHA" in descripciones[0]
    assert "radicados IUS duplicados" in descripciones[1]


# ---------------------------------------------------------------------
# Spec 002: columnas estandarizadas (RF-53, RF-54)
# ---------------------------------------------------------------------

def test_every_standardized_column_is_expected_and_described():
    for columna in COLUMN_TYPES:
        assert columna in EXPECTED_COLUMNS
        descripcion, = describe_missing([columna])
        assert "estandarizar" in descripcion


def test_missing_standardized_column_says_only_its_standardization_is_skipped():
    df = pd.DataFrame({col: [] for col in EXPECTED_COLUMNS if col != "SOLICITUD"})
    resultado = validate(df)

    assert resultado.missing_columns == ["SOLICITUD"]
    assert describe_missing(resultado.missing_columns) == ["no se estandarizará la columna SOLICITUD"]


def test_tipo_de_expediente_with_extra_header_text_is_recognized():
    for encabezado in ("TIPO DE EXPEDIENTE (ELECTRONICO - HIBRIDO)", "TIPO DE EXPEDIENTE\n(ELECTRONICO - HIBRIDO)"):
        columnas = [col if col != "TIPO DE EXPEDIENTE" else encabezado for col in EXPECTED_COLUMNS]
        resultado = validate(pd.DataFrame(columns=columnas))

        assert resultado.missing_columns == [], encabezado


def test_names_description_reflects_the_new_separation():
    descripcion, = describe_missing(["NOMBRES_APELLIDOS"])
    assert "separarán comparecientes" in descripcion
