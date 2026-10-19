"""T15: el pipeline (RF-51, RF-52, RF-55, RF-87, RF-92; Decisiones #4, #9, #10, #17) y la limpieza que lo precede. Datos sintéticos."""
import pandas as pd
import pytest

from src import parameters as p
from src import pipeline
from src.standardization import clean_and_standardize

NAMES = "NOMBRES_APELLIDOS"
IDENT = "IDENTIFICACIÓN"
PEGADO = "Ana Perez Gomez Y Luis Diaz Rojas"
SUGERENCIA = "ANA PEREZ GOMEZ | LUIS DIAZ ROJAS"
ETAPAS = [pipeline.STAGE_CLEAN, pipeline.STAGE_PARAMETERS, pipeline.STAGE_DUPLICATES, pipeline.STAGE_SPLIT]


def _df():
    return pd.DataFrame({
        "No": [1, 2, 3, 4, 5],
        "RADICADO IUS": ["E-2020-100001", "E-2020-100002", "E-2020-100003", "E-2020-100004", "E-2020-100005"],
        IDENT: ["1000000001", "1000000002\n1000000003", "1000000004\n1000000005", "1000000006", "1000000001"],
        NAMES: ["  ana   ruiz díaz ", "Luis Mora Paz\nEva Rios Gil", PEGADO, "Carlos Ruiz", "ANA RUIZ DIAZ"],
        "SOLICITUD": ["Devolución", "devolucion", None, "DEVOLUCIÓN", "DEVOLUCIÓN"],
        "MAGISTRADO": ["Peña Ruiz Ana", "Peña Ruiz Ana", "Peña Ruiz Ana", "Peña Ruiz Ana", "Peña Ruiz Ana"],
        "FECHA": ["01/03/2021", "02/03/2021", "03/03/2021", "04/03/2021", "05/03/2021"],
        "CLASIFICACIÓN DEL RADICADO": ["SIM", "ACTIVO", "ARCHIVADO", "ACTIVO", "ACTIVO"],
        "FUNCIONARIO A CARGO": ["JUAN PEREZ", "JUAN PEREZ", "MARIA LOPEZ", "FUNCIONARIOS RETIRADOS", "JUAN PEREZ"],
        "OBSERVACIONES": ["texto  libre", "", "x", "y", "z"],
    })


@pytest.fixture(scope="module")
def r():
    return pipeline.run(_df())


def _filas(resultado, id_registro):
    hojas = [h for nombre, h in resultado.sheets.items() if nombre not in ("SIM", pipeline.MULTI_IUS_SHEET)]
    todas = pd.concat(hojas, ignore_index=True)
    return todas[todas["ID REGISTRO"] == id_registro].sort_values("PERSONA N.º").reset_index(drop=True)


def _entradas(resultado, original, column=NAMES):
    return [e for e in resultado.review.entries if e.column == column and e.original == original]


# ---------------------------------------------------------------------
# Orden (RF-51, RF-52, Decisión #17)
# ---------------------------------------------------------------------

def test_etapas_en_orden_con_la_de_parametros():
    etapas = []
    pipeline.run(_df(), on_stage=etapas.append)

    assert etapas == ETAPAS
    assert pipeline.STAGE_PARAMETERS == "Estandarizando parámetros..."


def test_el_orden_de_los_pasos_es_el_del_cambio_6(monkeypatch):
    llamadas = []

    def espiar(nombre, detalle):
        funcion = getattr(pipeline, nombre)

        def espia(*args, **kwargs):
            llamadas.append((nombre, detalle(*args, **kwargs)))
            return funcion(*args, **kwargs)
        monkeypatch.setattr(pipeline, nombre, espia)

    filas = lambda df, *a, **k: len(df)  # noqa: E731
    espiar("add_original_columns", filas)
    espiar("clean_and_standardize", filas)
    espiar("standardize_parameters", lambda df, **k: (len(df), NAMES in k["columns"]))
    espiar("separate", filas)
    espiar("run_similarity_report", filas)
    espiar("split_by_status", filas)

    pipeline.run(_df())

    assert llamadas == [
        ("add_original_columns", 5),
        ("clean_and_standardize", 5),
        ("standardize_parameters", (5, False)),     # parámetros de las filas originales, sin nombres
        ("separate", 5),
        ("standardize_parameters", (6, True)),      # nombres, sobre las filas ya separadas
        ("run_similarity_report", 6),
        ("split_by_status", 6),
    ]


