"""T26: tabla de parámetros revisados, columnas _ORIGINAL y verificación de totales (cambio 6)."""
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

from src import parameters as p
from src import review_excel as rx

FINAL = "¿Unificar con? (valor final)"
FILAS = [
    ("SOLICITUD", "Devolucion", "DEVOLUCIÓN"),
    ("SOLICITUD", "", "POR DETERMINAR"),
    ("SALA", "SeRVR", "SeRVR"),
    ("SALA", "SRVR", "SRVR"),
    ("IDENTIFICACIÓN", "123456 y 654321", "123456\n654321"),
    ("IDENTIFICACIÓN", "C.C. 123456", "POR DETERMINAR"),
    ("DECISIÓN", "Archivar", "ARCHIVAR"),
    ("DECISIÓN", "Archivar", "ARCHIVO"),          # mismo original con dos finales
    ("TIPO DE EXPEDIENTE", "Digital", "DIGITAL"),  # fuera de la lista fija
    ("TIPO DE EXPEDIENTE", "Fisico", "FÍSICO"),
]


def _mapeo(filas=FILAS):
    return pd.DataFrame(filas, columns=["Columna", "Valor original", FINAL])


def _excel(tmp_path, hojas):
    ruta = Path(tmp_path) / "revisada.xlsx"
    with pd.ExcelWriter(ruta, engine="openpyxl") as escritor:
        for nombre, datos in hojas.items():
            datos.to_excel(escritor, sheet_name=nombre, index=False)
    return ruta


@pytest.fixture
def tabla():
    return p.ReviewedTable.from_rows(FILAS)


# ---------------------------------------------------------------------
# Lectura y escritura (RF-89, RF-96)
# ---------------------------------------------------------------------

def test_lee_la_hoja_mapeo(tmp_path):
    archivo = rx.read_review(_excel(tmp_path, {"Mapeo": _mapeo()}))

    assert archivo.table.lookup("SOLICITUD", "Devolucion") == "DEVOLUCIÓN"
    assert archivo.has_decisions is False
    assert archivo.decisions is None


def test_conflictos_y_finales_fuera_de_lista_no_se_aplican_y_se_listan(tabla):
    assert tabla.conflicts == [("DECISIÓN", "Archivar")]
    assert tabla.invalid == [("TIPO DE EXPEDIENTE", "Digital")]
    assert tabla.lookup("DECISIÓN", "Archivar") is None
    assert tabla.lookup("TIPO DE EXPEDIENTE", "Digital") is None
    assert tabla.lookup("TIPO DE EXPEDIENTE", "Fisico") == "FÍSICO"


def test_archivo_con_mapeo_y_tabla_de_estandarizacion_avisa_que_trae_decisiones(tmp_path):
    decisiones = pd.DataFrame({"Columna": ["SOLICITUD"], "Valor original": ["x"], "Decisión": ["ACEPTAR"]})
    archivo = rx.read_review(_excel(tmp_path, {"Mapeo": _mapeo(), "Tabla de estandarización": decisiones}))

    assert archivo.table is not None
    assert archivo.has_decisions is True


def test_archivo_solo_con_tabla_de_estandarizacion(tmp_path):
    decisiones = pd.DataFrame({"Columna": ["SOLICITUD"], "Valor original": ["x"], "Decisión": ["ACEPTAR"]})
    archivo = rx.read_review(_excel(tmp_path, {"Tabla de estandarización": decisiones}))

    assert archivo.table is None
    assert archivo.has_decisions is True


def test_archivo_sin_ninguna_de_las_dos_da_error_claro(tmp_path):
    with pytest.raises(rx.ReviewFileError, match="no es un Excel de revisión ni una tabla de parámetros revisados"):
        rx.read_review(_excel(tmp_path, {"Hoja1": pd.DataFrame({"A": [1]})}))


def test_mapeo_sin_sus_tres_columnas_no_cuenta_como_tabla(tmp_path):
    with pytest.raises(rx.ReviewFileError):
        rx.read_review(_excel(tmp_path, {"Mapeo": pd.DataFrame({"Columna": ["SALA"]})}))


