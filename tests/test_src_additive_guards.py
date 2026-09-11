import pandas as pd
import pytest

from src.reading import read_excel_file
from src.standardization import split_multiple_comparecientes, add_radicado_ius_revisada
from src.diagnostic import split_by_status, run_similarity_report
from src.exportation import export_multi_sheet_excel, ExportCancelled


# ---------------------------------------------------------------------
# read_excel_file: raise_errors
# ---------------------------------------------------------------------

def test_read_excel_file_missing_file_default_returns_none():
    assert read_excel_file("archivo_que_no_existe_12345.xlsx") is None


def test_read_excel_file_missing_file_raise_errors_propagates():
    with pytest.raises(Exception):
        read_excel_file("archivo_que_no_existe_12345.xlsx", raise_errors=True)


# ---------------------------------------------------------------------
# split_multiple_comparecientes: guarda de columnas ausentes
# ---------------------------------------------------------------------

def test_split_multiple_comparecientes_missing_columns_returns_df_unchanged():
    df = pd.DataFrame({"OTRA_COLUMNA": ["x", "y"]})
    resultado = split_multiple_comparecientes(df, name_col="NOMBRES_APELLIDOS", id_col="IDENTIFICACIÓN")
    pd.testing.assert_frame_equal(resultado, df)


def test_split_multiple_comparecientes_present_columns_regression():
    df = pd.DataFrame({
        "NOMBRES_APELLIDOS": ["JUAN PEREZ\nMARIA LOPEZ"],
        "IDENTIFICACIÓN": ["111\n222"],
    })
    resultado = split_multiple_comparecientes(df)
    assert len(resultado) == 2
    assert set(resultado["NOMBRES_APELLIDOS"]) == {"JUAN PEREZ", "MARIA LOPEZ"}


# ---------------------------------------------------------------------
# add_radicado_ius_revisada: guarda de columna ausente
# ---------------------------------------------------------------------

def test_add_radicado_ius_revisada_missing_column_returns_df_unchanged():
    df = pd.DataFrame({"OTRA_COLUMNA": ["x", "y"]})
    resultado = add_radicado_ius_revisada(df)
    pd.testing.assert_frame_equal(resultado, df)
    assert "Radicado IUS Revisada" not in resultado.columns


def test_add_radicado_ius_revisada_present_column_regression():
    df = pd.DataFrame({"RADICADO IUS": ["E-2018-610050 E-2020-611813"]})
    resultado = add_radicado_ius_revisada(df)
    assert resultado["Radicado IUS Revisada"].iloc[0] == "E-2020-611813"


# ---------------------------------------------------------------------
# split_by_status: degradación si faltan columnas
# ---------------------------------------------------------------------

def _df_split_status():
    return pd.DataFrame({
        "CLASIFICACIÓN DEL RADICADO": ["ACTIVO", "ARCHIVADO", "ARCHIVADO", "SIM"],
        "FUNCIONARIO A CARGO": ["JUAN PEREZ", "MARIA LOPEZ", "FUNCIONARIOS RETIRADOS", "JUAN PEREZ"],
    })


def test_split_by_status_present_columns_regression():
    grupos = split_by_status(_df_split_status())
    assert len(grupos["activos"]) == 2       # ACTIVO + SIM
    assert len(grupos["archivados"]) == 1    # ARCHIVADO, no retirado
    assert len(grupos["retirados"]) == 1     # ARCHIVADO + FUNCIONARIOS RETIRADOS
    assert len(grupos["sim"]) == 1           # el SIM, copiado desde activos


def test_split_by_status_missing_clasificacion():
    df = pd.DataFrame({"FUNCIONARIO A CARGO": ["JUAN PEREZ", "MARIA LOPEZ"]})
    grupos = split_by_status(df)
    assert len(grupos["activos"]) == len(df)
    assert len(grupos["archivados"]) == 0
    assert len(grupos["retirados"]) == 0
    assert len(grupos["sim"]) == 0


def test_split_by_status_missing_funcionario_a_cargo():
    df = pd.DataFrame({"CLASIFICACIÓN DEL RADICADO": ["ACTIVO", "ARCHIVADO", "ARCHIVADO"]})
    grupos = split_by_status(df)
    assert len(grupos["retirados"]) == 0
    assert len(grupos["archivados"]) == 2
    assert len(grupos["activos"]) == 1


# ---------------------------------------------------------------------
# run_similarity_report: retorno de conteos
# ---------------------------------------------------------------------

