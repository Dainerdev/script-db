from dataclasses import dataclass, field

import pandas as pd

from src.review_excel import ReviewData


@dataclass
class ValidationResult:
    sheet_ok: bool
    missing_columns: list[str]
    can_continue: bool  # False solo si sheet_ok es False


@dataclass
class DiagnosticSummary:
    total_rows: int
    rows_with_extra_spaces: int
    nulls_by_key_column: dict[str, int]
    duplicated_rows: int
    ids_with_name_variants: int
    duplicated_ius: int
    fuzzy_similar_names: int


@dataclass
class ProcessResult:
    sheets: dict[str, pd.DataFrame]
    counts: dict[str, int]
    source_path: str
    # Spec 002 (T16): lo que hace falta para guardar el Excel de revisión y
    # avisar de los pendientes. Con valores por defecto, para que un
    # ProcessResult de la spec 001 (solo hojas) siga siendo válido.
    review: ReviewData | None = None                     # RF-36 a RF-43
    highlights: dict = field(default_factory=dict)       # RF-40: hoja → celdas a pintar
    pending_values: int = 0                              # RF-50
    pending_rows: int = 0                                # RF-50
    missing_columns: list[str] = field(default_factory=list)   # RF-53
