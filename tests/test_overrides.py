"""T12: decisiones y correcciones de catálogo (RF-45, RF-46, RF-48, RF-58, RF-72 a RF-74, RF-77, RF-89). Datos sintéticos."""
import pandas as pd
import pytest

from src import comparecientes as c
from src import parameters as p

NAMES = "NOMBRES_APELLIDOS"


def _run(columna, valores, tabla=None, decisiones=(), correcciones=(), **kwargs):
    decisions = p.Decisions(table=list(decisiones), catalog=list(correcciones))
    return p.standardize_parameters(pd.DataFrame({columna: valores}), table=tabla, decisions=decisions, **kwargs)


def _entry(resultado, original):
    encontradas = [e for e in resultado.entries if e.original == original]
    assert len(encontradas) == 1, encontradas
    return encontradas[0]


# ---------------------------------------------------------------------
# ACEPTAR, MANTENER, otro texto (RF-45, RF-72, RF-74)
# ---------------------------------------------------------------------

def test_aceptar_sin_importar_mayusculas_ni_espacios_usa_la_sugerencia():
    r = _run("DECISIÓN", ["AGENDADO"] * 10 + ["agendada"] * 2, decisiones=[("DECISIÓN", "agendada", " aceptar ")])

    assert list(r.df["DECISIÓN"][-2:]) == ["AGENDADO", "AGENDADO"]
    entrada = _entry(r, "agendada")
    assert (entrada.final, entrada.state, entrada.motive, entrada.decision) == (
        "AGENDADO", p.DECIDED, "decisión", " aceptar ")
    assert all(pendientes == () for pendientes in r.df["_pending"])


def test_mantener_deshace_una_sustitucion_automatica():
    r = _run("SOLICITUD", ["REQUERIMIENTO"] * 5 + ["Rewquerimiento"],
             decisiones=[("SOLICITUD", "Rewquerimiento", "MANTENER")])

    assert r.df.loc[5, "SOLICITUD"] == "Rewquerimiento"
    assert _entry(r, "Rewquerimiento").state == p.DECIDED


def test_otro_texto_se_escribe_con_la_ortografia_de_la_columna():
    r = _run("MAGISTRADO", ["ANA PEREZ ROJAS"] * 5 + ["ANA PERES ROJAS"],
             decisiones=[("MAGISTRADO", "ANA PERES ROJAS", "Víctima Gómez")])

    assert r.df.loc[5, "MAGISTRADO"] == "VICTIMA GOMEZ"


# ---------------------------------------------------------------------
# Correcciones de catálogo (RF-58) y SALA POR CONFIRMAR (RF-73)
# ---------------------------------------------------------------------

def test_corregir_a_cambia_el_valor_del_catalogo_y_sus_variantes():
    r = _run("MAGISTRADO", ["ELSA MORA QUINTER"] * 3 + ["Elsa Mora Quintr"],
             correcciones=[("MAGISTRADO", "ELSA MORA QUINTER", "Elsy Mora Quintero")])

    assert set(r.df["MAGISTRADO"]) == {"ELSY MORA QUINTERO"}
    assert _entry(r, "ELSA MORA QUINTER").motive == "corrección de catálogo"


def test_codigo_de_sala_con_otro_texto_pasa_a_ser_variante():
    r = _run("SALA", ["SRVR"] * 5 + ["SARV"] * 2, decisiones=[("SALA", "SARV", "SARVR")])

    assert list(r.df["SALA"][-2:]) == ["SARVR", "SARVR"]
    por_confirmar = {e.original for e in r.entries if e.state == p.TO_CONFIRM}
    assert por_confirmar == {"SRVR"}


def test_codigo_de_sala_aceptado_queda_confirmado():
    r = _run("SALA", ["SRVR"] * 5, decisiones=[("SALA", "SRVR", "Aceptar")])

    assert not [e for e in r.entries if e.state == p.TO_CONFIRM]
    assert p.TO_CONFIRM not in r.summary["SALA"]["estados"]
    assert set(r.df["SALA"]) == {"SRVR"}


