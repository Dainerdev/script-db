"""Secuencia única del proceso, compartida por la GUI y main.py (spec 002, Decisiones #4 y #17)."""
import dataclasses
from dataclasses import dataclass

import pandas as pd

from src.comparecientes import NAMES, separate
from src.diagnostic import extract_multi_ius, run_similarity_report, split_by_status
from src.exportation import ExportCancelled, export_multi_sheet_excel
from src.parameters import (
    AUTOMATIC, DECIDED, DECISION_KEEP, REVIEW, Decisions, TableEntry, add_observation_column, add_original_columns,
    standardize_parameters,
)
from src.review_excel import (
    ReviewData, highlight_cells, locations_by_row, public_frame, review_path_for, save_pair, separation_counts,
    write_review,
)
from src.standardization import add_radicado_ius_revisada, clean_and_standardize
from src.text_keys import COLUMN_TYPES, to_text

# Etapas de la barra de progreso (RF-6 de la spec 001; RF-52 suma la de parámetros).
STAGE_CLEAN = "Limpiando y estandarizando..."
STAGE_PARAMETERS = "Estandarizando parámetros..."
STAGE_DUPLICATES = "Analizando duplicados..."
STAGE_SPLIT = "Separando registros..."
STAGES = (STAGE_CLEAN, STAGE_PARAMETERS, STAGE_DUPLICATES, STAGE_SPLIT)

# Hojas del resultado: grupo de split_by_status → nombre de la hoja.
_STATUS_SHEETS = (("activos", "Reparto_Activo"), ("archivados", "Archivados"),
                  ("retirados", "Funcionarios_Retirados"), ("sim", "SIM"))
MULTI_IUS_SHEET = "Multiples_IUS"
_DECIDED_MOTIVE = "decisión"


class ProcessCancelled(Exception):
    """El funcionario canceló: no hay resultado ni Excel de revisión (RF-55)."""


@dataclass
class PipelineResult:
    """Lo que deja "Procesar": las hojas listas para guardar y todo lo del Excel de revisión."""
    sheets: dict                # hoja → DataFrame sin columnas internas
    highlights: dict            # RF-40: hoja → celdas a pintar, (posición de la fila, encabezado)
    review: ReviewData          # tabla, resumen, totales, catálogos, ubicaciones…
    records: pd.DataFrame       # todas las filas ya separadas, con `_row_id`, `_marks`, `_pending`…
    missing_columns: list       # columnas estandarizadas que faltan en el archivo (RF-53)

    @property
    def counts(self) -> dict:
        return {name: len(sheet) for name, sheet in self.sheets.items()}

    @property
    def pending_values(self) -> int:
        """RF-50: pares (columna, valor original) PARA REVISAR."""
        return len({(entry.column, entry.original) for entry in self.review.entries if entry.state == REVIEW})

    @property
    def pending_rows(self) -> int:
        """RF-50: filas del resultado (ya separadas) con algún valor pendiente."""
        return sum(1 for pending in self.records["_pending"] if pending) if "_pending" in self.records else 0


def run(df, table=None, decisions: Decisions | None = None, on_stage=None,
        should_cancel=lambda: False) -> PipelineResult:
    """
    Procesa el DataFrame leído en el orden del cambio 6 (RF-51, Decisión
    #17): columnas _ORIGINAL (RF-87) → limpieza → parámetros de las filas
    originales salvo NOMBRES_APELLIDOS, con la verificación de totales
    (RF-92) → separar comparecientes → NOMBRES_APELLIDOS sobre las filas ya
    separadas → duplicados → separación por estado. `table` es la tabla de
    parámetros revisados y `decisions` las decisiones cargadas (de
    `review_excel.read_review`). `on_stage(texto)` recibe cada etapa (RF-52).
    `should_cancel()` se revisa entre etapas y entre columnas; si da True,
    lanza ProcessCancelled y no hay resultado (RF-55). Si los totales no
    cuadran, lanza parameters.TotalsMismatchError.
    """
    def check(*_):
        if should_cancel():
            raise ProcessCancelled()

    def stage(text):
        check()
        if on_stage is not None:
            on_stage(text)

    stage(STAGE_CLEAN)
    df = df.reset_index(drop=True)
    df = df.assign(_row_id=range(len(df)))
    df = clean_and_standardize(add_original_columns(df))

    stage(STAGE_PARAMETERS)
    parameters = standardize_parameters(df, table=table, columns=[c for c in COLUMN_TYPES if c != NAMES],
                                        decisions=decisions, before_column=check)
    check()
    separated = separate(parameters.df, decisions=decisions)
    check()
    names = standardize_parameters(_with_separation_marks(separated), columns=[NAMES],
                                   decisions=_names_decisions(decisions, separated.applied_decisions),
                                   check_columns=False, separation_suggestions=separated.pending,
                                   before_column=check)
    records = add_observation_column(names.df)

    stage(STAGE_DUPLICATES)
    run_similarity_report(records)

    stage(STAGE_SPLIT)
    groups = split_by_status(records)
    internal = {name: add_radicado_ius_revisada(groups[key]).reset_index(drop=True) for key, name in _STATUS_SHEETS}
    internal[MULTI_IUS_SHEET] = add_radicado_ius_revisada(extract_multi_ius(records)).reset_index(drop=True)
    review = ReviewData(
        entries=[*parameters.entries, *_separation_entries(separated.traces, decisions), *names.entries],
        summary=_in_column_order({**parameters.summary, **names.summary}),
        totals=parameters.totals,
        catalogs=_in_column_order({**parameters.catalogs, **names.catalogs}),
        separation=separation_counts(records),
        unmatched_decisions=(parameters.unmatched_decisions + names.unmatched_decisions
                             + _unapplied_separations(decisions, separated.applied_decisions)),
        invalid_decisions=[*(table.problems() if table is not None else []),               # RF-89
                           *parameters.invalid_decisions, *names.invalid_decisions],
        decisions=decisions,
        table=table,
        locations=locations_by_row(internal),
    )
    result = PipelineResult(
        sheets={name: public_frame(sheet) for name, sheet in internal.items()},
        highlights=highlight_cells(internal),
        review=review,
        records=records,
        missing_columns=[column for column in COLUMN_TYPES
                         if column in {*parameters.missing_columns, *names.missing_columns}],
    )
    check()
    return result


