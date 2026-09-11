from dataclasses import dataclass

import pandas as pd


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
