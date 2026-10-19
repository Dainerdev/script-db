from datetime import datetime

import pytest

from src import parameters as p

NOMBRES = "NOMBRES_APELLIDOS"
FUNCIONARIO = "FUNCIONARIO A CARGO"

# Los nombres de NOMBRES_APELLIDOS son inventados, con cédulas inventadas
# (principio 6). Los de MAGISTRADO son los ejemplos de la spec: magistrados,
# funcionarios públicos, no comparecientes.


def classify(counts, column="MAGISTRADO", cedulas=None):
    return p.classify_catalog_column(counts, column, cedulas)


# ---------------------------------------------------------------------
# Typos en nombres: nunca automáticos (RF-9, RF-11, RF-12, RF-84)
# ---------------------------------------------------------------------

def test_nombre_de_90_o_mas_queda_pendiente_con_sugerencia():
    # 95,2: en una categoría se corregiría solo; en un nombre, no (RF-12).
    r = classify({"MARCELA VALERIO MUÑOZ": 10, "Marcelo Valerio Muñoz": 1})

    marcelo = r.outcomes["Marcelo Valerio Muñoz"]
    assert (marcelo.final, marcelo.state, marcelo.suggestion) == (
        "Marcelo Valerio Muñoz", p.REVIEW, "MARCELA VALERIO MUÑOZ"
    )
    assert marcelo.motive == "error de tipeo"
    assert marcelo.similarity >= 90
    assert r.outcomes["MARCELA VALERIO MUÑOZ"].state is None


def test_nombre_entre_80_y_89_queda_pendiente_con_sugerencia():
    r = classify({"ANA MANUELA PARRA ARIAS": 10, "ANA MANUELA PARRA": 2})

    corto = r.outcomes["ANA MANUELA PARRA"]
    assert (corto.state, corto.suggestion, corto.motive) == (
        p.REVIEW, "ANA MANUELA PARRA ARIAS", "similitud 80–89"
    )


def test_nombre_solo_con_formato_se_corrige_solo_sin_tildes():
    r = classify({"José Wilmer Cardona Sánchez": 5})

    assert r.outcomes["José Wilmer Cardona Sánchez"] == p.Outcome(
        "JOSE WILMER CARDONA SANCHEZ", p.AUTOMATIC, "formato"
    )


def test_nombre_sin_enie_queda_pendiente_con_la_enie_como_sugerencia():
    r = classify({"CARLOS MUNOZ": 10, "CARLOS MUÑOZ": 2}, FUNCIONARIO)

    munoz = r.outcomes["CARLOS MUNOZ"]
    assert (munoz.state, munoz.suggestion, munoz.motive) == (p.REVIEW, "CARLOS MUÑOZ", "error de tipeo")
    assert r.outcomes["CARLOS MUÑOZ"].state is None


def test_nombre_con_digitos_es_otra_categoria():
    r = classify({"JUAN PEREZ": 3, "JUAN PEREZ 2": 1}, NOMBRES)

    # Cambio 5 (RF-20): POR DETERMINAR, sin quedar pendiente.
    assert r.outcomes["JUAN PEREZ 2"] == p.Outcome("POR DETERMINAR", p.AUTOMATIC, "otra categoría")


def test_fecha_en_un_nombre_es_otra_categoria():
    fecha = datetime(2021, 3, 1)
    r = classify({"JUAN PEREZ": 3, fecha: 1}, NOMBRES)

    assert r.outcomes[fecha] == p.Outcome("POR DETERMINAR", p.AUTOMATIC, "otra categoría")   # cambio 5


# ---------------------------------------------------------------------
# Cédulas compartidas con el valor del catálogo (RF-13)
# ---------------------------------------------------------------------

def test_variante_con_la_cedula_del_valor_del_catalogo_se_corrige_sola():
    r = classify(
        {"JUAN PEREZ": 5, "JUAN PERES": 1},
        NOMBRES,
        {"JUAN PEREZ": {"12345678": 5}, "JUAN PERES": {12345678.0: 1}},
    )

    peres = r.outcomes["JUAN PERES"]
    assert (peres.final, peres.state, peres.motive) == ("JUAN PEREZ", p.AUTOMATIC, "error de tipeo")
    assert not peres.pending


