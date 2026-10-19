from datetime import datetime

import pandas as pd
import pytest

from src import parameters as p


def classify(counts, column="DECISIÓN"):
    return p.classify_catalog_column(counts, column)


# ---------------------------------------------------------------------
# Categorías: formato, typos, 80–89 y valor propio (RF-9, RF-10, RF-11, RF-14)
# ---------------------------------------------------------------------

def test_rewquerimiento_se_corrige_solo():
    r = classify({"REQUERIMIENTO": 10, "Rewquerimiento": 1})

    rew = r.outcomes["Rewquerimiento"]
    assert (rew.final, rew.state, rew.motive) == ("REQUERIMIENTO", p.AUTOMATIC, "error de tipeo")
    assert rew.similarity >= 90
    assert r.outcomes["REQUERIMIENTO"].state is None


def test_devolucion_y_sus_variantes_quedan_con_tilde():
    # Las variantes de la captura de Dainer: formato y un typo de 94,7.
    r = classify({"DEVOLUCION": 10, "Devolución": 2, "Devoución": 1}, "SOLICITUD")

    assert r.outcomes["DEVOLUCION"] == p.Outcome("DEVOLUCIÓN", p.AUTOMATIC, "formato")
    assert r.outcomes["Devolución"] == p.Outcome("DEVOLUCIÓN", p.AUTOMATIC, "formato")
    typo = r.outcomes["Devoución"]
    assert (typo.final, typo.state, typo.motive) == ("DEVOLUCIÓN", p.AUTOMATIC, "error de tipeo")


def test_par_entre_80_y_89_queda_pendiente_con_sugerencia():
    r = classify({"AGENDADO": 10, "agendada": 2})

    agendada = r.outcomes["agendada"]
    assert (agendada.final, agendada.state, agendada.suggestion) == ("agendada", p.REVIEW, "AGENDADO")
    assert agendada.motive == "similitud 80–89"
    assert 80 <= agendada.similarity < 90
    assert agendada.pending


def test_valor_sin_parecido_es_valor_propio_del_catalogo():
    r = classify({"REQUERIMIENTO": 10, "Audiencia": 5})

    assert r.outcomes["Audiencia"] == p.Outcome("AUDIENCIA", p.AUTOMATIC, "formato")


def test_negacion_no_se_reemplaza_por_su_contrario():
    # 92,7 de similitud, pero RF-82 los deja en grupos distintos.
    r = classify({"AVOCAR CONOCIMIENTO": 10, "NO AVOCAR CONOCIMIENTO": 3})

    assert r.outcomes["NO AVOCAR CONOCIMIENTO"] == p.Outcome("NO AVOCAR CONOCIMIENTO")


# ---------------------------------------------------------------------
# Cambio 3: variante <80 con el valor del catálogo de su grupo (RF-84)
# ---------------------------------------------------------------------

def test_variante_menor_que_80_con_su_valor_del_catalogo_queda_pendiente():
    # "TRASLADO PGN" entra al grupo que abre "TRASLADAR PGN" (88), pero el
    # valor del catálogo es la variante más completa (RF-62), con la que
    # solo tiene 73,3.
    r = classify({"TRASLADAR PGN": 100, "TRASLADAR A LA PGN": 5, "Traslado PGN": 3})

    traslado = r.outcomes["Traslado PGN"]
    assert (traslado.final, traslado.state, traslado.suggestion) == (
        "Traslado PGN", p.REVIEW, "TRASLADAR A LA PGN"
    )
    assert traslado.motive == "similitud menor que 80"
    assert traslado.similarity < 80
    # Cambio 5 (RF-85): "TRASLADAR PGN" solo se diferencia en partículas del
    # valor del catálogo: es muy obvio y ya no queda pendiente.
    apertura = r.outcomes["TRASLADAR PGN"]
    assert (apertura.final, apertura.state, apertura.motive) == (
        "TRASLADAR A LA PGN", p.AUTOMATIC, "error de tipeo"
    )


# ---------------------------------------------------------------------
# Otra categoría y vacíos (RF-20, RF-21)
# ---------------------------------------------------------------------

TO_DETERMINE = p.Outcome("POR DETERMINAR", p.AUTOMATIC, "otra categoría")


