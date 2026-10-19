from datetime import datetime

import pytest

from src import parameters as p

TIPO = "TIPO DE EXPEDIENTE"


def test_listas_fijas_de_la_spec():
    assert p.FIXED_LISTS == {
        "TIPO DE EXPEDIENTE": ["FÍSICO", "ELECTRÓNICO", "HÍBRIDO", "POR DETERMINAR"],
        "DELEGADA": ["COORDINACIÓN", "1 DELEGADA", "2 DELEGADA", "3 DELEGADA"],
    }


# ---------------------------------------------------------------------
# TIPO DE EXPEDIENTE (RF-3, RF-9, RF-10, RF-18, RF-19, RF-66)
# ---------------------------------------------------------------------

@pytest.mark.parametrize("original, final", [
    ("ELECTRONICO", "ELECTRÓNICO"),
    ("FISICO ", "FÍSICO"),
    ("hibrido", "HÍBRIDO"),
])
def test_tipo_formato_se_corrige_solo(original, final):
    r = p.classify_fixed_list(original, TIPO)

    assert (r.final, r.state, r.motive) == (final, p.AUTOMATIC, "formato")


def test_tipo_valor_ya_correcto_no_genera_cambio():
    r = p.classify_fixed_list("ELECTRÓNICO", TIPO)

    assert (r.final, r.state) == ("ELECTRÓNICO", None)


def test_tipo_typo_de_90_o_mas_se_corrige_solo():
    r = p.classify_fixed_list("ELECTRONCO", TIPO)

    assert (r.final, r.state, r.motive) == ("ELECTRÓNICO", p.AUTOMATIC, "error de tipeo")
    assert r.similarity >= 90


@pytest.mark.parametrize("original", ["agendada", 44317, 44468.0076, datetime(2021, 3, 1), "siri"])
def test_tipo_valor_de_otra_columna_queda_por_determinar(original):
    r = p.classify_fixed_list(original, TIPO)

    assert (r.final, r.state, r.motive) == ("POR DETERMINAR", p.AUTOMATIC, "otra categoría")


@pytest.mark.parametrize("vacio", [None, float("nan"), "", "   ", "\xa0"])
def test_tipo_vacio_queda_por_determinar(vacio):
    r = p.classify_fixed_list(vacio, TIPO)

    assert (r.final, r.state, r.motive) == ("POR DETERMINAR", p.AUTOMATIC, "vacío")


@pytest.mark.parametrize("original", ["FISICO Y ELECTRONICO", "Electrónico / Físico"])
def test_tipo_fisico_y_electronico_es_hibrido(original):
    r = p.classify_fixed_list(original, TIPO)

    assert (r.final, r.state, r.motive) == ("HÍBRIDO", p.AUTOMATIC, "dos tipos en una celda")


# ---------------------------------------------------------------------
# DELEGADA (RF-4, RF-9, RF-10, RF-17, RF-21, RF-81)
# ---------------------------------------------------------------------

@pytest.mark.parametrize("original, final", [
    ("2 Delegada", "2 DELEGADA"),
    ("3 DELEGADA ", "3 DELEGADA"),
    ("cOORDINACIÓN", "COORDINACIÓN"),
    ("COORDINACION", "COORDINACIÓN"),
])
def test_delegada_formato_se_corrige_solo(original, final):
    r = p.classify_fixed_list(original, "DELEGADA")

    assert (r.final, r.state, r.motive) == (final, p.AUTOMATIC, "formato")


@pytest.mark.parametrize("original, final", [
    ("2DELEGADA", "2 DELEGADA"),
    ("COORDINACON", "COORDINACIÓN"),
])
def test_delegada_typo_de_90_o_mas_con_los_mismos_numeros(original, final):
    r = p.classify_fixed_list(original, "DELEGADA")

    assert (r.final, r.state, r.motive) == (final, p.AUTOMATIC, "error de tipeo")


def test_delegada_con_otro_numero_queda_pendiente_sin_sugerencia():
    # "4 DELEGADA" da 90 con 1, 2 y 3 DELEGADA, pero son otras dependencias
    # (RF-17): no se reemplaza ni se sugiere una de ellas.
    r = p.classify_fixed_list("4 DELEGADA", "DELEGADA")

    assert (r.final, r.state, r.suggestion) == ("4 DELEGADA", p.REVIEW, "")
    assert r.motive == "otra categoría"


def test_delegada_parecida_entre_80_y_89_queda_pendiente_con_sugerencia():
    r = p.classify_fixed_list("COORDINAC", "DELEGADA")

    assert (r.final, r.state, r.suggestion) == ("COORDINAC", p.REVIEW, "COORDINACIÓN")
    assert r.motive == "similitud 80–89"
    assert 80 <= r.similarity < 90


@pytest.mark.parametrize("vacio", [None, "", "\xa0"])
def test_delegada_vacia_es_por_determinar(vacio):
    # Cambio 6 (RF-21): antes quedaba vacía sin marca.
    r = p.classify_fixed_list(vacio, "DELEGADA")

    assert (r.final, r.state, r.motive) == ("POR DETERMINAR", p.AUTOMATIC, "vacío")


# ---------------------------------------------------------------------
# Vacíos en las demás columnas (RF-21)
# ---------------------------------------------------------------------

@pytest.mark.parametrize("column", ["SOLICITUD", "MAGISTRADO", "SALA", "IDENTIFICACIÓN"])
def test_vacio_en_las_demas_columnas_es_por_determinar(column):
    # Cambio 6 (RF-21): antes quedaba vacío sin marca.
    r = p.empty_outcome(column)

    assert (r.final, r.state, r.motive) == ("POR DETERMINAR", p.AUTOMATIC, "vacío")


def test_vacio_en_tipo_de_expediente_es_por_determinar():
    r = p.empty_outcome(TIPO)

    assert (r.final, r.state, r.motive) == ("POR DETERMINAR", p.AUTOMATIC, "vacío")
