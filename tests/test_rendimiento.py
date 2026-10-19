"""T20: tiempo con el corte del 5 de agosto (requisito no funcional, Decisión #13). Solo con -m datos_reales."""
import time
from pathlib import Path

import pandas as pd
import pytest

from src import pipeline
from src import review_excel as rx

REPO = Path(__file__).resolve().parent.parent
BASE = REPO / "data" / "original" / "Base de datos Delegadas JEP corte 5 agosto.xlsx"
REVISADA = REPO / "data" / "original" / "parametros_unificados_revisados_AHRV_13102026.xlsx"
LIMITE_PROCESAR = 600         # "termina en 10 minutos o menos en el equipo de desarrollo" (cambio 9: "Procesar")
TOPE_PUNTA_A_PUNTA = 900      # cambio 9: con el guardado, tope contra retrocesos (dio 653 s el 2026-10-19)


@pytest.mark.datos_reales
@pytest.mark.skipif(not (BASE.exists() and REVISADA.exists()), reason="faltan los archivos reales")
def test_datos_reales_procesar_en_10_minutos_y_guardar_en_menos_de_15(tmp_path):
    # Como lo vive el funcionario: leer, "Procesar" con la tabla del
    # supervisor (cada valor contra todo el catálogo, sin atajos) y guardar el
    # resultado con el Excel de revisión. Los archivos quedan en tmp_path
    # (datos personales: nunca en el repo, principio 6).
    tiempos = {}
    inicio = time.perf_counter()
    df = pd.read_excel(BASE, sheet_name="Reparto", engine="calamine")
    revision = rx.read_review(REVISADA)
    tiempos["leer"] = time.perf_counter() - inicio

    marca = time.perf_counter()
    resultado = pipeline.run(df, table=revision.table, decisions=revision.decisions)
    tiempos["procesar"] = time.perf_counter() - marca

    marca = time.perf_counter()
    pipeline.save(resultado, tmp_path / "resultado.xlsx", style_reference_path=BASE)
    tiempos["guardar"] = time.perf_counter() - marca
    total = time.perf_counter() - inicio
    print({etapa: f"{segundos:.0f} s" for etapa, segundos in tiempos.items()}, f"total {total:.0f} s")

    assert len(resultado.records) == 219768
    assert (tmp_path / "resultado_revision.xlsx").exists()
    procesar = tiempos["leer"] + tiempos["procesar"]
    assert procesar <= LIMITE_PROCESAR, f"«Procesar» tardó {procesar:.0f} s: más de 10 minutos"
    assert total <= TOPE_PUNTA_A_PUNTA, f"de punta a punta tardó {total:.0f} s: más de 15 minutos"
