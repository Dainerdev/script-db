import pandas as pd
import pytest

from gui import controller
from gui.state import DiagnosticSummary, ProcessResult, ValidationResult
from src import parameters as p
from src import pipeline
from src import review_excel as rx

ETAPAS = ["Limpiando y estandarizando...", "Estandarizando parámetros...", "Analizando duplicados...",
          "Separando registros..."]
PEGADO = "Ana Perez Gomez Y Luis Diaz Rojas"


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
    assert tipos_relevantes == ["stage", "stage", "stage", "stage", "done"]

    # RF-52 (cambia RF-6 de la spec 001): la etapa nueva va entre limpieza y duplicados.
    textos_stage = [e[1] for e in eventos if e[0] == "stage"]
    assert textos_stage == ETAPAS

    resultado = eventos[-1][1]
    assert isinstance(resultado, ProcessResult)
    assert resultado.source_path == "entrada.xlsx"
    assert set(resultado.sheets.keys()) == {
        "Reparto_Activo", "Archivados", "Funcionarios_Retirados", "SIM", "Multiples_IUS",
    }
    assert resultado.counts["Reparto_Activo"] == resultado.sheets["Reparto_Activo"].shape[0]


def test_process_progress_never_goes_back_and_ends_full():
    eventos = []
    controller.process(_df_completo(), source_path="entrada.xlsx", on_event=eventos.append)

    puntos = []
    for evento in eventos:
        if evento[0] == "progress":
            puntos.append(evento[1])
        elif evento[0] == "progress_crawl":
            puntos.extend(evento[1:])
    assert puntos == sorted(puntos)
    assert puntos[-1] == 1.0


def test_process_unexpected_error_emits_error_with_log(monkeypatch, tmp_path):
    def _boom(df):
        raise RuntimeError("fallo forzado para la prueba")

    monkeypatch.setattr(pipeline, "clean_and_standardize", _boom)
    monkeypatch.chdir(tmp_path)  # gui/error_log.py escribe en ./logs por defecto

    eventos = []
    controller.process(_df_completo(), source_path="entrada.xlsx", on_event=eventos.append)

    assert eventos[-1][0] == "error"
    _, mensaje, log_path = eventos[-1]
    assert "inesperado" in mensaje.lower()
    assert log_path is not None

    from pathlib import Path
    assert "fallo forzado para la prueba" in Path(log_path).read_text(encoding="utf-8")


def _procesar_cancelando_en(etapa):
    eventos = []

    def should_cancel():  # el usuario hace clic en Cancelar cuando aparece `etapa`
        return ("stage", etapa) in eventos

    controller.process(_df_completo(), source_path="entrada.xlsx", on_event=eventos.append, should_cancel=should_cancel)
    return eventos


def test_process_cancelled_after_first_stage_stops_before_done():
    eventos = _procesar_cancelando_en(ETAPAS[0])

    assert eventos[-1] == ("cancelled",)
    assert not any(e[0] == "done" for e in eventos)
    stages = [e[1] for e in eventos if e[0] == "stage"]
    assert stages == ETAPAS[:1]  # se corta antes de la 2a etapa


def test_process_cancelled_during_standardization_gives_no_result():
    # RF-55: sin resultado no hay nada que guardar (ni resultado ni Excel de revisión).
    eventos = _procesar_cancelando_en(ETAPAS[1])

    assert eventos[-1] == ("cancelled",)
    assert not any(e[0] == "done" for e in eventos)
    assert [e[1] for e in eventos if e[0] == "stage"] == ETAPAS[:2]


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
    assert resultado.missing_columns == list(p.COLUMN_TYPES)   # RF-53: se omite solo su estandarización


# ---------------------------------------------------------------------
# process(): estandarización (spec 002)
# ---------------------------------------------------------------------

def test_process_totals_mismatch_emits_clear_error_and_no_result(monkeypatch, tmp_path):
    verificar = p.verify_totals

    def alterada(filas_por_columna, total):
        filas = dict(filas_por_columna)
        columna = next(iter(filas))
        filas[columna] = filas[columna][:-1]
        return verificar(filas, total)
    monkeypatch.setattr(p, "verify_totals", alterada)
    monkeypatch.chdir(tmp_path)

    eventos = []
    controller.process(_df_completo(), source_path="entrada.xlsx", on_event=eventos.append)

    assert eventos[-1][0] == "error"
    _, mensaje, log_path = eventos[-1]
    assert "no cuadra" in mensaje and "No se guardó" in mensaje    # RF-92: el mensaje dice qué columna falló
    assert log_path is not None
    assert not any(e[0] == "done" for e in eventos)


