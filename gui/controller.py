from src.reading import read_excel_file
from src.standardization import clean_and_standardize, add_radicado_ius_revisada
from src.diagnostic import run_similarity_report, split_by_status, extract_multi_ius

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
2. process(df, source_path, on_event): RF-5/RF-6/RF-7/RF-10/RF-12. Limpia,
   analiza similitud, separa y agrega "Radicado IUS Revisada" sobre el
   DataFrame ya leído (nunca vuelve a tocar el disco).

La etapa "Exportando resultados..." (RF-8/RF-9/RF-11) no vive aquí: pasa
después del diálogo "Guardar como", que es responsabilidad de T8.
"""


def _translate_read_error(exc: Exception) -> str:
    if isinstance(exc, FileNotFoundError):
        return "No se encontró el archivo. Verifica la ruta e intenta de nuevo."
    if isinstance(exc, PermissionError):
        return "No se pudo abrir el archivo: parece estar abierto en otro programa (ciérralo e intenta de nuevo)."
    if isinstance(exc, ValueError) and "Worksheet" in str(exc):
        return "El archivo no tiene una hoja llamada exactamente 'Reparto'."
    return "No se pudo leer el archivo: parece estar dañado o no ser un Excel válido."


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


def process(df, source_path, on_event, should_cancel=lambda: False) -> None:
    """
    RF-5/RF-6/RF-7/RF-10/RF-12. Invoca solo funciones de `src/` (T3).
    Emite ("stage", texto) por etapa y termina con ("done", ProcessResult),
    ("cancelled",) si should_cancel() da True entre etapas (no se puede
    interrumpir una llamada de pandas a mitad de camino, solo saltar a la
    siguiente), o ante un error no previsto ("error", mensaje_generico, log_path).
    """
    try:
        on_event(("stage", "Limpiando y estandarizando..."))
        on_event(("progress", 1 / 3))
        df = clean_and_standardize(df)
        if should_cancel():
            on_event(("cancelled",))
            return

        on_event(("stage", "Analizando duplicados..."))
        on_event(("progress", 2 / 3))
        run_similarity_report(df)
        if should_cancel():
            on_event(("cancelled",))
            return

        on_event(("stage", "Separando registros..."))
        on_event(("progress", 1.0))
        grupos = split_by_status(df)
        df_multi_ius = extract_multi_ius(df)

        grupos["activos"] = add_radicado_ius_revisada(grupos["activos"])
        grupos["archivados"] = add_radicado_ius_revisada(grupos["archivados"])
        grupos["retirados"] = add_radicado_ius_revisada(grupos["retirados"])
        grupos["sim"] = add_radicado_ius_revisada(grupos["sim"])
        df_multi_ius = add_radicado_ius_revisada(df_multi_ius)

        sheets = {
            "Reparto_Activo": grupos["activos"],
            "Archivados": grupos["archivados"],
            "Funcionarios_Retirados": grupos["retirados"],
            "SIM": grupos["sim"],
            "Multiples_IUS": df_multi_ius,
        }
        counts = {name: len(sheet) for name, sheet in sheets.items()}

        on_event(("done", ProcessResult(sheets=sheets, counts=counts, source_path=source_path)))
    except Exception as exc:
        mensaje, log_path = handle_unexpected_error(exc)
        on_event(("error", mensaje, log_path))
