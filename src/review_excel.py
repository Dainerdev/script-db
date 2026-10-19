"""Escritura y lectura del Excel de revisión, ubicaciones y guardado en par (spec 002)."""
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from python_calamine import CalamineError

from src.exportation import PENDING_FILL  # noqa: F401  (el Resumen explica este color, RF-76)
from src.parameters import (
    CEDULA_AS_IS, DECIDED, EMPTY_TO_UNDETERMINED, OBSERVATION, PENDING_RESULT, REPLACED, REVIEW, TO_CONFIRM,
    UNCHANGED, Decisions, ReviewedTable, canonical_column,
)
from src.text_keys import to_text

MAPEO_SHEET = "Mapeo"
FINAL_COLUMN = "¿Unificar con? (valor final)"
MAPEO_COLUMNS = ["Columna", "Valor original", FINAL_COLUMN]
TABLE_SHEET = "Tabla de estandarización"
SUMMARY_SHEET = "Resumen"
CATALOG_PREFIX = "Catálogo "
DECISION_COLUMN = "Decisión"
CORRECTION_COLUMN = "Corregir a"
TABLE_COLUMNS = ["Columna", "Valor original", "Valor final o sugerido", "Similitud", "Motivo", "Estado",
                 "Filas afectadas", "Ubicación", DECISION_COLUMN]
CATALOG_COLUMNS = ["Valor", "Filas", CORRECTION_COLUMN]
SUMMARY_COLUMNS = ["Sección", "Columna", "Concepto", "Valores", "Filas"]
MAX_LOCATIONS = 50                                      # RF-37
_STATE_ORDER = {REVIEW: 0, TO_CONFIRM: 1}              # RF-38
_TOTALS_ORDER = [EMPTY_TO_UNDETERMINED, PENDING_RESULT, CEDULA_AS_IS, REPLACED, UNCHANGED]   # RF-92
_SEPARATION_ORDER = [("SEPARADA", "SEPARADA"), ("SEPARADA SIN CONFIRMAR", "SEPARADA SIN CONFIRMAR"),
                     ("SIN SEPARAR", "SIN SEPARAR"), ("", "No necesitaban separarse")]


class ReviewFileError(Exception):
    """El archivo elegido en "Cargar revisión" no sirve (RF-47)."""


@dataclass
class ReviewFile:
    """
    Lo que trae el archivo de "Cargar revisión" (RF-89): la tabla de
    parámetros revisados (hoja "Mapeo"), si trae decisiones (hoja "Tabla de
    estandarización") y las decisiones y correcciones de catálogo leídas.
    """
    table: ReviewedTable | None
    has_decisions: bool
    decisions: Decisions | None = None


@dataclass
class ReviewData:
    """Todo lo que va al Excel de revisión (plan, T13)."""
    entries: list
    summary: dict
    totals: dict
    catalogs: dict
    separation: dict | None = None          # RF-95, de separation_counts
    unmatched_decisions: int = 0            # RF-77
    invalid_decisions: list = field(default_factory=list)   # RF-48
    decisions: Decisions | None = None      # cargadas: se copian (RF-46)
    table: ReviewedTable | None = None      # RF-96
    locations: dict | None = None           # _row_id → ["hoja fila N"], de T14 (RF-37)
    saved_as: str = ""                      # RF-71


def separation_counts(df) -> dict:
    """RF-95: registros en cada estado de "SEPARACIÓN" (el vacío, los que no necesitaban separarse) y filas del resultado."""
    by_record = df.drop_duplicates("ID REGISTRO")["SEPARACIÓN"].fillna("")
    counts = Counter(by_record)
    result = {status: counts.get(status, 0) for status, _ in _SEPARATION_ORDER}
    result["filas"] = len(df)
    return result


def _text(value) -> str:
    return "" if value is None else to_text(value)


def _locations(row_ids, locations) -> str:
    if not locations:
        return ""
    found = []
    for row_id in row_ids:
        for place in locations.get(row_id, ()):
            if place not in found:
                found.append(place)
                if len(found) == MAX_LOCATIONS:
                    return "; ".join(found)
    return "; ".join(found)