def test_process_result_carries_review_highlights_and_pending_counts():
    df = _df_completo()
    df.loc[2, "NOMBRES_APELLIDOS"] = PEGADO
    df.loc[2, "IDENTIFICACIÓN"] = "10000003\n10000004"
    eventos = []

    controller.process(df, source_path="entrada.xlsx", on_event=eventos.append)

    resultado = eventos[-1][1]
    assert isinstance(resultado.review, rx.ReviewData)
    assert resultado.review.totals                     # RF-92: va al Resumen del Excel de revisión
    assert (resultado.pending_values, resultado.pending_rows) == (1, 1)     # RF-50
    assert any((0, "NOMBRES_APELLIDOS") in celdas for celdas in resultado.highlights.values())   # RF-40


def test_process_applies_loaded_decisions():
    revision = rx.ReviewFile(table=None, has_decisions=True,
                             decisions=p.Decisions(table=[("MAGISTRADO", "PEDRO SUAREZ", "Pedro Suarez Gil")]))
    eventos = []

    controller.process(_df_completo(), source_path="entrada.xlsx", on_event=eventos.append, review=revision)

    resultado = eventos[-1][1]
    magistrados = set(pd.concat([resultado.sheets["Reparto_Activo"], resultado.sheets["Funcionarios_Retirados"]])["MAGISTRADO"])
    assert magistrados == {"PEDRO SUAREZ GIL", "ANA TORRES"}
    assert resultado.review.decisions is revision.decisions      # se copian al nuevo Excel de revisión (RF-46)


def test_process_applies_reviewed_table():
    tabla = p.ReviewedTable.from_rows([("MAGISTRADO", "ANA TORRES", "ANA TORRES ROJAS")])
    eventos = []

    controller.process(_df_completo(), source_path="entrada.xlsx", on_event=eventos.append,
                       review=rx.ReviewFile(table=tabla, has_decisions=False))

    resultado = eventos[-1][1]
    assert "ANA TORRES ROJAS" in set(resultado.sheets["Reparto_Activo"]["MAGISTRADO"])
    assert resultado.review.table is tabla                        # se copia al nuevo Excel de revisión (RF-96)


# ---------------------------------------------------------------------
# read_review(): "Cargar revisión" (RF-44, RF-47, RF-89)
# ---------------------------------------------------------------------

def test_read_review_valid_table_emits_review_loaded(tmp_path):
    ruta = tmp_path / "tabla.xlsx"
    pd.DataFrame({"Columna": ["MAGISTRADO"], "Valor original": ["ANA TORRES"],
                  rx.FINAL_COLUMN: ["ANA TORRES ROJAS"]}).to_excel(ruta, sheet_name=rx.MAPEO_SHEET, index=False)

    eventos = []
    controller.read_review(str(ruta), on_event=eventos.append)

    assert eventos[0] == ("stage", "Leyendo archivo...")
    assert eventos[-1][0] == "review_loaded"
    revision = eventos[-1][1]
    assert revision.table.lookup("MAGISTRADO", "ANA TORRES") == "ANA TORRES ROJAS"


def test_read_review_other_excel_emits_review_error(tmp_path):
    ruta = tmp_path / "otro.xlsx"
    pd.DataFrame({"A": [1]}).to_excel(ruta, sheet_name="Reparto", index=False)

    eventos = []
    controller.read_review(str(ruta), on_event=eventos.append)

    assert eventos[-1][0] == "review_error"
    assert "no es un Excel de revisión" in eventos[-1][1]


def test_read_review_missing_file_emits_clear_review_error():
    eventos = []
    controller.read_review("revision_que_no_existe_12345.xlsx", on_event=eventos.append)

    assert eventos[-1] == ("review_error", "No se encontró el archivo. Verifica la ruta e intenta de nuevo.")


def test_read_review_damaged_file_emits_review_error_without_technical_text(tmp_path):
    ruta = tmp_path / "danado.xlsx"
    ruta.write_bytes(b"esto no es un Excel")

    eventos = []
    controller.read_review(str(ruta), on_event=eventos.append)

    assert eventos[-1][0] == "review_error"
    assert "Errno" not in eventos[-1][1] and "Traceback" not in eventos[-1][1]


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
    # Spec 002, RF-53: un archivo completo trae también las columnas estandarizadas.
    completo = _df_completo().assign(**{col: ["X"] * 3 for col in p.COLUMN_TYPES if col not in _df_completo()})
    completo.to_excel(ruta, sheet_name="Reparto", index=False)

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
