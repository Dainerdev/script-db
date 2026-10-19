from datetime import datetime

import pytest

from src import catalog, parameters as p
from src import text_keys as tk

# Cambio 5 de la spec 002 (T24): POR DETERMINAR (RF-20, RF-34), lo muy obvio
# (RF-85), los prefijos que niegan (RF-86) y la palabra repetida mal escrita
# (RF-62). Nombres y cédulas inventados (principio 6), salvo magistrados.

NOMBRES = "NOMBRES_APELLIDOS"
TO_DETERMINE = p.Outcome("POR DETERMINAR", p.AUTOMATIC, "otra categoría")


def classify(counts, column="DECISIÓN", cedulas=None):
    return p.classify_catalog_column(counts, column, cedulas).outcomes


# ---------------------------------------------------------------------
# text_keys: prefijos que niegan y diferencia muy obvia
# ---------------------------------------------------------------------

@pytest.mark.parametrize("a, b, expected", [
    ("DECLARAR EL CUMPLIMIENTO", "DECLARAR EL INCUMPLIMIENTO", True),
    ("ARCHIVAR EXPEDIENTE", "DESARCHIVAR EXPEDIENTE", True),
    ("DECLARAR PROCEDENTE", "DECLARAR IMPROCEDENTE", True),
    ("DECLARAR FUNDADO", "DECLARAR INFUNDADO", True),
    ("DCLARAR INCIMPLIMIENTO", "DECLARAR EL INCUMPLIMIENTO", False),   # los dos niegan
    ("AVOCAR CONOCIMIENTO", "AVOCAR EL CONOCIMIENTO", False),
])
def test_negates(a, b, expected):
    assert tk.negates(a, b) is expected


@pytest.mark.parametrize("a, b", [
    ("COMISIONAR UIA", "COMISIONAR A LA UIA"),          # solo partículas
    ("TERCEROS CIVILES", "TERCERO CIVIL"),              # singular/plural
    ("AVOCAR CONOCIMEINTO", "AVOCAR EL CONOCIMIENTO"),  # tipeo leve
    ("SALA PLEANA", "SALA PLENA"),
])
def test_diferencia_muy_obvia(a, b):
    assert tk.obvious_difference(a, b) is not None


@pytest.mark.parametrize("a, b", [
    ("MARCELO VALERIO MUNOZ", "MARCELA VALERIO MUNOZ"),        # 85,7: no es tipeo leve
    ("TRASLADO PGN", "TRASLADAR A LA PGN"),                    # 82: otra palabra
    ("ANA MANUELA PARRA", "ANA MANUELA PARRA ARIAS"),          # falta una palabra
    ("DECLARAR CUMPLIMIENTO", "DECLARAR EL INCUMPLIMIENTO"),   # prefijo que niega
    ("NO AVOCAR CONOCIMIENTO", "AVOCAR CONOCIMIENTO"),         # NO
    ("1 DELEGADA", "2 DELEGADA"),                              # números
])
def test_no_es_diferencia_muy_obvia(a, b):
    assert tk.obvious_difference(a, b) is None


# ---------------------------------------------------------------------
# catalog: prefijos que niegan (RF-86) y palabra repetida mal escrita (RF-62)
# ---------------------------------------------------------------------

def test_cumplimiento_e_incumplimiento_en_grupos_distintos():
    grupos = catalog.group({"DECLARAR EL INCUMPLIMIENTO": 10, "Declarar el cumplimiento": 5}, "DECISIÓN")

    assert grupos["DECLARAR EL CUMPLIMIENTO"] == "DECLARAR EL CUMPLIMIENTO"


def test_no_se_une_a_un_grupo_donde_ya_esta_su_contrario():
    # INDEFINIDA no niega a la apertura (DEFINITIVA) sino a DEFINIDA, que ya
    # está en el grupo (hallado en la revisión de OpenCode, 2026-10-13).
    counts = {
        "SUSPENDER LA AUDIENCIA HASTA LA RESUELTA DEFINITIVA": 100,
        "SUSPENDER LA AUDIENCIA HASTA LA RESUELTA DEFINIDA": 50,
        "SUSPENDER LA AUDIENCIA HASTA LA RESUELTA INDEFINIDA": 10,
    }
    grupos = catalog.group(counts, "DECISIÓN")

    indefinida = "SUSPENDER LA AUDIENCIA HASTA LA RESUELTA INDEFINIDA"
    assert grupos[indefinida] == indefinida
    assert p.classify_catalog_column(counts, "DECISIÓN").outcomes[indefinida].final == indefinida