def _table_rows(data: ReviewData) -> list:
    """RF-37 a RF-39: una fila por entrada, primero PARA REVISAR y POR CONFIRMAR, por filas (RF-38)."""
    ordered = sorted(data.entries, key=lambda entry: (_STATE_ORDER.get(entry.state, 2), -len(entry.row_ids)))
    rows = [[entry.column, entry.original, entry.final,
             "" if entry.similarity is None else f"{entry.similarity:.1f}", entry.motive, entry.state,
             str(len(entry.row_ids)), _locations(entry.row_ids, data.locations), entry.decision or ""]
            for entry in ordered]
    if data.decisions is not None:                                                    # RF-46
        written = {(entry.column, entry.original, entry.decision) for entry in data.entries if entry.decision}
        for column, original, text in data.decisions.table:
            key = (_text(column).strip(), _text(original).strip(), _text(text))
            if key not in written:
                written.add(key)
                rows.append([key[0], _text(original), "", "", "decisión", DECIDED, "0", "", key[2]])
    return rows


def _catalog_rows(column, catalog, decisions) -> list:
    """RF-42: valor, filas y "Corregir a"; las correcciones cargadas se copian (RF-46)."""
    rows = [[_text(value), str(int(count)), ""] for value, count in zip(catalog["Valor"], catalog["Filas"])]
    if decisions is not None:
        position = {row[0]: row for row in rows}
        for row_column, value, text in decisions.catalog:
            if _text(row_column).strip() != column:
                continue
            value = _text(value).strip()
            if value in position:
                position[value][2] = _text(text)
            else:
                position[value] = [value, "0", _text(text)]
                rows.append(position[value])
    return rows


def _summary_rows(data: ReviewData) -> list:
    rows = [
        ["Cómo leer", "", "El relleno de color en una celda del resultado: valor pendiente de revisión.", "", ""],
        ["Cómo leer", "", f"La columna «{OBSERVATION}» del resultado trae las marcas de la fila: pendiente de "
                          "revisión, no es una persona, hay más comparecientes sin nombrar.", "", ""],
        ["Cómo leer", "", f"En «{DECISION_COLUMN}» (Tabla de estandarización) escriba ACEPTAR (usar la "
                          "sugerencia), MANTENER (dejar el original) u otro texto (el valor final); para separar "
                          "nombres, las partes separadas por « | ». Después use «Cargar revisión».", "", ""],
        ["Cómo leer", "", f"En «{CORRECTION_COLUMN}» (hojas de catálogo) escriba el valor correcto: cambia ese "
                          "valor y todas sus variantes.", "", ""],
    ]
    for column, info in data.summary.items():                                          # RF-43
        for state, (values, count) in info["estados"].items():
            rows.append(["Estados por columna", column, state, str(values), str(count)])
        other_values, other_rows = info.get("otra categoría", (0, 0))
        rows.append(["Estados por columna", column, "de otra categoría", str(other_values), str(other_rows)])
    for column, counts in data.totals.items():                                         # RF-92
        for result in _TOTALS_ORDER:
            rows.append(["Verificación de totales", column, result, "", str(counts.get(result, 0))])
        rows.append(["Verificación de totales", column, "Suma", "", str(sum(counts.values()))])
    if data.separation is not None:                                                    # RF-95
        for status, label in _SEPARATION_ORDER:
            rows.append(["Separación de comparecientes", "", label, str(data.separation.get(status, 0)), ""])
        rows.append(["Separación de comparecientes", "", "Filas del resultado", str(data.separation.get("filas", 0)), ""])
    rows.append(["Decisiones", "", "Decisiones sin coincidencia", str(data.unmatched_decisions), ""])   # RF-77
    for problem in data.invalid_decisions:                                             # RF-48
        rows.append(["Decisiones", "", f"No aplicada: {problem}", "", ""])
    if data.saved_as:                                                                  # RF-71
        rows.append(["Archivo", "", "Guardado como", data.saved_as, ""])
    return rows