# ---------------------------------------------------------------------
# Decisiones que no se aplican (RF-48) y sin coincidencia (RF-46, RF-77)
# ---------------------------------------------------------------------

def test_valor_fuera_de_la_lista_fija_no_se_aplica_y_se_lista():
    r = _run("TIPO DE EXPEDIENTE", ["Fisico", "Digital"], decisiones=[("TIPO DE EXPEDIENTE", "Digital", "DIGITAL")])

    assert r.df.loc[1, "TIPO DE EXPEDIENTE"] == "POR DETERMINAR"
    assert len(r.invalid_decisions) == 1 and "Digital" in r.invalid_decisions[0]


def test_columna_inexistente_se_lista():
    r = _run("SOLICITUD", ["REQUERIMIENTO"], decisiones=[("COLUMNA RARA", "x", "y")])

    assert len(r.invalid_decisions) == 1 and "COLUMNA RARA" in r.invalid_decisions[0]


def test_columna_inexistente_no_se_revisa_en_la_segunda_pasada():
    r = _run(NAMES, ["ANA RUIZ"], decisiones=[("COLUMNA RARA", "x", "y")], columns=[NAMES], check_columns=False)

    assert r.invalid_decisions == []


def test_dos_decisiones_distintas_para_el_mismo_par_no_se_aplican():
    r = _run("SOLICITUD", ["REQUERIMIENTO"] * 5 + ["Rewquerimiento"],
             decisiones=[("SOLICITUD", "Rewquerimiento", "MANTENER"), ("SOLICITUD", "Rewquerimiento", "OTRA COSA")])

    assert r.df.loc[5, "SOLICITUD"] == "REQUERIMIENTO"
    assert len(r.invalid_decisions) == 1


def test_aceptar_sin_sugerencia_no_se_aplica_y_se_lista():
    r = _run("IDENTIFICACIÓN", ["SC8076405"], decisiones=[("IDENTIFICACIÓN", "SC8076405", "ACEPTAR")])

    assert r.df.loc[0, "_pending"] == ("IDENTIFICACIÓN",)
    assert len(r.invalid_decisions) == 1


def test_decision_de_otro_corte_cuenta_sin_coincidencia_y_se_conserva():
    decisiones = [("SOLICITUD", "Valor de otro corte", "X")]
    r = _run("SOLICITUD", ["REQUERIMIENTO"], decisiones=decisiones)

    assert r.unmatched_decisions == 1
    assert r.loaded_decisions.table == decisiones


# ---------------------------------------------------------------------
# Tabla revisada (cambio 6, RF-89)
# ---------------------------------------------------------------------

TABLA = p.ReviewedTable.from_rows([("SOLICITUD", "Devolucion", "DEVOLUCIÓN"), ("SOLICITUD", "OTRO", "OTRO")])


def test_una_decision_le_gana_a_la_tabla():
    r = _run("SOLICITUD", ["Devolucion", "Devolucion", "OTRO"], tabla=TABLA,
             decisiones=[("SOLICITUD", "Devolucion", "MANTENER")])

    assert list(r.df["SOLICITUD"]) == ["Devolucion", "Devolucion", "OTRO"]


def test_una_correccion_de_catalogo_cambia_lo_que_puso_la_tabla():
    r = _run("SOLICITUD", ["Devolucion", "Devolucion", "OTRO"], tabla=TABLA,
             correcciones=[("SOLICITUD", "DEVOLUCIÓN", "Devolución de expediente")])

    assert list(r.df["SOLICITUD"]) == ["DEVOLUCIÓN DE EXPEDIENTE", "DEVOLUCIÓN DE EXPEDIENTE", "OTRO"]


# ---------------------------------------------------------------------
# Segunda pasada: el original de un nombre es el de esa persona
# ---------------------------------------------------------------------

