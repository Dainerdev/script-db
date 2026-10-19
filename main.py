from pathlib import Path

from src.reading import read_excel_file, excel_general_information
from src.diagnostic import run_diagnostics
from src.parameters import TotalsMismatchError
from src.pipeline import run as run_pipeline, save
from src.review_excel import ReviewFileError, read_review

# ============================================================
# CONFIGURATION
# ============================================================
FILE_EXCEL = "data/original/base_pasantes.xlsx"
FILE_RESULTS = "data/processed/diagnostic_results.xlsx"
# Spec 002 (RF-61): ruta de un Excel de revisión (o de una tabla de
# parámetros revisados del supervisor) cuyas decisiones se aplican; None =
# solo las reglas automáticas. El Excel de revisión nuevo se guarda junto a
# FILE_RESULTS, con su nombre más "_revision" (RF-60, RF-36); si ya existe,
# con un número al final, sin reemplazarlo (RF-71).
FILE_REVIEW = None


def main():
    """
    Realiza el proceso completo: lectura -> diagnóstico -> limpieza ->
    estandarización de parámetros y separación de comparecientes -> reporte
    de similitud -> separación por estado -> exportación del resultado y del
    Excel de revisión. Desde la spec 002 hace exactamente lo mismo que el
    botón "Procesar" de la GUI (src/pipeline.py, RF-60). Devuelve las rutas
    guardadas (resultado, Excel de revisión), o None si no se guardó nada.
    """

    # ============================================================
    # 1. LECTURA
    # ============================================================
    df = read_excel_file(FILE_EXCEL)
    excel_general_information(df)
    if df is None:
        return None

    # ============================================================
    # 2. DIAGNÓSTICO INICIAL
    # ============================================================
    run_diagnostics(df)

    # ============================================================
    # 3. REVISIÓN A APLICAR (opcional, RF-61)
    # ============================================================
    review = None
    if FILE_REVIEW:
        try:
            review = read_review(FILE_REVIEW)
        except ReviewFileError as error:
            print(f"\nNo se procesó: {error}")
            return None
        print(f"\nAplicando la revisión de: {FILE_REVIEW}")

    # ============================================================
    # 4. LIMPIEZA, ESTANDARIZACIÓN, DUPLICADOS Y SEPARACIÓN
    # ============================================================
    try:
        result = run_pipeline(
            df,
            table=review.table if review is not None else None,
            decisions=review.decisions if review is not None else None,
            on_stage=lambda etapa: print(f"\n=== {etapa} ==="),
        )
    except TotalsMismatchError as error:
        print(f"\n{error}")
        return None

    # ============================================================
    # 5. EXPORTACIÓN (resultado + Excel de revisión, juntos o ninguno)
    # ============================================================
    print("\nEXPORTANDO RESULTADOS A EXCEL (resultado y Excel de revisión)...\n")
    Path(FILE_RESULTS).parent.mkdir(parents=True, exist_ok=True)
    result_path, review_path = save(result, FILE_RESULTS, style_reference_path=FILE_EXCEL)

    print(f"Resultado: {result_path}")
    print(f"Excel de revisión: {review_path}")
    for hoja, cantidad in result.counts.items():
        print(f" - {hoja}: {cantidad:,} registros")
    print(f"Pendientes de revisión: {result.pending_values:,} valores en {result.pending_rows:,} filas "
          "(pintados en el resultado y listados en el Excel de revisión).")
    return result_path, review_path


if __name__ == "__main__":
    main()
