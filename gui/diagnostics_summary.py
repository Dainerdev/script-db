import pandas as pd

from src.diagnostic import run_diagnostics, check_duplicates, run_similarity_report
from gui.state import DiagnosticSummary
from gui.validation import EXPECTED_COLUMNS


def _rows_with_extra_spaces(df: pd.DataFrame) -> int:
    """
    Cuenta FILAS (no celdas) con al menos un problema de espaciado en
    cualquier columna de texto. `run_diagnostics` (src/diagnostic.py)
    reporta esto por columna, no por fila, así que se agrega aquí aparte
    para RF-4 — no es lógica de limpieza de `src/`, es solo un conteo de
    presentación, con los mismos criterios (espacios al inicio/final o
    dobles) que ya usa `run_diagnostics`.
    """
    text_cols = [c for c in df.columns if pd.api.types.is_string_dtype(df[c]) or df[c].dtype == "object"]
    if not text_cols or len(df) == 0:
        return 0

    has_issue = pd.Series(False, index=df.index)
    for col in text_cols:
        data = df[col].dropna().astype(str)
        col_issue = (
            data.str.match(r"^\s+")
            | data.str.match(r".*\s+$")
            | data.str.contains(r"\s{2,}", regex=True)
        )
        has_issue.loc[col_issue.index] |= col_issue
    return int(has_issue.sum())


def _nulls_by_key_column(result_nulls: pd.DataFrame, df_columns) -> dict[str, int]:
    lookup = dict(zip(result_nulls["Columna"], result_nulls["Nulos"]))
    return {col: int(lookup[col]) for col in EXPECTED_COLUMNS if col in df_columns}


def build_summary(df: pd.DataFrame) -> DiagnosticSummary:
    """
    RF-4: arma el resumen de diagnóstico en español a partir de las
    funciones de `src/` (run_diagnostics, check_duplicates,
    run_similarity_report), tal como están. Los 3 conteos de similitud
    (IUS duplicados, cédulas con variantes, nombres fuzzy) vienen del
    diccionario que retorna run_similarity_report (T3) — ya trae sus
    propias guardas para columnas ausentes.
    """
    _, result_nulls, _, _, _ = run_diagnostics(df)
    similarity_counts = run_similarity_report(df)

    return DiagnosticSummary(
        total_rows=len(df),
        rows_with_extra_spaces=_rows_with_extra_spaces(df),
        nulls_by_key_column=_nulls_by_key_column(result_nulls, df.columns),
        duplicated_rows=len(check_duplicates(df)),
        ids_with_name_variants=similarity_counts["cedulas_variantes"],
        duplicated_ius=similarity_counts["ius_duplicados"],
        fuzzy_similar_names=similarity_counts["nombres_fuzzy"],
    )