def test_decision_sobre_un_nombre_separado_no_toca_a_los_demas_de_la_celda():
    df = pd.DataFrame({NAMES: ["ANA RUIZ DIAZ", "LUIS MORA"], "NOMBRES_APELLIDOS_ORIGINAL": ["Ana Ruiz Diaz\nLuis Mora"] * 2})
    decisions = p.Decisions(table=[(NAMES, "LUIS MORA", "Luis Mora Paz")])

    r = p.standardize_parameters(df, decisions=decisions, columns=[NAMES])

    assert list(r.df[NAMES]) == ["ANA RUIZ DIAZ", "LUIS MORA PAZ"]


# ---------------------------------------------------------------------
# Decisiones de separar nombres (RF-39, RF-48 modificado)
# ---------------------------------------------------------------------

PEGADO = "Ana Ruiz Diaz Luis Mora Paz Eva Rios Gil"
PARTES = "Ana Ruiz Diaz | Luis Mora Paz | Eva Rios Gil"


def _separar(ident, decision):
    df = pd.DataFrame({NAMES: [PEGADO], "IDENTIFICACIÓN": [ident]})
    return c.separate(df, decisions=p.Decisions(table=[(NAMES, PEGADO, decision)]))


def test_separacion_decidida_con_otra_cantidad_de_cedulas_queda_sin_confirmar():
    r = _separar("11111111\n22222222", PARTES)

    assert list(r.df[NAMES]) == ["Ana Ruiz Diaz", "Luis Mora Paz", "Eva Rios Gil"]
    assert set(r.df["SEPARACIÓN"]) == {"SEPARADA SIN CONFIRMAR"}
    assert r.pending == {}
    assert c.Trace(0, PEGADO, PARTES, "decisión") in r.traces


def test_separacion_decidida_con_tantas_cedulas_queda_separada():
    r = _separar("11111111\n22222222\n33333333", PARTES)

    assert set(r.df["SEPARACIÓN"]) == {"SEPARADA"}


def test_mantener_una_celda_pendiente_de_separar_la_deja_en_una_fila_sin_pendiente():
    r = _separar("11111111\n22222222", "mantener")

    assert list(r.df[NAMES]) == [PEGADO]
    assert set(r.df["SEPARACIÓN"]) == {""}
    assert r.pending == {}
    assert r.marks == {}


def test_aceptar_una_celda_pendiente_usa_su_sugerencia():
    conocidos = pd.DataFrame({NAMES: ["Mario Andres Lopez Diaz", "Pedro Luis Ruiz Ruiz",
                                      "Mario Andres Lopez Diaz Pedro Luis Ruiz Ruiz"],
                              "IDENTIFICACIÓN": ["11111111", "22222222", ""]})
    decision = p.Decisions(table=[(NAMES, "Mario Andres Lopez Diaz Pedro Luis Ruiz Ruiz", "ACEPTAR")])

    r = c.separate(conocidos, decisions=decision)

    filas = r.df[r.df["ID REGISTRO"] == 3]
    assert list(filas[NAMES]) == ["MARIO ANDRES LOPEZ DIAZ", "PEDRO LUIS RUIZ RUIZ"]
    assert 2 not in r.pending


# T15: la tabla muestra la celda pendiente con su línea de persona (sin el
# asunto ni "Y OTROS"); la decisión escrita sobre ese texto también vale.

def test_decision_escrita_sobre_la_linea_de_persona_separa_la_celda():
    celda = "Solicitud de informe\n" + PEGADO
    df = pd.DataFrame({NAMES: [celda], "IDENTIFICACIÓN": ["11111111\n22222222\n33333333"]})

    r = c.separate(df, decisions=p.Decisions(table=[(NAMES, PEGADO, PARTES)]))

    assert list(r.df[NAMES]) == ["Ana Ruiz Diaz", "Luis Mora Paz", "Eva Rios Gil"]
    assert r.applied_decisions == {PEGADO}


def test_mantener_escrito_sobre_la_linea_de_persona_no_devuelve_el_asunto():
    df = pd.DataFrame({NAMES: [PEGADO + " y otros"], "IDENTIFICACIÓN": ["11111111\n22222222"]})

    r = c.separate(df, decisions=p.Decisions(table=[(NAMES, PEGADO, "MANTENER")]))

    assert list(r.df[NAMES]) == [PEGADO]
    assert r.pending == {}