@pytest.mark.parametrize("cedulas_peres", [
    None,                                   # sin cédulas
    {"SIN CC": 1},                          # no es una cédula
    {"12345678": 1, "87654321": 1},         # una fila con otra cédula
])
def test_sin_todas_las_cedulas_compartidas_la_variante_queda_pendiente(cedulas_peres):
    cedulas = {"JUAN PEREZ": {"12345678": 5}}
    if cedulas_peres:
        cedulas["JUAN PERES"] = cedulas_peres

    r = classify({"JUAN PEREZ": 5, "JUAN PERES": 2}, NOMBRES, cedulas)

    peres = r.outcomes["JUAN PERES"]
    assert (peres.state, peres.suggestion) == (p.REVIEW, "JUAN PEREZ")


def test_cedulas_compartidas_solo_cuentan_en_nombres_apellidos():
    r = classify(
        {"JUAN PEREZ": 5, "JUAN PERES": 1},
        FUNCIONARIO,
        {"JUAN PEREZ": {"12345678": 5}, "JUAN PERES": {"12345678": 1}},
    )

    assert r.outcomes["JUAN PERES"].state == p.REVIEW


# ---------------------------------------------------------------------
# Misma cédula con un nombre muy distinto (RF-65)
# ---------------------------------------------------------------------

def test_misma_cedula_con_nombre_distinto_deja_pendiente_el_de_menos_filas():
    r = classify(
        {"JUAN PEREZ": 5, "PEDRO GOMEZ": 1},
        NOMBRES,
        {"JUAN PEREZ": {"12345678": 5}, "PEDRO GOMEZ": {"12345678": 1}},
    )

    pedro = r.outcomes["PEDRO GOMEZ"]
    assert (pedro.final, pedro.state, pedro.suggestion) == ("PEDRO GOMEZ", p.REVIEW, "JUAN PEREZ")
    assert pedro.motive == "misma cédula con nombres distintos"
    assert pedro.similarity < 80
    assert not r.outcomes["JUAN PEREZ"].pending


@pytest.mark.parametrize("cedulas_pedro, filas_pedro", [
    ({"12345678": 1, "99999999": 1}, 2),    # dos cédulas distintas: no es "una misma"
    ({"12345678": 5}, 5),                   # la cédula no aparece en MÁS filas con el otro
])
def test_misma_cedula_sin_las_condiciones_no_deja_pendiente(cedulas_pedro, filas_pedro):
    r = classify(
        {"JUAN PEREZ": 5, "PEDRO GOMEZ": filas_pedro},
        NOMBRES,
        {"JUAN PEREZ": {"12345678": 5}, "PEDRO GOMEZ": cedulas_pedro},
    )

    assert not r.outcomes["PEDRO GOMEZ"].pending


def test_misma_cedula_en_el_mismo_grupo_no_se_sugiere_a_si_mismo():
    # "JUAN CARLO PERES" entra al grupo de "JUAN CARLOS PEREZ" (90,9), cuyo
    # valor del catálogo es el más completo, "JUAN CARLOS PEREZ GOMEZ"
    # (76,9 con él). Comparten la cédula y "JUAN CARLO PERES" tiene más
    # filas: RF-65 no aplica dentro del mismo grupo (sugeriría el mismo
    # valor del catálogo); la variante se corrige por RF-13.
    r = classify(
        {"JUAN CARLOS PEREZ": 10, "JUAN CARLOS PEREZ GOMEZ": 1, "JUAN CARLO PERES": 3},
        NOMBRES,
        {"JUAN CARLOS PEREZ GOMEZ": {"12345678": 1}, "JUAN CARLO PERES": {"12345678": 3}},
    )

    assert r.outcomes["JUAN CARLOS PEREZ GOMEZ"] == p.Outcome("JUAN CARLOS PEREZ GOMEZ")
    assert r.outcomes["JUAN CARLO PERES"].final == "JUAN CARLOS PEREZ GOMEZ"


# ---------------------------------------------------------------------
# No es una persona (RF-30, RF-57)
# ---------------------------------------------------------------------

def test_sala_plena_se_marca_como_no_persona():
    r = classify({"Sala Plena": 5, "ANA PEREZ ROJAS": 2})

    assert r.outcomes["Sala Plena"] == p.Outcome("SALA PLENA", p.AUTOMATIC, "formato", not_a_person=True)
    assert not r.outcomes["ANA PEREZ ROJAS"].not_a_person