def test_la_hoja_mapeo_escrita_y_vuelta_a_leer_da_la_misma_tabla(tmp_path, tabla):
    ruta = Path(tmp_path) / "revision.xlsx"
    with pd.ExcelWriter(ruta, engine="xlsxwriter") as escritor:
        rx.write_mapeo_sheet(escritor, tabla)

    leida = rx.read_review(ruta).table

    assert leida.rows == tabla.rows
    assert leida.finals == tabla.finals
    assert leida.conflicts == tabla.conflicts
    assert leida.invalid == tabla.invalid


def test_textos_como_numeros_vuelven_iguales(tmp_path):
    filas = [("IDENTIFICACIÓN", "0012", "POR DETERMINAR"), ("TIPO DE EXPEDIENTE", "44317", "POR DETERMINAR")]
    ruta = Path(tmp_path) / "revision.xlsx"
    with pd.ExcelWriter(ruta, engine="xlsxwriter") as escritor:
        rx.write_mapeo_sheet(escritor, p.ReviewedTable.from_rows(filas))

    leida = rx.read_review(ruta).table

    assert leida.lookup("IDENTIFICACIÓN", "0012") == "POR DETERMINAR"
    assert leida.lookup("TIPO DE EXPEDIENTE", "44317") == "POR DETERMINAR"


# ---------------------------------------------------------------------
# Aplicar la tabla (RF-88, RF-90, RF-91, RF-93)
# ---------------------------------------------------------------------

AUTO = p.Outcome("DEVOLUCION", p.AUTOMATIC, "formato")


@pytest.mark.parametrize("original", ["Devolucion", " Devolucion  "])
def test_valor_de_la_tabla_se_reemplaza_por_su_final(tabla, original):
    r = p.apply_reviewed_table(original, AUTO, "SOLICITUD", tabla)

    assert (r.final, r.state, r.motive) == ("DEVOLUCIÓN", p.DECIDED, "decisión")


def test_otro_formato_no_coincide_y_sugiere_el_final_de_la_tabla(tabla):
    r = p.apply_reviewed_table("devolucion", AUTO, "SOLICITUD", tabla)

    assert (r.final, r.state, r.motive, r.suggestion) == (
        "devolucion", p.REVIEW, "no está en la tabla revisada", "DEVOLUCIÓN")


def test_valor_nuevo_sugiere_el_resultado_de_la_regla(tabla):
    automatico = p.Outcome("ARCHIVO NUEVO", p.AUTOMATIC, "formato")

    r = p.apply_reviewed_table("Archivo nuevo", automatico, "SOLICITUD", tabla)

    assert (r.state, r.suggestion) == (p.REVIEW, "ARCHIVO NUEVO")


def test_valor_nuevo_pendiente_sugiere_la_sugerencia_de_la_regla(tabla):
    automatico = p.Outcome("Archivo nuevo", p.REVIEW, "similitud 80–89", "ARCHIVO")

    r = p.apply_reviewed_table("Archivo nuevo", automatico, "SOLICITUD", tabla)

    assert r.suggestion == "ARCHIVO"


def test_el_valor_pendiente_conserva_el_texto_ya_limpio_si_se_da(tabla):
    r = p.apply_reviewed_table("Archivo   nuevo", AUTO, "SOLICITUD", tabla, current="Archivo nuevo")

    assert r.final == "Archivo nuevo"


def test_valores_que_solo_difieren_en_mayusculas_son_distintos(tabla):
    assert p.apply_reviewed_table("SeRVR", p.Outcome("SERVR"), "SALA", tabla) == p.Outcome("SeRVR")
    assert p.apply_reviewed_table("SRVR", p.Outcome("SRVR"), "SALA", tabla) == p.Outcome("SRVR")


def test_identificacion_con_numeros_reescritos_queda_tal_cual(tabla):
    automatico = p.classify_identification("123456 y 654321")

    r = p.apply_reviewed_table("123456 y 654321", automatico, "IDENTIFICACIÓN", tabla)

    assert (r.final, r.pending) == ("123456 y 654321", False)


