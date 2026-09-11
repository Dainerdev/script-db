import pandas as pd
import pytest

from gui import controller
from gui.state import DiagnosticSummary, ProcessResult, ValidationResult


def _df_completo():
    return pd.DataFrame({
        "No": [1, 2, 3],
        "RADICADO IUS": ["A-2020-001", "B-2020-002", "C-2020-003"],
        "IDENTIFICACIÓN": ["10000001", "10000002", "10000003"],
        "NOMBRES_APELLIDOS": ["JUAN PEREZ", "MARIA LOPEZ", "ANA TORRES"],
        "FECHA": ["2020-01-01", "2020-01-02", "2020-01-03"],
        "REPARTO": ["2020-01-01", "2020-01-02", "2020-01-03"],
        "CLASIFICACIÓN DEL RADICADO": ["ACTIVO", "ARCHIVADO", "SIM"],
        "FUNCIONARIO A CARGO": ["JUAN PEREZ", "FUNCIONARIOS RETIRADOS", "MARIA LOPEZ"],
        "MAGISTRADO": ["PEDRO SUAREZ", "PEDRO SUAREZ", "ANA TORRES"],
    })


# ---------------------------------------------------------------------
# process(): orden de eventos, error no previsto, columnas faltantes
# ---------------------------------------------------------------------

def test_process_emits_stages_then_done_in_order():
    eventos = []
    controller.process(_df_completo(), source_path="entrada.xlsx", on_event=eventos.append)

    tipos_relevantes = [e[0] for e in eventos if e[0] in ("stage", "done")]
    assert tipos_relevantes == ["stage", "stage", "stage", "done"]

    textos_stage = [e[1] for e in eventos if e[0] == "stage"]
    assert textos_stage == [
        "Limpiando y estandarizando...",
        "Analizando duplicados...",
        "Separando registros...",
    ]

    resultado = eventos[-1][1]
    assert isinstance(resultado, ProcessResult)
    assert resultado.source_path == "entrada.xlsx"
    assert set(resultado.sheets.keys()) == {
        "Reparto_Activo", "Archivados", "Funcionarios_Retirados", "SIM", "Multiples_IUS",
    }
    assert resultado.counts["Reparto_Activo"] == resultado.sheets["Reparto_Activo"].shape[0]


def test_process_unexpected_error_emits_error_with_log(monkeypatch, tmp_path):
    def _boom(df):
        raise RuntimeError("fallo forzado para la prueba")

    monkeypatch.setattr(controller, "clean_and_standardize", _boom)
    monkeypatch.chdir(tmp_path)  # gui/error_log.py escribe en ./logs por defecto

    eventos = []
    controller.process(_df_completo(), source_path="entrada.xlsx", on_event=eventos.append)

    assert eventos[-1][0] == "error"
    _, mensaje, log_path = eventos[-1]
    assert "inesperado" in mensaje.lower()
    assert log_path is not None

    from pathlib import Path
    assert "fallo forzado para la prueba" in Path(log_path).read_text(encoding="utf-8")


def test_process_cancelled_after_first_stage_stops_before_done():
    def should_cancel():
        return True  # el usuario "ya hizo clic en Cancelar" antes de empezar

    eventos = []
    controller.process(_df_completo(), source_path="entrada.xlsx", on_event=eventos.append, should_cancel=should_cancel)

    assert eventos[-1] == ("cancelled",)
    assert not any(e[0] == "done" for e in eventos)
    stages = [e[1] for e in eventos if e[0] == "stage"]
    assert stages == ["Limpiando y estandarizando..."]  # se corta antes de la 2a etapa


def test_process_not_cancelled_by_default():
    eventos = []
    controller.process(_df_completo(), source_path="entrada.xlsx", on_event=eventos.append)
    assert eventos[-1][0] == "done"


def test_process_missing_columns_completes_without_exception():
    df = pd.DataFrame({"ALGO": ["  con espacios  ", "normal"]})
    eventos = []
    controller.process(df, source_path="entrada.xlsx", on_event=eventos.append)

    assert eventos[-1][0] == "done"
    resultado = eventos[-1][1]
    assert resultado.sheets["Reparto_Activo"].shape[0] == 2  # todo queda en Activos (T3)
    assert resultado.sheets["Archivados"].empty


# ---------------------------------------------------------------------
# read_and_validate(): archivo inexistente, hoja faltante, archivo válido
# ---------------------------------------------------------------------

def test_read_and_validate_missing_file_emits_read_error():
    eventos = []
    controller.read_and_validate("archivo_que_no_existe_12345.xlsx", on_event=eventos.append)

    assert eventos[0] == ("stage", "Leyendo archivo...")
    assert eventos[-1][0] == "read_error"


def test_read_and_validate_wrong_sheet_name_emits_specific_read_error(tmp_path):
    ruta = tmp_path / "archivo.xlsx"
    pd.DataFrame({"A": [1, 2]}).to_excel(ruta, sheet_name="OtraHoja", index=False)

    eventos = []
    controller.read_and_validate(str(ruta), on_event=eventos.append)

    assert eventos[-1][0] == "read_error"
    assert "Reparto" in eventos[-1][1]


def test_read_and_validate_valid_file_emits_diagnostic(tmp_path):
    ruta = tmp_path / "archivo.xlsx"
    _df_completo().to_excel(ruta, sheet_name="Reparto", index=False)

    eventos = []
    controller.read_and_validate(str(ruta), on_event=eventos.append)

    assert eventos[0] == ("stage", "Leyendo archivo...")
    assert eventos[-1][0] == "diagnostic"

    _, validation, diagnostic, df = eventos[-1]
    assert isinstance(validation, ValidationResult)
    assert isinstance(diagnostic, DiagnosticSummary)
    assert validation.sheet_ok is True
    assert validation.missing_columns == []
    assert diagnostic.total_rows == 3
    assert len(df) == 3
