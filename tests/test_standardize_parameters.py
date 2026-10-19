"""T11: standardize_parameters (RF-1, RF-2, RF-37, RF-41, RF-42, RF-43, RF-53, RF-54, RF-56, RF-78). Datos sintéticos."""
import pandas as pd
import pytest

from src import parameters as p

TIPO_ENCABEZADO = "TIPO DE EXPEDIENTE\n(ELECTRONICO - HIBRIDO)"
NAMES = "NOMBRES_APELLIDOS"


def _df():
    return pd.DataFrame({
        "No": range(1, 9),
        TIPO_ENCABEZADO: ["Fisico", "ELECTRÓNICO", None, "ELECTRÓNICO", "FÍSICO", "FÍSICO", "ELECTRÓNICO", "FÍSICO"],
        "DELEGADA": ["1 DELEGADA"] * 8,
        "SALA": ["SRVR"] * 7 + ["srvr"],
        "SOLICITUD": ["DEVOLUCIÓN"] * 5 + ["Devoución", "DEVOLUCION", None],
        "DECISIÓN": ["AGENDADO"] * 6 + ["agendada", "0"],
        "PERTENECE": ["VICTIMA"] * 8,
        NAMES: ["ANA RUIZ DIAZ"] * 8,
        "MAGISTRADO": ["ANA PEREZ ROJAS"] * 6 + ["Sala Plena", "ANA PEREZ ROJAS"],
        "FUNCIONARIO A CARGO": ["LUIS MORA"] * 8,
        "IDENTIFICACIÓN": ["11111111"] * 7 + ["Caso 3"],
        "OBSERVACIONES": ["texto libre  sin tocar"] * 8,
    })


@pytest.fixture(scope="module")
def r():
    return p.standardize_parameters(_df())


def _entry(resultado, column, original):
    encontradas = [e for e in resultado.entries if e.column == column and e.original == original]
    assert len(encontradas) == 1, (column, original, encontradas)
    return encontradas[0]


# ---------------------------------------------------------------------
# Columnas: RF-1, RF-53, RF-54
# ---------------------------------------------------------------------

def test_las_columnas_no_estandarizadas_no_cambian(r):
    assert list(r.df["OBSERVACIONES"]) == list(_df()["OBSERVACIONES"])
    assert list(r.df["No"]) == list(range(1, 9))


def test_reconoce_tipo_de_expediente_con_texto_extra_en_el_encabezado(r):
    assert r.df.loc[0, TIPO_ENCABEZADO] == "FÍSICO"
    assert r.df.loc[2, TIPO_ENCABEZADO] == "POR DETERMINAR"


def test_sin_sala_se_omite_solo_sala():
    resultado = p.standardize_parameters(_df().drop(columns=["SALA"]))

    assert resultado.missing_columns == ["SALA"]
    assert not [e for e in resultado.entries if e.column == "SALA"]
    assert resultado.df.loc[5, "SOLICITUD"] == "DEVOLUCIÓN"


def test_columns_limita_las_columnas_que_se_estandarizan():
    resultado = p.standardize_parameters(_df(), columns=[NAMES])

    assert resultado.df.loc[6, "DECISIÓN"] == "agendada"
    assert resultado.df.loc[7, "DECISIÓN"] == "0"
    assert resultado.missing_columns == []
    assert set(resultado.totals) == set()


# ---------------------------------------------------------------------
# Tabla de estandarización: RF-37, RF-41
# ---------------------------------------------------------------------

def test_cada_sustitucion_tiene_su_entrada(r):
    tipeo = _entry(r, "SOLICITUD", "Devoución")
    assert (tipeo.final, tipeo.state, tipeo.motive, tipeo.row_ids) == ("DEVOLUCIÓN", p.AUTOMATIC, "error de tipeo", [5])
    assert tipeo.similarity >= 90

    assert _entry(r, "SOLICITUD", "").row_ids == [7]
    assert _entry(r, "SOLICITUD", "").motive == "vacío"
    assert (_entry(r, "TIPO DE EXPEDIENTE", "").final, _entry(r, "TIPO DE EXPEDIENTE", "").row_ids) == ("POR DETERMINAR", [2])
    assert _entry(r, "DECISIÓN", "0").motive == "otra categoría"
    assert _entry(r, "IDENTIFICACIÓN", "Caso 3").final == "CASO 003"


def test_los_pendientes_llevan_la_sugerencia_como_final(r):
    agendada = _entry(r, "DECISIÓN", "agendada")

    assert (agendada.final, agendada.state, agendada.motive, agendada.row_ids) == (
        "AGENDADO", p.REVIEW, "similitud 80–89", [6])


def test_un_cambio_solo_de_formato_no_tiene_entrada(r):
    assert not [e for e in r.entries if e.original in ("DEVOLUCION", "Fisico", "srvr")]


def test_codigo_de_sala_por_confirmar_con_todas_sus_filas(r):
    sala = _entry(r, "SALA", "SRVR")

    assert (sala.final, sala.state, sala.row_ids) == ("SRVR", p.TO_CONFIRM, list(range(8)))


# ---------------------------------------------------------------------
# Marcas, pendientes y observación: RF-56, RF-78
# ---------------------------------------------------------------------

def test_pendientes_por_fila_y_sala_por_confirmar_no_cuenta(r):
    assert r.df.loc[6, "_pending"] == ("DECISIÓN",)
    assert all(pendientes == () for i, pendientes in enumerate(r.df["_pending"]) if i != 6)