@pytest.mark.parametrize("original", [0, "0", 44317.0, "007-2025", "15/03/2021", datetime(2021, 3, 1)])
def test_valor_de_otra_categoria_queda_por_determinar(original):
    # Cambio 5 (RF-20): antes quedaba pendiente con su texto; ahora se
    # escribe POR DETERMINAR y no cuenta como pendiente.
    r = classify({"POR REVISAR": 10, original: 5}, "PERTENECE")

    assert r.outcomes[original] == TO_DETERMINE
    assert not r.outcomes[original].pending


def test_valor_de_otra_categoria_no_entra_a_los_grupos():
    # Si "0" armara un grupo, "00" sería su variante de formato; así, cada
    # uno queda por su cuenta como POR DETERMINAR.
    r = classify({0: 5, "00": 1}, "PERTENECE")

    assert r.outcomes["00"] == TO_DETERMINE


@pytest.mark.parametrize("vacio", [None, "   ", "\xa0"])
def test_vacio_en_categoria_es_por_determinar(vacio):
    # Cambio 6 (RF-21): antes quedaba vacío sin marca.
    r = classify({vacio: 4, "REQUERIMIENTO": 1})

    assert r.outcomes[vacio] == p.Outcome("POR DETERMINAR", p.AUTOMATIC, "vacío")


# ---------------------------------------------------------------------
# SALA: formato y POR CONFIRMAR sin color ni conteo (RF-9, RF-15, RF-16, RF-56)
# ---------------------------------------------------------------------

def test_sala_formato_y_codigos_por_confirmar():
    r = classify({"SAI": 5, "sai": 1, "SR": 3, "SRV": 2}, "SALA")

    assert r.outcomes["sai"] == p.Outcome("SAI", p.AUTOMATIC, "formato")
    assert r.outcomes["SR"] == p.Outcome("SR")
    assert r.outcomes["SRV"] == p.Outcome("SRV")
    assert set(r.to_confirm) == {"SAI", "SR", "SRV"}
    for code, outcome in r.to_confirm.items():
        assert outcome == p.Outcome(code, p.TO_CONFIRM, "confirmar código de SALA")


def test_sala_por_confirmar_no_cuenta_como_pendiente():
    r = classify({"SAI": 5, "sai": 1, "SR": 3, "SRV": 2}, "SALA")

    assert not any(o.pending for o in r.outcomes.values())
    assert not any(o.pending for o in r.to_confirm.values())


def test_sala_solo_con_digitos_es_otra_categoria_y_no_se_confirma():
    r = classify({"SR": 3, "1": 2}, "SALA")

    assert r.outcomes["1"] == TO_DETERMINE        # cambio 5 (RF-20)
    assert set(r.to_confirm) == {"SR"}


def test_categoria_no_tiene_codigos_por_confirmar():
    r = classify({"REQUERIMIENTO": 10, "Rewquerimiento": 1})

    assert r.to_confirm == {}


def test_acepta_el_conteo_de_pandas():
    counts = pd.Series(["SAI", "sai", "SAI", None]).value_counts(dropna=False)

    r = classify(counts, "SALA")

    assert r.outcomes["sai"].final == "SAI"
    assert set(r.to_confirm) == {"SAI"}


# ---------------------------------------------------------------------
# Definición "valor de otra categoría"
# ---------------------------------------------------------------------

@pytest.mark.parametrize("value, column, expected", [
    ("0", "PERTENECE", True),
    ("007-2025", "SOLICITUD", True),
    (44317, "SALA", True),
    ("REQUERIMIENTO 2", "SOLICITUD", False),
    ("SA", "SALA", False),
    (datetime(2021, 3, 1), "DECISIÓN", True),
    (pd.Timestamp("2021-03-01"), "MAGISTRADO", True),
    ("JUAN PEREZ 2", "MAGISTRADO", True),
    ("JUAN PEREZ", "NOMBRES_APELLIDOS", False),
    (None, "PERTENECE", False),
    (pd.NaT, "PERTENECE", False),
])
def test_definicion_de_valor_de_otra_categoria(value, column, expected):
    assert p.is_other_category(value, column) is expected


def test_pendiente_es_solo_para_revisar():
    assert p.Outcome("X", p.REVIEW, "otra categoría").pending
    assert not p.Outcome("X", p.TO_CONFIRM, "confirmar código de SALA").pending
    assert not p.Outcome("X", p.AUTOMATIC, "formato").pending
    assert not p.Outcome("X").pending