def _df_similarity_full():
    return pd.DataFrame({
        "No": [1, 2, 3, 4, 5],
        "RADICADO IUS": ["A-2020-001", "A-2020-001", "B-2020-002", "C-2020-003", "D-2020-004"],
        "IDENTIFICACIÓN": ["10000001", "10000001", "10000002", "10000002", "10000003"],
        "NOMBRES_APELLIDOS": [
            "JUAN PEREZ GOMEZ", "JUAN PEREZ GOMEZ", "MARIA LOPEZ RUIZ",
            "MARIA L RUIZ", "JUAN PEREZ GOMES",
        ],
    })


def test_run_similarity_report_counts_with_all_columns():
    resultado = run_similarity_report(_df_similarity_full())
    assert resultado == {"ius_duplicados": 1, "cedulas_variantes": 1, "nombres_fuzzy": 1}


def test_run_similarity_report_counts_default_zero_when_columns_missing():
    df = pd.DataFrame({"NOMBRES_APELLIDOS": ["JUAN PEREZ GOMEZ", "JUAN PEREZ GOMES"]})
    resultado = run_similarity_report(df)
    assert resultado["ius_duplicados"] == 0
    assert resultado["cedulas_variantes"] == 0
    assert resultado["nombres_fuzzy"] == 1


# ---------------------------------------------------------------------
# export_multi_sheet_excel: raise_errors
# ---------------------------------------------------------------------

def test_export_multi_sheet_excel_success_regression(tmp_path):
    ruta = tmp_path / "salida.xlsx"
    export_multi_sheet_excel({"Hoja1": pd.DataFrame({"A": [1, 2]})}, str(ruta))
    assert ruta.exists()


def test_export_multi_sheet_excel_invalid_path_default_returns_none(tmp_path):
    ruta_invalida = tmp_path / "carpeta_que_no_existe" / "salida.xlsx"
    resultado = export_multi_sheet_excel({"Hoja1": pd.DataFrame({"A": [1]})}, str(ruta_invalida))
    assert resultado is None
    assert not ruta_invalida.exists()


def test_export_multi_sheet_excel_invalid_path_raise_errors_propagates(tmp_path):
    ruta_invalida = tmp_path / "carpeta_que_no_existe" / "salida.xlsx"
    with pytest.raises(Exception):
        export_multi_sheet_excel({"Hoja1": pd.DataFrame({"A": [1]})}, str(ruta_invalida), raise_errors=True)


def test_export_multi_sheet_excel_on_sheet_done_called_per_sheet_in_order(tmp_path):
    ruta = tmp_path / "salida.xlsx"
    llamados = []
    export_multi_sheet_excel(
        {"Hoja1": pd.DataFrame({"A": [1]}), "Hoja2": pd.DataFrame({"A": [2]})},
        str(ruta),
        on_sheet_done=lambda nombre, i, total: llamados.append((nombre, i, total)),
    )
    assert llamados == [("Hoja1", 1, 2), ("Hoja2", 2, 2)]


def test_export_multi_sheet_excel_on_sheet_start_fires_before_on_sheet_done(tmp_path):
    ruta = tmp_path / "salida.xlsx"
    eventos = []
    export_multi_sheet_excel(
        {"Hoja1": pd.DataFrame({"A": [1]}), "Hoja2": pd.DataFrame({"A": [2]})},
        str(ruta),
        on_sheet_start=lambda nombre, i, total: eventos.append(("start", nombre, i, total)),
        on_sheet_done=lambda nombre, i, total: eventos.append(("done", nombre, i, total)),
    )
    assert eventos == [
        ("start", "Hoja1", 1, 2), ("done", "Hoja1", 1, 2),
        ("start", "Hoja2", 2, 2), ("done", "Hoja2", 2, 2),
    ]


def test_export_multi_sheet_excel_should_cancel_raises_export_cancelled(tmp_path):
    ruta = tmp_path / "salida.xlsx"
    with pytest.raises(ExportCancelled):
        export_multi_sheet_excel(
            {"Hoja1": pd.DataFrame({"A": [1]}), "Hoja2": pd.DataFrame({"A": [2]})},
            str(ruta),
            raise_errors=True,
            should_cancel=lambda: True,
        )


def test_export_multi_sheet_excel_should_cancel_without_raise_errors_returns_none(tmp_path):
    # Nota: cancelar ANTES de escribir cualquier hoja igual puede dejar un
    # archivo vacío/roto en disco (ExcelWriter.__exit__ lo cierra de todas
    # formas) — limpiarlo es responsabilidad del caller (gui/app.py lo hace
    # con raise_errors=True + except ExportCancelled). Esta prueba solo
    # confirma que el comportamiento con raise_errors=False (default) no
    # cambió: no propaga la excepción, retorna None.
    ruta = tmp_path / "no_deberia_completarse.xlsx"
    resultado = export_multi_sheet_excel(
        {"Hoja1": pd.DataFrame({"A": [1]})},
        str(ruta),
        should_cancel=lambda: True,
    )
    assert resultado is None