# ---------------------------------------------------------------------
# Totales (RF-92)
# ---------------------------------------------------------------------

def test_los_totales_se_cuentan_sobre_las_filas_originales(r):
    assert len(r.records) == 6
    assert set(r.review.totals) == {IDENT, "SOLICITUD", "MAGISTRADO", "FUNCIONARIO A CARGO"}
    for columna, conteo in r.review.totals.items():
        assert conteo.total() == 5, columna


def test_una_suma_alterada_da_el_error_de_rf92_y_no_hay_resultado(monkeypatch):
    verificar = p.verify_totals

    def alterada(filas_por_columna, total):
        filas = dict(filas_por_columna)
        columna = next(iter(filas))
        filas[columna] = filas[columna][:-1]
        return verificar(filas, total)
    monkeypatch.setattr(p, "verify_totals", alterada)
    etapas = []

    with pytest.raises(p.TotalsMismatchError, match="no cuadra"):
        pipeline.run(_df(), on_stage=etapas.append)
    assert etapas == ETAPAS[:2]


# ---------------------------------------------------------------------
# Cancelación (RF-55)
# ---------------------------------------------------------------------

def test_cancelar_entre_etapas_no_da_resultado():
    etapas = []

    with pytest.raises(pipeline.ProcessCancelled):
        pipeline.run(_df(), on_stage=etapas.append, should_cancel=lambda: etapas == ETAPAS[:1])
    assert etapas == ETAPAS[:1]


def test_cancelar_entre_columnas_de_la_estandarizacion_no_da_resultado(monkeypatch):
    etapas, revisiones, separadas = [], [], []
    monkeypatch.setattr(pipeline, "separate", lambda *a, **k: separadas.append(1))

    def cancelar():
        if etapas[-1:] != [pipeline.STAGE_PARAMETERS]:
            return False
        revisiones.append(1)
        return len(revisiones) == 2          # la segunda revisión es antes de la segunda columna

    with pytest.raises(pipeline.ProcessCancelled):
        pipeline.run(_df(), on_stage=etapas.append, should_cancel=cancelar)
    assert etapas == ETAPAS[:2]
    assert separadas == []


# ---------------------------------------------------------------------
# Columnas _ORIGINAL, separación y nombres (RF-22, RF-25, RF-27, RF-75, RF-87)
# ---------------------------------------------------------------------

def test_las_columnas_original_quedan_crudas_junto_a_cada_columna(r):
    fila = _filas(r, 1).iloc[0]
    columnas = list(r.sheets["Reparto_Activo"].columns)

    assert fila["NOMBRES_APELLIDOS_ORIGINAL"] == "  ana   ruiz díaz "
    assert columnas.index("NOMBRES_APELLIDOS_ORIGINAL") == columnas.index(NAMES) + 1
    assert _filas(r, 2).iloc[0]["IDENTIFICACIÓN_ORIGINAL"] == "1000000002\n1000000003"


def test_una_fila_por_compareciente_con_el_grupo_completo_de_cedulas(r):
    filas = _filas(r, 2)

    assert list(filas[NAMES]) == ["LUIS MORA PAZ", "EVA RIOS GIL"]
    assert set(filas["SEPARACIÓN"]) == {"SEPARADA"}
    assert all(f.split("\n") == ["1000000002", "1000000003"] for f in filas[IDENT])


def test_la_separacion_queda_en_la_tabla_de_estandarizacion(r):
    entrada, = _entradas(r, "Luis Mora Paz\nEva Rios Gil")

    assert (entrada.final, entrada.motive, entrada.state) == ("Luis Mora Paz | Eva Rios Gil", "varios nombres", p.AUTOMATIC)
    assert entrada.row_ids == [1]


def test_los_nombres_se_estandarizan_despues_de_separar_y_conservan_la_n(r):
    # RF-8: mayúsculas, sin tildes en las vocales, con Ñ.
    assert _filas(r, 1).iloc[0][NAMES] == _filas(r, 5).iloc[0][NAMES] == "ANA RUIZ DIAZ"
    assert set(r.records["MAGISTRADO"]) == {"PEÑA RUIZ ANA"}
    assert len(r.sheets[pipeline.MULTI_IUS_SHEET]) == 2      # mismo nombre ya estandarizado, dos IUS