def write_review(path, data: ReviewData) -> None:
    """
    Escribe el Excel de revisión: la tabla de estandarización con "Decisión"
    vacía (salvo las decisiones copiadas), el Resumen, una hoja de catálogo
    por columna con "Corregir a" y, si se aplicó una tabla revisada, la hoja
    "Mapeo" (RF-36 a RF-39, RF-42, RF-43, RF-46, RF-96). Todo como texto
    (Decisión #11), así la clave (columna, valor original) vuelve igual.
    """
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        pd.DataFrame(_table_rows(data), columns=TABLE_COLUMNS, dtype=object).to_excel(
            writer, sheet_name=TABLE_SHEET, index=False)
        pd.DataFrame(_summary_rows(data), columns=SUMMARY_COLUMNS, dtype=object).to_excel(
            writer, sheet_name=SUMMARY_SHEET, index=False)
        for column, catalog in data.catalogs.items():
            pd.DataFrame(_catalog_rows(column, catalog, data.decisions), columns=CATALOG_COLUMNS, dtype=object).to_excel(
                writer, sheet_name=f"{CATALOG_PREFIX}{column}"[:31], index=False)
        if data.table is not None:
            write_mapeo_sheet(writer, data.table)


def _read_decisions(book, sheets) -> Decisions:
    table = pd.read_excel(book, sheet_name=TABLE_SHEET, dtype=object)
    decisions = Decisions()
    for column, original, text in zip(table["Columna"], table["Valor original"], table[DECISION_COLUMN]):
        if _text(text).strip():
            decisions.table.append((_text(column).strip(), _text(original), _text(text)))
    for sheet in sheets:
        if not sheet.startswith(CATALOG_PREFIX):
            continue
        catalog = pd.read_excel(book, sheet_name=sheet, dtype=object)
        if not all(column in catalog.columns for column in ("Valor", CORRECTION_COLUMN)):
            continue
        column = sheet[len(CATALOG_PREFIX):]
        for value, text in zip(catalog["Valor"], catalog[CORRECTION_COLUMN]):
            if _text(text).strip():
                decisions.catalog.append((column, _text(value), _text(text)))
    return decisions


def read_review(path) -> ReviewFile:
    """
    Lee el archivo de "Cargar revisión" y reconoce su formato por las hojas
    (RF-89): "Mapeo" con sus tres columnas → tabla de parámetros revisados;
    "Tabla de estandarización" con Columna, Valor original y Decisión → sus
    decisiones, más las correcciones de las hojas de catálogo; las dos a la
    vez es un Excel de revisión con la tabla copiada (RF-96). Sin ninguna,
    ReviewFileError con un mensaje claro (RF-47). Todo se lee como texto
    (Decisión #11), así "0012" y "44317" vuelven iguales.
    """
    try:
        with pd.ExcelFile(path, engine="calamine") as book:
            sheets = book.sheet_names
            table = None
            if MAPEO_SHEET in sheets:
                mapeo = pd.read_excel(book, sheet_name=MAPEO_SHEET, dtype=object)
                if all(column in mapeo.columns for column in MAPEO_COLUMNS):
                    table = ReviewedTable.from_rows(zip(*(mapeo[column] for column in MAPEO_COLUMNS)))
            has_decisions = TABLE_SHEET in sheets and all(
                column in pd.read_excel(book, sheet_name=TABLE_SHEET, nrows=0).columns
                for column in ("Columna", "Valor original", DECISION_COLUMN))
            decisions = _read_decisions(book, sheets) if has_decisions else None
    except (OSError, ValueError, CalamineError) as error:      # la causa queda en __cause__
        raise ReviewFileError("No se pudo leer el archivo elegido: parece estar dañado, abierto en otro "
                              "programa o no ser un Excel válido.") from error
    if table is None and not has_decisions:
        raise ReviewFileError(
            "El archivo elegido no es un Excel de revisión ni una tabla de parámetros revisados: le falta "
            f"la hoja «{MAPEO_SHEET}» (con las columnas {', '.join(MAPEO_COLUMNS)}) o la hoja «{TABLE_SHEET}».")
    return ReviewFile(table, has_decisions, decisions)


