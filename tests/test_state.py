import pandas as pd

from gui.state import ValidationResult, DiagnosticSummary, ProcessResult


def test_validation_result_fields():
    r = ValidationResult(sheet_ok=True, missing_columns=["FECHA"], can_continue=True)
    assert r.sheet_ok is True
    assert r.missing_columns == ["FECHA"]
    assert r.can_continue is True


def test_diagnostic_summary_fields():
    d = DiagnosticSummary(
        total_rows=100,
        rows_with_extra_spaces=5,
        nulls_by_key_column={"FECHA": 2},
        duplicated_rows=1,
        ids_with_name_variants=3,
        duplicated_ius=4,
        fuzzy_similar_names=2,
    )
    assert d.total_rows == 100
    assert d.nulls_by_key_column == {"FECHA": 2}
    assert d.fuzzy_similar_names == 2


def test_process_result_fields():
    df = pd.DataFrame({"A": [1, 2]})
    p = ProcessResult(sheets={"Reparto_Activo": df}, counts={"Reparto_Activo": 2}, source_path="entrada.xlsx")
    assert p.sheets["Reparto_Activo"] is df
    assert p.counts["Reparto_Activo"] == 2
    assert p.source_path == "entrada.xlsx"