def test_la_observacion_junta_las_marcas_con_punto_y_coma(r):
    df = p.add_observation_column(r.df)

    assert df.loc[6, "Observación estandarización"] == "pendiente de revisión; no es una persona"
    assert df.loc[0, "Observación estandarización"] == ""
    assert df.columns[-1] == "Observación estandarización"


def test_las_marcas_que_ya_traia_la_fila_se_conservan():
    df = _df()
    df["_marks"] = [("hay más comparecientes sin nombrar",)] + [()] * 7

    resultado = p.standardize_parameters(df)

    assert resultado.df.loc[0, "_marks"] == ("hay más comparecientes sin nombrar",)
    assert resultado.df.loc[6, "_marks"] == ("pendiente de revisión", "no es una persona")


# ---------------------------------------------------------------------
# Catálogos y resumen: RF-2, RF-42, RF-43
# ---------------------------------------------------------------------

def test_catalogo_por_columna_sin_los_pendientes(r):
    solicitud = r.catalogs["SOLICITUD"]
    decision = r.catalogs["DECISIÓN"]

    assert list(solicitud.columns) == ["Valor", "Filas"]
    assert dict(zip(solicitud["Valor"], solicitud["Filas"])) == {"DEVOLUCIÓN": 7, "POR DETERMINAR": 1}
    assert dict(zip(decision["Valor"], decision["Filas"])) == {"AGENDADO": 6, "POR DETERMINAR": 1}


def test_resumen_cada_valor_en_un_solo_estado(r):
    decision = r.summary["DECISIÓN"]

    assert decision["estados"] == {p.SUMMARY_UNCHANGED: (1, 6), p.REVIEW: (1, 1), p.AUTOMATIC: (1, 1)}
    assert decision["otra categoría"] == (1, 1)
    for columna, datos in r.summary.items():
        assert sum(filas for _, filas in datos["estados"].values()) == 8, columna


def test_resumen_las_filas_cuentan_por_su_propio_estado():
    # "1 DELEGADA" no cambia y "1 DELEGADA " sí (DECIDIDO por la tabla): el
    # valor cuenta una vez, pero cada fila en su estado, como RF-92.
    df = pd.DataFrame({"DELEGADA": ["1 DELEGADA", "1 DELEGADA ", "1 DELEGADA "]})
    tabla = p.ReviewedTable.from_rows([("DELEGADA", "1 DELEGADA", "1 DELEGADA")])

    resultado = p.standardize_parameters(df, table=tabla)

    estados = resultado.summary["DELEGADA"]["estados"]
    assert sum(valores for valores, _ in estados.values()) == 1
    assert {estado: filas for estado, (_, filas) in estados.items()} == {p.SUMMARY_UNCHANGED: 1, p.DECIDED: 2}


def test_resumen_sala_por_confirmar_no_es_pendiente(r):
    assert r.summary["SALA"]["estados"] == {p.TO_CONFIRM: (2, 8)}


def test_totales_de_rf92_sin_nombres(r):
    assert NAMES not in r.totals
    assert all(sum(c.values()) == 8 for c in r.totals.values())


# ---------------------------------------------------------------------
# Tabla revisada (cambio 6): búsqueda con el texto original
# ---------------------------------------------------------------------

def test_con_tabla_revisada_busca_con_la_columna_original():
    df = _df()
    df.loc[5, "SOLICITUD"] = " Devolucion  "
    df = p.add_original_columns(df)
    df.loc[5, "SOLICITUD"] = "Devolucion"                # ya limpio por la spec 001
    tabla = p.ReviewedTable.from_rows([("SOLICITUD", "Devolucion", "DEVOLUCIÓN"), ("SALA", "SRVR", "SRVR"),
                                       ("SALA", "srvr", "SRVR")])

    resultado = p.standardize_parameters(df, table=tabla)

    entrada = _entry(resultado, "SOLICITUD", "Devolucion")
    assert (entrada.final, entrada.state, entrada.motive) == ("DEVOLUCIÓN", p.DECIDED, "decisión")
    assert not [e for e in resultado.entries if e.state == p.TO_CONFIRM]
    assert resultado.df.loc[5, "SOLICITUD_ORIGINAL"] == " Devolucion  "


# ---------------------------------------------------------------------
# Segunda pasada, solo NOMBRES_APELLIDOS (cambio 6, RF-25, RF-28)
# ---------------------------------------------------------------------

def test_nombres_sin_asuntos_ni_celdas_sin_separar_en_el_catalogo():
    df = pd.DataFrame({
        NAMES: ["Autorizacion De Recepcion De Informes", "Mario Lopez Diaz Pedro Ruiz Ruiz", "Ana Ruiz Diaz",
                "ANA RUIZ DIAZ"],
        "IDENTIFICACIÓN": ["CASO 003", "11111111\n22222222", "33333333", "33333333"],
        "SEPARACIÓN": ["", "SIN SEPARAR", "", ""],
        "_marks": [("no es una persona",), ("pendiente de revisión",), (), ()],
    })

    resultado = p.standardize_parameters(df, columns=[NAMES])

    assert resultado.df.loc[0, NAMES] == "AUTORIZACION DE RECEPCION DE INFORMES"
    assert resultado.df.loc[1, NAMES] == "MARIO LOPEZ DIAZ PEDRO RUIZ RUIZ"
    assert set(resultado.catalogs[NAMES]["Valor"]) == {"ANA RUIZ DIAZ"}