def write_mapeo_sheet(writer: pd.ExcelWriter, table: ReviewedTable) -> None:
    """
    Copia la tabla de parámetros revisados completa, como texto, en la hoja
    "Mapeo" del Excel de revisión (RF-96): así, al volver a cargar ese Excel,
    se aplican la tabla y las decisiones nuevas (RF-89).
    """
    pd.DataFrame(table.rows, columns=MAPEO_COLUMNS, dtype=object).to_excel(
        writer, sheet_name=MAPEO_SHEET, index=False)


# ---------------------------------------------------------------------------
# T14: ubicaciones, celdas a pintar y guardado en par
# ---------------------------------------------------------------------------

def public_frame(df):
    """El resultado sin las columnas internas del proceso (`_row_id`, `_person`, `_marks`, `_pending`)."""
    return df[[column for column in df.columns if not str(column).startswith("_")]].copy()


def highlight_cells(sheets) -> dict:
    """
    RF-40: por hoja, las celdas a pintar, (posición de la fila, encabezado
    real de la columna), sacadas de `_pending` (que guarda el nombre
    canónico: TIPO DE EXPEDIENTE puede venir con texto extra, RF-54).
    """
    result = {}
    for name, df in sheets.items():
        if "_pending" not in df.columns:
            continue
        header = {}
        for column in df.columns:
            canonical = canonical_column(column)
            if canonical is not None:
                header.setdefault(canonical, column)
        cells = [(position, header[column]) for position, pending in enumerate(df["_pending"])
                 for column in pending if column in header]
        if cells:
            result[name] = cells
    return result


def locations_by_row(sheets) -> dict:
    """RF-37: `_row_id` → ["hoja fila N", …] (N es la fila de Excel: el encabezado es la 1)."""
    places = {}
    for name, df in sheets.items():
        if "_row_id" not in df.columns:
            continue
        for position, row_id in enumerate(df["_row_id"]):
            places.setdefault(row_id, []).append(f"{name} fila {position + 2}")
    return places


def review_path_for(result_path) -> Path:
    """RF-36, RF-71: el resultado más "_revision"; si ya existe, "_revision (2)", "(3)"… sin reemplazar nada."""
    result = Path(result_path)
    candidate = result.with_name(f"{result.stem}_revision.xlsx")
    number = 2
    while candidate.exists():
        candidate = result.with_name(f"{result.stem}_revision ({number}).xlsx")
        number += 1
    return candidate


def save_pair(result_path, write_result, write_review=None) -> tuple:
    """
    Guarda el resultado y el Excel de revisión juntos o ninguno (RF-80,
    Decisión #8): los dos se escriben primero en archivos temporales de la
    misma carpeta (`write_result` y `write_review` reciben la ruta) y solo
    al final reemplazan a los definitivos. Si algo falla o se cancela, se
    borran los temporales; si falla el segundo reemplazo, se deshace el
    primero (vuelve el resultado anterior, si había). Devuelve (ruta del
    resultado, ruta de la revisión). Con `write_review=None` (un resultado
    sin estandarización, como los de la spec 001) guarda solo el resultado,
    también por un temporal, y la ruta de la revisión es None (T17).
    """
    result = Path(result_path)
    review = review_path_for(result) if write_review is not None else None
    temp_result = result.with_name(f"~tmp_{result.stem}.xlsx")
    temp_review = result.with_name(f"~tmp_{review.stem}.xlsx") if review is not None else None
    backup = result.with_name(f"~bak_{result.stem}.xlsx")
    try:
        write_result(temp_result)
        if review is not None:
            write_review(temp_review)
        had_result = result.exists()
        if had_result:
            os.replace(result, backup)
        try:
            os.replace(temp_result, result)
            if review is not None:
                os.replace(temp_review, review)
        except BaseException:
            if had_result:
                os.replace(backup, result)
            elif result.exists():
                result.unlink()
            raise
        if had_result:
            backup.unlink(missing_ok=True)
    finally:
        temp_result.unlink(missing_ok=True)
        if temp_review is not None:
            temp_review.unlink(missing_ok=True)
    return result, review