def test_identificacion_que_la_tabla_manda_a_por_determinar_cambia(tabla):
    r = p.apply_reviewed_table("C.C. 123456", p.classify_identification("C.C. 123456"), "IDENTIFICACIÓN", tabla)

    assert (r.final, r.state) == ("POR DETERMINAR", p.DECIDED)


@pytest.mark.parametrize("cedulas", ["87654321", "11111111\n22222222", 87654321.0])
def test_cedulas_que_no_estan_en_la_tabla_no_cambian_ni_quedan_pendientes(tabla, cedulas):
    automatico = p.classify_identification(cedulas)

    assert p.apply_reviewed_table(cedulas, automatico, "IDENTIFICACIÓN", tabla) == automatico


@pytest.mark.parametrize("columna, original", [("DECISIÓN", "Archivar"), ("TIPO DE EXPEDIENTE", "Digital")])
def test_filas_no_aplicadas_quedan_pendientes(tabla, columna, original):
    automatico = p.Outcome("X", p.AUTOMATIC, "formato")

    r = p.apply_reviewed_table(original, automatico, columna, tabla)

    assert (r.state, r.motive, r.suggestion) == (p.REVIEW, "no está en la tabla revisada", "X")


def test_columna_que_no_esta_en_la_tabla_usa_la_regla(tabla):
    automatico = p.Outcome("ANA RUIZ", p.AUTOMATIC, "formato")

    assert p.apply_reviewed_table("Ana Ruiz", automatico, "MAGISTRADO", tabla) == automatico
    assert p.apply_reviewed_table("Ana Ruiz", automatico, "MAGISTRADO", None) == automatico


@pytest.mark.parametrize("vacio", [None, "", "   "])
def test_vacio_sigue_por_determinar(tabla, vacio):
    automatico = p.empty_outcome("SOLICITUD")

    assert p.apply_reviewed_table(vacio, automatico, "SOLICITUD", tabla) == automatico


# ---------------------------------------------------------------------
# Columnas _ORIGINAL (RF-87)
# ---------------------------------------------------------------------

def test_columnas_original_junto_a_cada_columna_estandarizada():
    df = pd.DataFrame({"No": [1], "SOLICITUD": [" Devolucion  "],
                       "TIPO DE EXPEDIENTE\n(ELECTRONICO - HIBRIDO)": [44317.0], "OBSERVACIONES": ["x"]})

    r = p.add_original_columns(df)

    assert list(r.columns) == ["No", "SOLICITUD", "SOLICITUD_ORIGINAL", "TIPO DE EXPEDIENTE\n(ELECTRONICO - HIBRIDO)",
                               "TIPO DE EXPEDIENTE_ORIGINAL", "OBSERVACIONES"]
    assert r.loc[0, "SOLICITUD_ORIGINAL"] == " Devolucion  "
    assert r.loc[0, "TIPO DE EXPEDIENTE_ORIGINAL"] == 44317.0
    assert "SOLICITUD_ORIGINAL" not in df.columns


def test_columnas_original_no_se_duplican():
    df = p.add_original_columns(pd.DataFrame({"SALA": ["SRVR"]}))

    assert list(p.add_original_columns(df).columns) == ["SALA", "SALA_ORIGINAL"]


# ---------------------------------------------------------------------
# Verificación de totales (RF-92)
# ---------------------------------------------------------------------

