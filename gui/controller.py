from src import pipeline
from src.parameters import TotalsMismatchError
from src.reading import read_excel_file
from src.review_excel import ReviewFileError, read_review as read_review_file

from gui.validation import validate
from gui.diagnostics_summary import build_summary
from gui.error_log import handle_unexpected_error
from gui.state import ProcessResult

"""
Orquesta el pipeline en dos fases, cada una invocada por separado desde
gui/app.py (T8) — no una sola función, porque RF-3 exige una pausa real
para que el funcionario decida "Continuar"/"Cancelar" antes de seguir:

1. read_and_validate(path, on_event): RF-2/RF-3/RF-4. Lee el archivo UNA
   sola vez (Decisión técnica #6 del plan) y arma el diagnóstico.
2. process(df, source_path, on_event): RF-5/RF-6/RF-7/RF-10/RF-12. Desde la
   spec 002 delega en src/pipeline.py (Decisión #4): limpia, estandariza
   parámetros, separa comparecientes, analiza similitud y separa por estado
   sobre el DataFrame ya leído (nunca vuelve a tocar el disco).

read_review(path, on_event) lee el archivo de "Cargar revisión" (spec 002,
RF-44, RF-47); con lo que trae, gui/app.py vuelve a llamar a process.

La etapa "Exportando resultados..." (RF-8/RF-9/RF-11) no vive aquí: pasa
después del diálogo "Guardar como", que es responsabilidad de T8.
"""

# Tramo de la barra de progreso de cada etapa, según lo que tardó cada una
# con el corte del 5 de agosto (spec 002, T15: 8 s, 139 s, 13 s y 4 s).
_STAGE_PROGRESS = {
    pipeline.STAGE_CLEAN: (0.0, 0.05),
    pipeline.STAGE_PARAMETERS: (0.05, 0.88),
    pipeline.STAGE_DUPLICATES: (0.88, 0.97),
    pipeline.STAGE_SPLIT: (0.97, 1.0),
}


def _translate_read_error(exc: Exception) -> str:
    if isinstance(exc, FileNotFoundError):
        return "No se encontró el archivo. Verifica la ruta e intenta de nuevo."
    if isinstance(exc, PermissionError):
        return "No se pudo abrir el archivo: parece estar abierto en otro programa (ciérralo e intenta de nuevo)."
    if isinstance(exc, ValueError) and "Worksheet" in str(exc):
        return "El archivo no tiene una hoja llamada exactamente 'Reparto'."
    return "No se pudo leer el archivo: parece estar dañado o no ser un Excel válido."


def _translate_review_error(exc: ReviewFileError) -> str:
    """RF-47: el mensaje de ReviewFileError, salvo que la causa sea una de las de lectura con texto propio."""
    if isinstance(exc.__cause__, (FileNotFoundError, PermissionError)):
        return _translate_read_error(exc.__cause__)
    return str(exc)


def read_and_validate(path, on_event) -> None:
    """
    RF-2/RF-3/RF-4. Emite:
    - ("stage", texto)
    - ("read_error", mensaje_especifico)                       si RF-2 bloquea
    - ("diagnostic", ValidationResult, DiagnosticSummary, df)   si se pudo leer
    """
    on_event(("stage", "Leyendo archivo..."))
    try:
        df = read_excel_file(path, raise_errors=True)
    except Exception as exc:
        on_event(("read_error", _translate_read_error(exc)))
        return

    validation = validate(df)
    if not validation.sheet_ok:
        on_event(("read_error", "El archivo no tiene datos reconocibles en la hoja 'Reparto'."))
        return

    diagnostic = build_summary(df)
    on_event(("diagnostic", validation, diagnostic, df))


def process(df, source_path, on_event, should_cancel=lambda: False, review=None) -> None:
    """
    RF-5/RF-6/RF-7/RF-10/RF-12. Invoca solo funciones de `src/` (T3); desde
    la spec 002, `pipeline.run`. `review` es lo leído por read_review
    (ReviewFile): su tabla de parámetros revisados y sus decisiones se
    aplican (RF-44, RF-89). Emite ("stage", texto) y ("progress_crawl",
    desde, hasta) por etapa —incluida "Estandarizando parámetros...", RF-52—
    y termina con ("done", ProcessResult); con ("cancelled",) si
    should_cancel() da True entre etapas o entre columnas (no se puede
    interrumpir una llamada de pandas a mitad de camino; RF-55: no queda
    resultado); con ("error", mensaje, log_path) si los totales no cuadran
    (RF-92, con el mensaje que dice qué columna falló) o ante un error no
    previsto (mensaje genérico).
    """
    def on_stage(text):
        start, end = _STAGE_PROGRESS[text]
        on_event(("stage", text))
        on_event(("progress_crawl", start, end))

    try:
        result = pipeline.run(
            df,
            table=review.table if review is not None else None,
            decisions=review.decisions if review is not None else None,
            on_stage=on_stage,
            should_cancel=should_cancel,
        )
    except pipeline.ProcessCancelled:
        on_event(("cancelled",))
        return
    except TotalsMismatchError as exc:
        _, log_path = handle_unexpected_error(exc)
        on_event(("error", str(exc), log_path))
        return
    except Exception as exc:
        mensaje, log_path = handle_unexpected_error(exc)
        on_event(("error", mensaje, log_path))
        return

    on_event(("progress", 1.0))
    on_event(("done", ProcessResult(
        sheets=result.sheets,
        counts=result.counts,
        source_path=source_path,
        review=result.review,
        highlights=result.highlights,
        pending_values=result.pending_values,
        pending_rows=result.pending_rows,
        missing_columns=result.missing_columns,
    )))


def read_review(path, on_event) -> None:
    """
    "Cargar revisión" (spec 002, RF-44, RF-47, RF-89). Emite ("stage",
    texto) y termina con ("review_loaded", ReviewFile) si el archivo es un
    Excel de revisión o una tabla de parámetros revisados, o con
    ("review_error", mensaje) si no lo es o no se pudo leer: en ese caso no
    cambia nada. Un error no previsto da ("error", mensaje_generico, log_path).
    """
    on_event(("stage", "Leyendo archivo..."))
    try:
        review = read_review_file(path)
    except ReviewFileError as exc:
        on_event(("review_error", _translate_review_error(exc)))
        return
    except Exception as exc:
        mensaje, log_path = handle_unexpected_error(exc)
        on_event(("error", mensaje, log_path))
        return
    on_event(("review_loaded", review))