@pytest.mark.parametrize("original, final", [
    ("PROCESOS ARCHIVADOS POR FUNCIONARIOS RETIRADOS", "PROCESOS ARCHIVADOS POR FUNCIONARIOS RETIRADOS"),
    ("ARCHIVADO - DEVOLUCIÓN - NO MISIONAL", "ARCHIVADO - DEVOLUCION - NO MISIONAL"),
])
def test_funcionario_que_no_es_persona_se_marca_sin_perder_sus_palabras(original, final):
    r = classify({original: 10, "LUIS GOMEZ": 3}, FUNCIONARIO)

    outcome = r.outcomes[original]
    assert (outcome.final, outcome.not_a_person) == (final, True)
    assert not outcome.pending


@pytest.mark.parametrize("value, column, expected", [
    ("SALA PLENA", "MAGISTRADO", True),
    ("Subsección Segunda", "MAGISTRADO", True),
    ("PETICIONARIO", "MAGISTRADO", True),
    ("NO APLICA", "MAGISTRADO", True),
    ("LUIS GOMEZ SALAS", "MAGISTRADO", False),      # SALAS es un apellido, no SALA
    ("ANA CORTES", "MAGISTRADO", False),
    ("PROCESOS ARCHIVADOS", FUNCIONARIO, True),
    ("SALA PLENA", NOMBRES, False),                 # en nombres los asuntos van por RF-28
    (None, "MAGISTRADO", False),
])
def test_definicion_de_no_es_una_persona(value, column, expected):
    assert p.is_not_a_person(value, column) is expected


def test_no_persona_pendiente_tambien_lleva_la_marca():
    # "SALA PLEANA" es un tipeo leve de SALA PLENA: desde el cambio 5 se
    # unifica sola (RF-85). "SALA PLENO" (PLENO / PLENA, 80) sigue pendiente.
    r = classify({"SALA PLENA": 10, "SALA PLEANA": 1, "SALA PLENO": 1})

    pleana = r.outcomes["SALA PLEANA"]
    assert (pleana.final, pleana.state, pleana.not_a_person) == ("SALA PLENA", p.AUTOMATIC, True)
    pleno = r.outcomes["SALA PLENO"]
    assert pleno.pending and pleno.not_a_person


# ---------------------------------------------------------------------
# Dos magistrados en una celda (RF-31)
# ---------------------------------------------------------------------

def test_dos_magistrados_en_una_celda_quedan_pendientes_en_una_sola_fila():
    celda = "GLORIA ESTELA PENALOZA RINCON JOSE WILMER CARDONA SANCHEZ"
    r = classify({
        "GLORIA ESTELA PEÑALOZA RINCON": 10,
        "JOSE WILMER CARDONA SANCHEZ": 8,
        celda: 1,
    })

    assert r.outcomes[celda] == p.Outcome(celda, p.REVIEW, "varios magistrados")
    assert r.outcomes["JOSE WILMER CARDONA SANCHEZ"].state is None


def test_dos_magistrados_con_y_entre_ellos():
    celda = "Ana Perez Rojas y Luis Gomez Diaz"
    r = classify({"ANA PEREZ ROJAS": 4, "LUIS GOMEZ DIAZ": 3, celda: 1})

    assert r.outcomes[celda].motive == "varios magistrados"


@pytest.mark.parametrize("counts", [
    # un nombre completo que contiene un nombre corto conocido
    {"PATRICIA LINO PRIETO": 5, "PATRICIA LINO": 3},
    # dos nombres conocidos que se solapan son la misma persona
    {"ANA MARIA PEREZ": 2, "MARIA PEREZ GOMEZ": 2, "ANA MARIA PEREZ GOMEZ": 1},
])
def test_un_solo_magistrado_no_es_varios(counts):
    r = classify(counts)

    assert all(o.motive != "varios magistrados" for o in r.outcomes.values())


def test_varios_magistrados_solo_en_magistrado():
    celda = "ANA PEREZ ROJAS LUIS GOMEZ DIAZ"
    r = classify({"ANA PEREZ ROJAS": 4, "LUIS GOMEZ DIAZ": 3, celda: 1}, FUNCIONARIO)

    assert r.outcomes[celda].motive != "varios magistrados"