def test_palabra_repetida_mal_escrita_no_es_mas_completa():
    valor = catalog.representative(
        {"Luis Eduardo Benitez Benitez": 3000, "LUIS EDUARDO BENITEZ BENITJEZ": 6}, "MAGISTRADO"
    )

    assert valor == "LUIS EDUARDO BENITEZ BENITEZ"


@pytest.mark.parametrize("typo", ["LUIS EDUARDO BENITES BENITEZ", "LUIS EDUARDO BENITEZ BENITES"])
def test_repetida_con_una_letra_cambiada_tampoco(typo):
    # BENITES / BENITEZ se parecen 85,7: dentro del mismo valor es la misma
    # palabra repetida con un error, no un apellido más (visto con datos reales).
    valor = catalog.representative({"Luis Eduardo Benitez Benitez": 3000, typo: 1}, "MAGISTRADO")

    assert valor == "LUIS EDUARDO BENITEZ BENITEZ"


def test_palabra_de_verdad_nueva_sigue_haciendo_mas_completa():
    valor = catalog.representative({"ANA MANUELA PARRA ARIAS": 2, "ANA MANUELA PARRA": 10}, "MAGISTRADO")

    assert valor == "ANA MANUELA PARRA ARIAS"


# ---------------------------------------------------------------------
# parameters: POR DETERMINAR (RF-20) y lo muy obvio (RF-85)
# ---------------------------------------------------------------------

@pytest.mark.parametrize("column, value", [
    ("PERTENECE", 0),
    ("SOLICITUD", "007-2025"),
    ("SALA", "1"),
    ("MAGISTRADO", datetime(2021, 3, 1)),
    (NOMBRES, "JUAN PEREZ 2"),
])
def test_otra_categoria_queda_por_determinar_sin_pendiente(column, value):
    outcome = classify({value: 3, "OTRO VALOR CUALQUIERA": 5}, column)[value]

    assert outcome == TO_DETERMINE
    assert not outcome.pending


@pytest.mark.parametrize("counts, value, final", [
    ({"Comisionar UIA": 30, "COMISIONAR A LA UIA": 5}, "Comisionar UIA", "COMISIONAR A LA UIA"),
    ({"AVOCAR EL CONOCIMIENTO": 20, "Avocar conocimeinto": 3}, "Avocar conocimeinto", "AVOCAR EL CONOCIMIENTO"),
])
def test_lo_muy_obvio_se_unifica_solo(counts, value, final):
    outcome = classify(counts)[value]

    assert (outcome.final, outcome.state, outcome.motive) == (final, p.AUTOMATIC, "error de tipeo")


def test_lo_muy_obvio_en_un_nombre_tambien():
    outcome = classify({"SANDRA JEANNETTE CASTRO OSPINA": 50, "Sandra Jannette Castro Ospina": 10},
                       "MAGISTRADO")["Sandra Jannette Castro Ospina"]

    assert (outcome.final, outcome.state) == ("SANDRA JEANNETTE CASTRO OSPINA", p.AUTOMATIC)


def test_un_typo_que_no_es_leve_sigue_pendiente():
    outcome = classify({"MARCELA VALERIO MUÑOZ": 10, "Marcelo Valerio Muñoz": 1},
                       "MAGISTRADO")["Marcelo Valerio Muñoz"]

    assert outcome.pending


def test_lo_muy_obvio_no_se_une_si_las_cedulas_lo_contradicen():
    counts = {"ANA VILLAMARINO RUIZ": 5, "ANA VILLAMRINO RUIZ": 2}

    distintas = classify(counts, NOMBRES, {"ANA VILLAMARINO RUIZ": {"11111111": 5},
                                           "ANA VILLAMRINO RUIZ": {"22222222": 2}})
    sin_cedulas = classify(counts, NOMBRES)

    assert distintas["ANA VILLAMRINO RUIZ"].pending
    assert sin_cedulas["ANA VILLAMRINO RUIZ"].final == "ANA VILLAMARINO RUIZ"
    assert not sin_cedulas["ANA VILLAMRINO RUIZ"].pending


# ---------------------------------------------------------------------
# IDENTIFICACIÓN (RF-34): solo letras o error de Excel → POR DETERMINAR
# ---------------------------------------------------------------------

@pytest.mark.parametrize("original", ["No registra", "Medida Cautelar", "#¡VALOR!", "#N/A", "CASO"])
def test_identificacion_que_no_es_identificacion_queda_por_determinar(original):
    assert p.classify_identification(original) == TO_DETERMINE


@pytest.mark.parametrize("original", ["SC8076405", "TD 6149", "1812", "Caso 003 y 004", "12345678\nNo registra"])
def test_identificacion_dudosa_sigue_pendiente(original):
    outcome = p.classify_identification(original)

    assert (outcome.state, outcome.motive) == (p.REVIEW, "identificación inválida")
