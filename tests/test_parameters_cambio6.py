"""Cambio 6 de la spec 002, T25: vacíos a POR DETERMINAR (RF-21) y cédulas por persona (RF-94)."""
import pytest

from src import parameters as p

VACIOS = [None, float("nan"), "", "   ", "\xa0"]
POR_DETERMINAR = ("POR DETERMINAR", p.AUTOMATIC, "vacío")


def _resumen(outcome):
    return outcome.final, outcome.state, outcome.motive


# ---------------------------------------------------------------------
# RF-21: una celda vacía de cualquier columna estandarizada → POR DETERMINAR
# ---------------------------------------------------------------------

@pytest.mark.parametrize("column", ["SOLICITUD", "DECISIÓN", "PERTENECE", "SALA", "MAGISTRADO",
                                    "FUNCIONARIO A CARGO", "NOMBRES_APELLIDOS", "IDENTIFICACIÓN",
                                    "DELEGADA", "TIPO DE EXPEDIENTE"])
def test_vacio_es_por_determinar_en_todas_las_columnas(column):
    r = p.empty_outcome(column)

    assert _resumen(r) == POR_DETERMINAR
    assert not r.pending


@pytest.mark.parametrize("vacio", VACIOS)
@pytest.mark.parametrize("column", ["SOLICITUD", "MAGISTRADO", "NOMBRES_APELLIDOS"])
def test_vacio_en_columna_de_catalogo(column, vacio):
    r = p.classify_catalog_column({vacio: 4, "REQUERIMIENTO": 1}, column)

    assert _resumen(r.outcomes[vacio]) == POR_DETERMINAR


@pytest.mark.parametrize("vacio", VACIOS)
def test_vacio_en_identificacion(vacio):
    assert _resumen(p.classify_identification(vacio)) == POR_DETERMINAR


@pytest.mark.parametrize("vacio", VACIOS)
def test_vacio_en_delegada(vacio):
    assert _resumen(p.classify_fixed_list(vacio, "DELEGADA")) == POR_DETERMINAR


# ---------------------------------------------------------------------
# RF-94: las reglas de cédulas de un nombre solo cuentan filas con una sola cédula
# ---------------------------------------------------------------------

GRUPO = "11111111\n22222222"


def test_dos_nombres_que_solo_comparten_un_grupo_no_quedan_pendientes_por_rf65():
    # Separados de la misma celda, cada uno lleva el grupo completo (RF-22).
    counts = {"JUAN PEREZ": 3, "MARIA GOMEZ": 5}
    cedulas = {"JUAN PEREZ": {GRUPO: 3}, "MARIA GOMEZ": {GRUPO: 5}}

    r = p.classify_catalog_column(counts, "NOMBRES_APELLIDOS", cedulas)

    assert not r.outcomes["JUAN PEREZ"].pending
    assert not r.outcomes["MARIA GOMEZ"].pending


def test_variante_cuya_unica_fila_trae_varias_cedulas_no_se_corrige_por_rf13():
    # Con la cédula sola, JUAN PERES pasaría a JUAN PEREZ por RF-13; con el
    # grupo no hay ninguna fila de una sola cédula y queda por RF-12.
    counts = {"JUAN PEREZ": 50, "JUAN PERES": 1}
    cedulas = {"JUAN PEREZ": {"11111111": 50}, "JUAN PERES": {GRUPO: 1}}

    r = p.classify_catalog_column(counts, "NOMBRES_APELLIDOS", cedulas)

    assert r.outcomes["JUAN PERES"].pending
    assert r.outcomes["JUAN PERES"].suggestion == "JUAN PEREZ"


def test_la_misma_variante_con_la_cedula_sola_si_se_corrige_por_rf13():
    counts = {"JUAN PEREZ": 50, "JUAN PERES": 1}
    cedulas = {"JUAN PEREZ": {"11111111": 50}, "JUAN PERES": {"11111111": 1}}

    r = p.classify_catalog_column(counts, "NOMBRES_APELLIDOS", cedulas)

    assert _resumen(r.outcomes["JUAN PERES"])[:2] == ("JUAN PEREZ", p.AUTOMATIC)
