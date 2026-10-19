"""Escritura y lectura del Excel de revisión, ubicaciones y guardado en par (spec 002)."""
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from python_calamine import CalamineError
from xlsxwriter.utility import xl_col_to_name

from src.exportation import PENDING_FILL
from src.parameters import (
    CEDULA_AS_IS, DECIDED, DECISION_ACCEPT, DECISION_KEEP, EMPTY_TO_UNDETERMINED, OBSERVATION, PENDING_RESULT,
    REPLACED, REVIEW, TO_CONFIRM, UNCHANGED, Decisions, ReviewedTable, canonical_column,
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
# "Decisión" va al lado de la sugerencia (cambio 10): es la columna que llena el funcionario. read_review
# busca las columnas por nombre, así que un Excel con el orden anterior se sigue cargando.
TABLE_COLUMNS = ["Columna", "Valor original", "Valor final o sugerido", DECISION_COLUMN, "Similitud", "Motivo",
                 "Estado", "Filas afectadas", "Ubicación"]
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
    rows = [[entry.column, entry.original, entry.final, entry.decision or "",
             "" if entry.similarity is None else f"{entry.similarity:.1f}", entry.motive, entry.state,
             str(len(entry.row_ids)), _locations(entry.row_ids, data.locations)]
            for entry in ordered]
    if data.decisions is not None:                                                    # RF-46
        written = {(entry.column, entry.original, entry.decision) for entry in data.entries if entry.decision}
        for column, original, text in data.decisions.table:
            key = (_text(column).strip(), _text(original).strip(), _text(text))
            if key not in written:
                written.add(key)
                rows.append([key[0], _text(original), "", key[2], "", "decisión", DECIDED, "0", ""])
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


README_SHEET = "Léeme"
_STATE_FILLS = {REVIEW: PENDING_FILL, TO_CONFIRM: "#DDEBF7", DECIDED: "#E2EFDA"}      # RF-97
_DECISION_HELP = ("Elija ACEPTAR (usar el valor sugerido) o MANTENER (dejar el valor como estaba), o escriba "
                  "el valor correcto. Para separar nombres: las partes separadas por « | ».")
_CORRECTION_HELP = ("Escriba el valor correcto: cambia este valor y todas sus variantes en el resultado. "
                    "Déjelo vacío si el valor está bien.")


def _formats(book) -> dict:
    """Estilo de la lista de parámetros de la reunión (RF-97): encabezado azul oscuro, texto arriba."""
    header = {"bold": True, "font_color": "#FFFFFF", "text_wrap": True, "valign": "top", "border": 1}
    return {
        "header": book.add_format({**header, "bg_color": "#1F4E78"}),
        "to_fill": book.add_format({**header, "bg_color": "#548235"}),     # columnas que llena el funcionario
        "top": book.add_format({"valign": "top"}),
        "wrap": book.add_format({"valign": "top", "text_wrap": True}),
        "right": book.add_format({"valign": "top", "align": "right"}),        # cifras (escritas como texto)
        "title": book.add_format({"bold": True, "font_size": 14}),
        "label": book.add_format({"bold": True, "valign": "top"}),
        **{state: book.add_format({"bg_color": color}) for state, color in _STATE_FILLS.items()},
    }


def _styled_sheet(writer, name, rows, columns, widths, fmt, freeze=(1, 0), wrap=(), to_fill=(), right=()):
    """Escribe una hoja como texto (Decisión #11) con encabezado de color, anchos, fila fija y filtro (RF-97)."""
    pd.DataFrame(rows, columns=columns, dtype=object).to_excel(writer, sheet_name=name, index=False)
    sheet = writer.sheets[name]
    for col, title in enumerate(columns):
        sheet.write_string(0, col, title, fmt["to_fill"] if title in to_fill else fmt["header"])
    for col, width in enumerate(widths):
        sheet.set_column(col, col, width, fmt["wrap"] if col in wrap else fmt["right"] if col in right else fmt["top"])
    sheet.set_row(0, 30)
    sheet.freeze_panes(*freeze)
    sheet.autofilter(0, 0, len(rows), len(columns) - 1)
    # Todo va como texto a propósito (Decisión #11): sin el triángulo verde de "número guardado como texto".
    sheet.ignore_errors({"number_stored_as_text": f"A1:{xl_col_to_name(len(columns) - 1)}{len(rows) + 1}"})
    return sheet


def _readme_rows(data: ReviewData) -> list:
    """RF-97: qué es el archivo, cuánto quedó pendiente, colores y cómo decidir y cargar."""
    pending = [entry for entry in data.entries if entry.state == REVIEW]
    values = len({(entry.column, entry.original) for entry in pending})
    rows = len({row_id for entry in pending for row_id in entry.row_ids})
    pendientes = (f"Pendientes de revisión: {values:,} {'valor' if values == 1 else 'valores'} en {rows:,} "
                  f"{'fila' if rows == 1 else 'filas'}. Están en amarillo en la «{TABLE_SHEET}» y en el resultado."
                  if values else "No quedaron valores pendientes de revisión.")
    lines = [
        ("Qué es", "La lista de los valores que el programa cambió o dejó pendientes al estandarizar el "
                   "resultado, para que usted los revise y decida."),
        ("Pendientes", pendientes),
        ("Colores", "En la «Tabla de estandarización»: amarillo = PARA REVISAR (lo decide usted; en el "
                    "resultado esas celdas también están en amarillo) · azul = POR CONFIRMAR (código de SALA "
                    "nuevo) · verde = DECIDIDO (ya tiene una decisión) · sin color = el programa lo cambió solo."),
        ("Cómo decidir", f"En la columna «{DECISION_COLUMN}» elija de la lista ACEPTAR (usar el valor sugerido) "
                         "o MANTENER (dejar el valor como estaba), o escriba el valor correcto. Las filas sin "
                         "decisión no cambian nada."),
        ("Separar nombres", f"Para separar una celda con varios nombres, escriba en «{DECISION_COLUMN}» las "
                            "partes separadas por « | ». Ejemplo: ANA RUIZ DIAZ | LUIS MORA PAZ."),
        ("Corregir el catálogo", f"En las hojas «{CATALOG_PREFIX}…», escriba en «{CORRECTION_COLUMN}» el valor "
                                 "correcto: cambia ese valor y todas sus variantes."),
        ("Aplicar las decisiones", "Guarde y cierre este archivo. En el programa: «Seleccionar archivo» (la base "
                                   "original) → «Cargar revisión…» → elija este archivo. Sale un resultado nuevo con "
                                   "sus decisiones y un Excel de revisión nuevo que las conserva."),
        ("Hojas", f"{TABLE_SHEET}: lo que cambió o quedó pendiente, valor por valor. {SUMMARY_SHEET}: cifras por "
                  f"columna, verificación de totales y separación de comparecientes. {CATALOG_PREFIX}…: los "
                  f"valores finales de cada columna. {MAPEO_SHEET}: la tabla de parámetros revisada por el "
                  "supervisor, si se aplicó."),
        ("Datos personales", "Este archivo tiene nombres e identificaciones de comparecientes: no lo envíe ni lo "
                             "suba a plataformas externas."),
    ]
    if data.saved_as:
        lines.append(("Este archivo", data.saved_as))
    return lines


def _write_readme(book, data: ReviewData, fmt) -> None:
    sheet = book.add_worksheet(README_SHEET)
    sheet.set_column(0, 0, 26)
    sheet.set_column(1, 1, 110)
    sheet.write_string(0, 0, "Excel de revisión — Limpieza de base de datos (Procuraduría/JEP)", fmt["title"])
    for row, (label, text) in enumerate(_readme_rows(data), start=2):
        sheet.write_string(row, 0, label, fmt["label"])
        sheet.write_string(row, 1, text, fmt["wrap"])


def write_review(path, data: ReviewData) -> None:
    """
    Escribe el Excel de revisión: la hoja "Léeme" (RF-97), la tabla de
    estandarización con "Decisión" vacía (salvo las decisiones copiadas) y su
    lista ACEPTAR/MANTENER (RF-98), el Resumen, una hoja de catálogo por
    columna con "Corregir a" y, si se aplicó una tabla revisada, la hoja
    "Mapeo" (RF-36 a RF-39, RF-42, RF-43, RF-46, RF-96). Todo como texto
    (Decisión #11), así la clave (columna, valor original) vuelve igual; el
    estilo no cambia las columnas que lee `read_review`.
    """
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        fmt = _formats(writer.book)
        _write_readme(writer.book, data, fmt)

        rows = _table_rows(data)
        sheet = _styled_sheet(writer, TABLE_SHEET, rows, TABLE_COLUMNS, [20, 36, 36, 30, 9, 24, 15, 9, 40], fmt,
                              freeze=(1, 2), wrap=(1, 2, 5), to_fill=(DECISION_COLUMN,), right=(4, 7))
        if rows:
            last, state_col = len(rows), chr(ord("A") + TABLE_COLUMNS.index("Estado"))
            for state in _STATE_FILLS:                                                  # RF-97
                sheet.conditional_format(1, 0, last, len(TABLE_COLUMNS) - 1, {
                    "type": "formula", "criteria": f'=${state_col}2="{state}"', "format": fmt[state]})
            decision_col = TABLE_COLUMNS.index(DECISION_COLUMN)
            sheet.data_validation(1, decision_col, last, decision_col, {                 # RF-98
                "validate": "list", "source": [DECISION_ACCEPT, DECISION_KEEP], "show_error": False,
                "input_title": DECISION_COLUMN, "input_message": _DECISION_HELP})

        _styled_sheet(writer, SUMMARY_SHEET, _summary_rows(data), SUMMARY_COLUMNS, [26, 24, 70, 12, 12], fmt,
                      wrap=(2,), right=(3, 4))
        for column, catalog in data.catalogs.items():
            rows = _catalog_rows(column, catalog, data.decisions)
            sheet = _styled_sheet(writer, f"{CATALOG_PREFIX}{column}"[:31], rows, CATALOG_COLUMNS, [50, 10, 40],
                                  fmt, wrap=(0,), to_fill=(CORRECTION_COLUMN,), right=(1,))
            if rows:
                sheet.data_validation(1, 2, len(rows), 2, {
                    "validate": "any", "input_title": CORRECTION_COLUMN, "input_message": _CORRECTION_HELP})
        if data.table is not None:
            write_mapeo_sheet(writer, data.table, fmt)


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


def write_mapeo_sheet(writer: pd.ExcelWriter, table: ReviewedTable, fmt=None) -> None:
    """
    Copia la tabla de parámetros revisados completa, como texto, en la hoja
    "Mapeo" del Excel de revisión (RF-96): así, al volver a cargar ese Excel,
    se aplican la tabla y las decisiones nuevas (RF-89).
    """
    _styled_sheet(writer, MAPEO_SHEET, table.rows, MAPEO_COLUMNS, [24, 50, 50],
                  fmt if fmt is not None else _formats(writer.book), wrap=(1, 2))


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
