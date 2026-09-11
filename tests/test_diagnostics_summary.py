import pandas as pd

from gui.diagnostics_summary import build_summary


def _df_completo():
    return pd.DataFrame({
        "No": [1, 2, 3, 4, 5, 1],
        "RADICADO IUS": ["A-2020-001", "A-2020-001", "B-2020-002", "C-2020-003", "D-2020-004", "A-2020-001"],
        "IDENTIFICACIÓN": ["10000001", "10000001", "10000002", "10000002", "10000003", "10000001"],
        "NOMBRES_APELLIDOS": [
            "JUAN PEREZ GOMEZ", "JUAN PEREZ GOMEZ", "MARIA LOPEZ RUIZ",
            "MARIA L RUIZ", "JUAN PEREZ GOMES", "JUAN PEREZ GOMEZ",
        ],
        "FECHA": ["2020-01-01", None, "2020-01-03", "2020-01-04", "2020-01-05", "2020-01-01"],
        "REPARTO": ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-04", "2020-01-05", "2020-01-01"],
        "CLASIFICACIÓN DEL RADICADO": ["ACTIVO", "ARCHIVADO", "ARCHIVADO", "SIM", "ACTIVO", "ACTIVO"],
        "FUNCIONARIO A CARGO": [
            "JUAN PEREZ", "MARIA LOPEZ", "FUNCIONARIOS RETIRADOS",
            "JUAN PEREZ", "MARIA LOPEZ", "JUAN PEREZ",
        ],
        "MAGISTRADO": ["PEDRO SUAREZ", "PEDRO SUAREZ", "ANA TORRES", "ANA TORRES", "PEDRO SUAREZ", "PEDRO SUAREZ"],
        "OBSERVACIONES": ["sin novedad", "  espacio inicial", "espacio final  ", "normal", "normal", "sin novedad"],
    })


def test_build_summary_produces_seven_correct_fields():
    resumen = build_summary(_df_completo())

    assert resumen.total_rows == 6
    assert resumen.rows_with_extra_spaces == 2          # filas 1 y 2 (índice 0), por OBSERVACIONES
    assert resumen.nulls_by_key_column["FECHA"] == 1
    assert resumen.nulls_by_key_column["REPARTO"] == 0
    assert len(resumen.nulls_by_key_column) == 9         # las 9 columnas esperadas, todas presentes
    assert resumen.duplicated_rows == 2                  # fila 0 y su copia exacta (fila 5)
    assert resumen.ids_with_name_variants == 1            # cédula 10000002: 2 nombres distintos
    assert resumen.duplicated_ius == 1                    # A-2020-001 con 2 "No" distintos
    assert resumen.fuzzy_similar_names == 1                # GOMEZ / GOMES


def test_build_summary_degrades_gracefully_with_missing_columns():
    df = pd.DataFrame({
        "NOMBRES_APELLIDOS": ["JUAN PEREZ GOMEZ", "JUAN PEREZ GOMES"],
        "OBSERVACIONES": ["normal", "normal"],
    })
    resumen = build_summary(df)

    assert resumen.total_rows == 2
    assert resumen.duplicated_ius == 0
    assert resumen.ids_with_name_variants == 0
    assert resumen.fuzzy_similar_names == 1
    assert resumen.nulls_by_key_column == {"NOMBRES_APELLIDOS": 0}