def test_celda_sin_separar_queda_pendiente_con_la_sugerencia(r):
    entrada, = [e for e in _entradas(r, PEGADO) if e.state == p.REVIEW]
    fila = _filas(r, 3).iloc[0]

    assert (entrada.final, entrada.motive) == (SUGERENCIA, p.SEVERAL_NAMES)
    assert fila["SEPARACIÓN"] == "SIN SEPARAR"
    assert "pendiente de revisión" in fila[p.OBSERVATION]
    assert (0, NAMES) in r.highlights["Archivados"]
    assert r.review.summary[NAMES]["estados"][p.REVIEW][1] >= 1


# ---------------------------------------------------------------------
# Lo que sale: hojas, ubicaciones, Excel de revisión
# ---------------------------------------------------------------------

def test_hojas_del_resultado_sin_columnas_internas(r):
    assert list(r.sheets) == ["Reparto_Activo", "Archivados", "Funcionarios_Retirados", "SIM", "Multiples_IUS"]
    assert r.counts == {"Reparto_Activo": 4, "Archivados": 1, "Funcionarios_Retirados": 1, "SIM": 1,
                        "Multiples_IUS": 2}
    for nombre, hoja in r.sheets.items():
        assert not [c for c in hoja.columns if str(c).startswith("_")], nombre
        assert list(hoja.columns)[-1] == p.OBSERVATION, nombre


def test_datos_del_excel_de_revision(r):
    assert r.review.locations[2] == ["Archivados fila 2"]
    assert r.review.separation["SEPARADA"] == 1 and r.review.separation["SIN SEPARAR"] == 1
    assert r.review.separation["filas"] == 6
    # Catálogos y resumen en el orden de las columnas de la spec (los nombres no van al final).
    assert list(r.review.catalogs) == ["SOLICITUD", NAMES, "MAGISTRADO", "FUNCIONARIO A CARGO", IDENT]
    assert list(r.review.summary) == list(r.review.catalogs)
    assert r.review.unmatched_decisions == 0


# ---------------------------------------------------------------------
# Decisiones cargadas (RF-39, RF-48, RF-77)
# ---------------------------------------------------------------------

def _con_decision(texto, original=PEGADO):
    return pipeline.run(_df(), decisions=p.Decisions(table=[(NAMES, original, texto)]))


def test_aceptar_la_sugerencia_separa_y_no_cuenta_como_sin_coincidencia():
    resultado = _con_decision("ACEPTAR")
    filas = _filas(resultado, 3)

    assert list(filas[NAMES]) == ["ANA PEREZ GOMEZ", "LUIS DIAZ ROJAS"]
    assert set(filas["SEPARACIÓN"]) == {"SEPARADA"}
    assert all(NAMES not in pend for pend in resultado.records.loc[resultado.records["ID REGISTRO"] == 3, "_pending"])
    entrada, = _entradas(resultado, PEGADO)
    assert (entrada.state, entrada.decision, entrada.final) == (p.DECIDED, "ACEPTAR", SUGERENCIA)
    assert resultado.review.unmatched_decisions == 0


def test_mantener_deja_la_celda_entera_sin_pendiente():
    resultado = _con_decision("MANTENER")
    filas = _filas(resultado, 3)

    assert len(filas) == 1 and filas.iloc[0]["SEPARACIÓN"] == ""
    assert NAMES not in resultado.records.loc[resultado.records["ID REGISTRO"] == 3, "_pending"].iloc[0]
    assert resultado.review.unmatched_decisions == 0


def test_una_separacion_decidida_sobre_una_celda_que_no_esta_cuenta_como_sin_coincidencia():
    resultado = _con_decision("Pedro Gil Paz | Rosa Rey Soto", original="Pedro Gil Paz Rosa Rey Soto")

    assert resultado.review.unmatched_decisions == 1


def test_filas_de_la_tabla_revisada_que_no_se_aplican_se_listan():
    # RF-89 (T18): como RF-48, el mismo original con dos finales y un final
    # fuera de la lista fija no se aplican y van al resumen.
    tabla = p.ReviewedTable.from_rows([
        ("SOLICITUD", "Devolución", "DEVOLUCIÓN"), ("SOLICITUD", "Devolución", "DEVOLUCION"),
        ("TIPO DE EXPEDIENTE", "Digital", "DIGITAL"),
    ])

    resultado = pipeline.run(_df(), table=tabla)

    problemas = resultado.review.invalid_decisions
    assert any("SOLICITUD" in x and "«Devolución»" in x and "dos valores finales" in x for x in problemas)
    assert any("TIPO DE EXPEDIENTE" in x and "«Digital»" in x and "«DIGITAL»" in x for x in problemas)
    assert all(x.startswith("Tabla revisada") for x in problemas)