def test_totales_por_resultado_en_el_orden_de_la_spec():
    filas = {
        "SOLICITUD": [
            (None, p.empty_outcome("SOLICITUD")),
            ("Rewquerimiento x", p.Outcome("Rewquerimiento x", p.REVIEW, "similitud 80–89", "X")),
            ("Devolucion", p.Outcome("DEVOLUCIÓN", p.DECIDED, "decisión")),
            ("0", p.Outcome("POR DETERMINAR", p.AUTOMATIC, "otra categoría")),
            ("devolucion", p.Outcome("DEVOLUCIÓN", p.AUTOMATIC, "formato")),
            ("DEVOLUCIÓN", p.Outcome("DEVOLUCIÓN")),
        ],
        "SALA": [("SRVR", p.Outcome("SRVR", p.TO_CONFIRM, "confirmar código de SALA"))] * 6,
        "IDENTIFICACIÓN": [
            ("12345678", p.Outcome("12345678")),
            ("123456 y 654321", p.Outcome("123456 y 654321")),
            ("Caso 3", p.Outcome("CASO 003", p.AUTOMATIC, "formato de identificación")),
            ("x", p.Outcome("x", p.REVIEW, "no está en la tabla revisada", "")),
            (" ", p.empty_outcome("IDENTIFICACIÓN")),
            ("1234567.0", p.Outcome("1234567", p.AUTOMATIC, "formato")),
        ],
        "NOMBRES_APELLIDOS": [("Ana", p.Outcome("ANA"))],      # no cuenta
    }

    totales = p.verify_totals(filas, total=6)

    assert totales["SOLICITUD"] == Counter({p.EMPTY_TO_UNDETERMINED: 1, p.PENDING_RESULT: 1, p.REPLACED: 2,
                                            p.UNCHANGED: 2})
    assert totales["SALA"] == Counter({p.UNCHANGED: 6})
    assert totales["IDENTIFICACIÓN"] == Counter({p.CEDULA_AS_IS: 3, p.REPLACED: 1, p.PENDING_RESULT: 1,
                                                 p.EMPTY_TO_UNDETERMINED: 1})
    assert "NOMBRES_APELLIDOS" not in totales


def test_totales_que_no_cuadran_dan_error_claro():
    filas = {"SOLICITUD": [("a", p.Outcome("A"))] * 5}

    with pytest.raises(p.TotalsMismatchError, match="SOLICITUD.*5.*6"):
        p.verify_totals(filas, total=6)


# ---------------------------------------------------------------------
# Datos reales (Decisión #13): igual que la herramienta local
# ---------------------------------------------------------------------

REPO = Path(__file__).resolve().parent.parent
BASE = REPO / "data" / "original" / "Base de datos Delegadas JEP corte 5 agosto.xlsx"
REVISADA = REPO / "data" / "original" / "parametros_unificados_revisados_AHRV_13102026.xlsx"


@pytest.mark.datos_reales
@pytest.mark.skipif(not (BASE.exists() and REVISADA.exists()), reason="faltan los archivos reales")
def test_datos_reales_tabla_del_supervisor_sobre_el_corte():
    tabla = rx.read_review(REVISADA).table
    df = pd.read_excel(BASE, sheet_name="Reparto", engine="calamine")
    tipo = next(col for col in df.columns if col.startswith("TIPO DE EXPEDIENTE"))
    df = df.rename(columns={tipo: "TIPO DE EXPEDIENTE"})

    filas, rf91, rf90 = {}, Counter(), Counter()
    for columna in sorted(tabla.columns):
        valores = df[columna]
        if columna in p.FIXED_LISTS:
            automatico = {v: p.classify_fixed_list(v, columna) for v in valores.unique()}
        elif columna == "IDENTIFICACIÓN":
            automatico = {v: p.classify_identification(v) for v in valores.unique()}
        else:
            automatico = p.classify_catalog_column(valores.value_counts(dropna=False), columna).outcomes
        filas[columna] = []
        for v in valores:
            r = p.apply_reviewed_table(v, automatico[v], columna, tabla)
            filas[columna].append((v, r))
            rf90[columna] += r.motive == "no está en la tabla revisada"
            final = tabla.lookup(columna, p.to_text(v).strip())
            rf91[columna] += columna == "IDENTIFICACIÓN" and final is not None and p.has_long_number(final)

    totales = p.verify_totals(filas, total=len(df))

    assert len(df) == 134040
    assert all(sum(c.values()) == 134040 for c in totales.values())
    assert rf91["IDENTIFICACIÓN"] == 106
    # La herramienta local listaba 10 fuera de la tabla; una de ellas es "-",
    # que el producto trata como vacía (solo signos) → POR DETERMINAR (RF-21).
    assert rf90 == Counter({"IDENTIFICACIÓN": 9})
