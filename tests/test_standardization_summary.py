"""T17: resumen de la estandarización en la ventana (RF-43, RF-48, RF-53, RF-76, RF-77, RF-92, RF-95). Sin Tk."""
from collections import Counter

import pandas as pd

from gui.standardization_summary import format_standardization
from gui.state import ProcessResult
from src import parameters as p
from src import review_excel as rx


def _resultado(**cambios):
    datos = dict(
        entries=[],
        summary={
            "SOLICITUD": {"estados": {p.SUMMARY_UNCHANGED: (3, 1200), p.AUTOMATIC: (2, 40), p.REVIEW: (1, 5)},
                          "otra categoría": (2, 7)},
            "MAGISTRADO": {"estados": {p.SUMMARY_UNCHANGED: (10, 1245)}, "otra categoría": (0, 0)},
        },
        totals={"SOLICITUD": Counter({p.UNCHANGED: 1200, p.REPLACED: 40, p.PENDING_RESULT: 5}),
                "MAGISTRADO": Counter({p.UNCHANGED: 1245})},
        catalogs={},
        separation={"SEPARADA": 3, "SEPARADA SIN CONFIRMAR": 2, "SIN SEPARAR": 1, "": 1239, "filas": 1252},
    )
    datos.update(cambios.pop("review", {}))
    base = dict(sheets={}, counts={}, source_path="entrada.xlsx", review=rx.ReviewData(**datos),
                pending_values=1, pending_rows=5, missing_columns=["SALA"])
    base.update(cambios)
    return ProcessResult(**base)


def test_estados_por_columna_con_valores_y_filas():
    texto = format_standardization(_resultado())

    assert "SOLICITUD: SIN CAMBIO 3 valores / 1,200 filas · AUTOMÁTICO 2 / 40 · PARA REVISAR 1 / 5" in texto
    assert "MAGISTRADO: SIN CAMBIO 10 valores / 1,245 filas" in texto
    assert "De otra categoría: SOLICITUD 2 valores / 7 filas" in texto       # aparte (RF-43)


def test_un_solo_valor_o_fila_va_en_singular():
    texto = format_standardization(_resultado(review={"summary": {
        "SALA": {"estados": {p.SUMMARY_UNCHANGED: (1, 1)}, "otra categoría": (1, 1)}}}))

    assert "SALA: SIN CAMBIO 1 valor / 1 fila" in texto
    assert "De otra categoría: SALA 1 valor / 1 fila" in texto


def test_pendientes_totales_y_separacion():
    texto = format_standardization(_resultado())

    assert "Pendientes de revisión: 1 valor en 5 filas" in texto
    assert "Verificación de totales: cada una de las 2 columnas suma 1,245 filas." in texto      # RF-92
    assert ("Separación de comparecientes: 3 SEPARADA · 2 SEPARADA SIN CONFIRMAR · 1 SIN SEPARAR · "
            "1,239 no necesitaban separarse; el resultado tiene 1,252 filas.") in texto          # RF-95


def test_singular_y_plural_de_los_pendientes():
    assert "1 valor en 1 fila." in format_standardization(_resultado(pending_values=1, pending_rows=1))
    assert "8,742 valores en 35,117 filas" in format_standardization(_resultado(pending_values=8742, pending_rows=35117))


def test_sin_pendientes_lo_dice():
    texto = format_standardization(_resultado(pending_values=0, pending_rows=0))

    assert "No quedaron valores pendientes de revisión." in texto


def test_explica_el_color_y_la_observacion_y_lista_faltantes():
    texto = format_standardization(_resultado())

    assert "relleno" in texto and p.OBSERVATION in texto                      # RF-76
    assert "faltan en el archivo (se omitió solo su estandarización): SALA" in texto     # RF-53


def test_decisiones_sin_coincidencia_y_no_aplicadas():
    problemas = [f"SOLICITUD · «v{i}»: dos decisiones distintas; no se aplicó ninguna." for i in range(12)]
    texto = format_standardization(_resultado(review={
        "decisions": p.Decisions(), "unmatched_decisions": 3, "invalid_decisions": problemas}))

    assert "Decisiones cargadas que no coincidieron con ningún valor: 3" in texto     # RF-77
    assert "Decisiones no aplicadas (12):" in texto                                     # RF-48
    assert problemas[0] in texto and problemas[9] in texto and problemas[10] not in texto
    assert "y 2 más (ver el Resumen del Excel de revisión)" in texto


def test_sin_decisiones_cargadas_no_habla_de_decisiones():
    assert "Decisiones" not in format_standardization(_resultado())


def test_resultado_sin_estandarizacion_no_tiene_resumen():
    assert format_standardization(ProcessResult(sheets={}, counts={}, source_path="x.xlsx")) == ""