# ---------------------------------------------------------------------
# Guardar (T19: una sola función para la GUI y main.py, Decisión #4)
# ---------------------------------------------------------------------

def test_save_guarda_resultado_y_revision_con_su_nombre_en_el_resumen(r, tmp_path):
    resultado, revision = pipeline.save(r, tmp_path / "salida.xlsx")

    assert (resultado.name, revision.name) == ("salida.xlsx", "salida_revision.xlsx")      # RF-36
    resumen = pd.read_excel(revision, sheet_name="Resumen", dtype=str)
    assert "salida_revision.xlsx" in set(resumen["Valores"])                               # RF-71


def test_save_cancelado_no_deja_nada(r, tmp_path):
    from src.exportation import ExportCancelled

    with pytest.raises(ExportCancelled):
        pipeline.save(r, tmp_path / "salida.xlsx", should_cancel=lambda: True)

    assert list(tmp_path.iterdir()) == []                                                  # RF-80


def test_save_avisa_antes_de_escribir_la_revision(r, tmp_path):
    pasos = []

    pipeline.save(r, tmp_path / "salida.xlsx", on_sheet_done=lambda hoja, i, n: pasos.append(hoja),
                  before_review=lambda: pasos.append("revisión"))

    assert pasos == [*r.sheets, "revisión"]


# ---------------------------------------------------------------------
# Casos límite
# ---------------------------------------------------------------------

def test_archivo_sin_filas_no_da_error():
    resultado = pipeline.run(_df().iloc[0:0])

    assert all(n == 0 for n in resultado.counts.values())
    assert not [e for e in resultado.review.entries if e.state == p.REVIEW]


def test_sin_columna_de_nombres_sigue_y_la_lista_como_faltante():
    resultado = pipeline.run(_df().drop(columns=[NAMES]))

    assert NAMES in resultado.missing_columns
    assert resultado.counts["Reparto_Activo"] == 3


# ---------------------------------------------------------------------
# clean_and_standardize (Decisiones #9, #10)
# ---------------------------------------------------------------------

def test_limpieza_conserva_saltos_de_linea_en_nombres_e_identificacion():
    df = pd.DataFrame({NAMES: ["  Ana  Ruiz \r\n\n  Luis   Mora  "], IDENT: ["11111111 \n\n 22222222"],
                       "OBSERVACIONES": ["a \n  b"]})

    limpio = clean_and_standardize(df)

    assert limpio.loc[0, NAMES] == "Ana Ruiz\nLuis Mora"
    assert limpio.loc[0, IDENT] == "11111111\n22222222"
    assert limpio.loc[0, "OBSERVACIONES"] == "a b"


def test_limpieza_no_separa_ni_formatea_nombres():
    df = pd.DataFrame({NAMES: ["ana peña\nluis mora"], IDENT: ["11111111\n22222222"],
                       "MAGISTRADO": ["Peña Ruiz"], "FUNCIONARIO A CARGO": ["luis  mora"]})

    limpio = clean_and_standardize(df)

    assert len(limpio) == 1
    assert limpio.loc[0, NAMES] == "ana peña\nluis mora"
    assert limpio.loc[0, "MAGISTRADO"] == "Peña Ruiz"
    assert limpio.loc[0, "FUNCIONARIO A CARGO"] == "luis mora"


def test_limpieza_no_toca_las_columnas_original_ni_los_vacios():
    df = pd.DataFrame({NAMES: [None, " x "], "NOMBRES_APELLIDOS_ORIGINAL": [None, " x  \n y "],
                       "SALA_ORIGINAL": ["  srvr  ", None]})

    limpio = clean_and_standardize(df)

    assert pd.isna(limpio.loc[0, NAMES]) and limpio.loc[1, NAMES] == "x"
    assert limpio.loc[1, "NOMBRES_APELLIDOS_ORIGINAL"] == " x  \n y "
    assert limpio.loc[0, "SALA_ORIGINAL"] == "  srvr  "