def save(result, output_path, style_reference_path=None, on_sheet_start=None, on_sheet_done=None,
         should_cancel=lambda: False, before_review=None) -> tuple:
    """
    Guarda el resultado y el Excel de revisión juntos o ninguno (RF-36,
    RF-80; T19: una sola función para la GUI y main.py, así los dos guardan
    lo mismo). `result` es un PipelineResult o un ProcessResult de la GUI
    (usa `sheets`, `highlights` y `review`); sin `review` (spec 001) guarda
    solo el resultado. El resultado lleva las celdas pendientes pintadas
    (RF-40) y el estilo de `style_reference_path`; el Resumen del Excel de
    revisión dice con qué nombre quedó (RF-71). `on_sheet_start`,
    `on_sheet_done` y `should_cancel` pasan a `export_multi_sheet_excel`;
    `should_cancel` también se revisa antes de la revisión (ExportCancelled)
    y `before_review()` avisa que empieza. Devuelve (ruta del resultado,
    ruta de la revisión o None).
    """
    review = result.review
    # Se calcula una vez, en el mismo momento en que save_pair elige la ruta.
    review_name = review_path_for(output_path).name if review is not None else ""

    def write_result(path):
        export_multi_sheet_excel(
            sheets=result.sheets,
            file_path=path,
            style_reference_path=style_reference_path,
            style_reference_sheet="Reparto",
            raise_errors=True,
            on_sheet_start=on_sheet_start,
            on_sheet_done=on_sheet_done,
            should_cancel=should_cancel,
            highlight_cells=result.highlights or None,
        )

    def write_review_file(path):
        if should_cancel():
            raise ExportCancelled("Cancelado antes de guardar el Excel de revisión.")
        if before_review is not None:
            before_review()
        write_review(path, dataclasses.replace(review, saved_as=review_name))

    return save_pair(output_path, write_result, write_review_file if review is not None else None)


def _with_separation_marks(separated) -> pd.DataFrame:
    """Suma a `_marks` de cada persona las marcas de la separación ("no es una persona", "Y OTROS"…)."""
    df = separated.df
    marks = [tuple(dict.fromkeys([*row, *sorted(separated.marks.get((row_id, person), ()))]))
             for row, row_id, person in zip(df["_marks"], df["_row_id"], df["_person"])]
    return df.assign(_marks=marks)


def _names_decisions(decisions, applied) -> Decisions | None:
    """
    Decisiones para la pasada de NOMBRES_APELLIDOS: sin las que ya separaron
    una celda (su texto ya no está en ninguna fila y contarían como sin
    coincidencia, RF-77). MANTENER se queda: la celda sigue entera y la
    decisión la protege de la estandarización.
    """
    if decisions is None:
        return None
    table = [row for row in decisions.table
             if not (to_text(row[0]).strip() == NAMES and to_text(row[1]).strip() in applied
                     and to_text(row[2]).strip().upper() != DECISION_KEEP)]
    return Decisions(table=table, catalog=decisions.catalog)


def _unapplied_separations(decisions, applied) -> int:
    """RF-77: decisiones "parte | parte" cuya celda no está en el archivo (la pasada de nombres no las mira)."""
    if decisions is None:
        return 0
    keys = {to_text(value).strip() for column, value, text in decisions.table
            if to_text(column).strip() == NAMES and "|" in to_text(text)}
    return len(keys - set(applied))


def _separation_entries(traces, decisions) -> list:
    """RF-29, RF-68, RF-75: el rastro de la separación como entradas de la tabla de estandarización."""
    loaded = {}
    for column, value, text in (decisions.table if decisions is not None else []):
        if to_text(column).strip() == NAMES:
            loaded.setdefault(to_text(value).strip(), to_text(text))
    grouped = {}
    for trace in traces:
        decided = trace.motive == _DECIDED_MOTIVE
        key = (trace.original.strip(), trace.final, trace.motive)
        if key not in grouped:
            grouped[key] = TableEntry(NAMES, key[0], trace.final, None, trace.motive,
                                      DECIDED if decided else AUTOMATIC,
                                      decision=loaded.get(key[0]) if decided else None)
        grouped[key].row_ids.append(trace.row_id)
    return list(grouped.values())


def _in_column_order(by_column: dict) -> dict:
    """Por columna, en el orden de la spec (las dos pasadas dejarían los nombres al final)."""
    return {column: by_column[column] for column in COLUMN_TYPES if column in by_column}