# ---------------------------------------------------------------------
# T22 (validación): pruebas directas que la revisión RF por RF encontró
# parciales — RF-19, RF-34, RF-41, RF-56 y RF-67.
# ---------------------------------------------------------------------

def _df_rf41():
    return pd.DataFrame({
        "No": range(1, 14),
        IDENT: ["11111111", "11111111", "11111111", "11111111", "Sin cédula", "Caso 7", None,
                "22222222", "33333333", "22222222\n33333333", "44444444", "55555555", "No registra"],
        NAMES: ["Ana Ruiz Diaz", "Ana Ruiz Diaz", "Ana Ruiz Diaz", "Ana Ruiz Dias",     # RF-13: la cédula confirma
                "Juana Rios Paz",                                                          # RF-33 en IDENTIFICACIÓN
                "Luis Mora Paz\nEva Rios Gil",                                             # RF-23: un valor que no es cédula
                "Pedro Gil Paz\nRosa Rey Soto",                                            # RF-67: sin identificación
                "Mario Andres Lopez Diaz", "Pedro Luis Ruiz Ruiz",
                "Mario Andres Lopez Diaz Pedro Luis Ruiz Ruiz",                            # RF-24: nombres pegados
                "Carlos Vega Ruiz y otros",                                                # RF-29
                "Solicitud de informe\nMarta Sol Vega",                                    # RF-68
                "Lina Paz Rey"],                                                           # RF-34 en IDENTIFICACIÓN
        "TIPO DE EXPEDIENTE": ["Agendado", "Fisico y electronico"] + ["FÍSICO"] * 11,     # RF-19, RF-66
    })


def test_rf41_cada_sustitucion_de_la_lista_queda_en_la_tabla():
    r = pipeline.run(_df_rf41())

    def estado(columna, original):
        encontradas = [e for e in r.review.entries if e.column == columna and e.original == original]
        assert encontradas, (columna, original)
        return encontradas[0]

    assert estado(NAMES, "Ana Ruiz Dias").final == "ANA RUIZ DIAZ"                         # RF-13
    assert estado("TIPO DE EXPEDIENTE", "Agendado").final == "POR DETERMINAR"               # RF-19
    assert estado("TIPO DE EXPEDIENTE", "Fisico y electronico").final == "HÍBRIDO"          # RF-66
    assert estado(IDENT, "Sin cédula").final == "SIN CC"                                    # RF-33
    no_registra = estado(IDENT, "No registra")                                              # RF-34
    assert (no_registra.final, no_registra.motive) == ("POR DETERMINAR", "otra categoría")
    for celda in ("Luis Mora Paz\nEva Rios Gil", "Pedro Gil Paz\nRosa Rey Soto",            # RF-23, RF-67
                  "Mario Andres Lopez Diaz Pedro Luis Ruiz Ruiz"):                          # RF-24
        assert estado(NAMES, celda).motive == "varios nombres", celda
    assert estado(NAMES, "Carlos Vega Ruiz y otros").motive == '"Y OTROS"'                  # RF-29
    assert estado(NAMES, "Solicitud de informe\nMarta Sol Vega").motive == "línea que no es de persona"   # RF-68
    for e in r.review.entries:
        assert e.state in (p.AUTOMATIC, p.REVIEW, p.TO_CONFIRM, p.DECIDED) and e.row_ids


def test_rf67_varias_personas_sin_identificacion_quedan_por_determinar_y_sin_confirmar():
    r = pipeline.run(_df_rf41())
    filas = r.records[r.records["ID REGISTRO"] == 7]

    assert list(filas[NAMES]) == ["PEDRO GIL PAZ", "ROSA REY SOTO"]
    assert set(filas[IDENT]) == {"POR DETERMINAR"}
    assert set(filas["SEPARACIÓN"]) == {"SEPARADA SIN CONFIRMAR"}


def test_rf56_codigos_de_sala_por_confirmar_no_se_pintan_ni_cuentan():
    df = _df().assign(SALA=["SRVR", "SRVR", "SDSJ", "SRVR", "SDSJ"])

    r = pipeline.run(df)

    assert [e for e in r.review.entries if e.column == "SALA" and e.state == p.TO_CONFIRM]
    assert not any(columna == "SALA" for celdas in r.highlights.values() for _, columna in celdas)
    assert not any("SALA" in pendiente for pendiente in r.records["_pending"])
