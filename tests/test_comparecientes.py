"""T9: separar comparecientes por líneas (spec 002, cambio 6). Datos sintéticos (principio 6)."""
import pandas as pd
import pytest

from src import comparecientes as c

NAMES, IDS, IUS = "NOMBRES_APELLIDOS", "IDENTIFICACIÓN", "RADICADO IUS"
GRUPO = "11111111\n22222222"


def _df(*filas, con_id=True):
    columnas = ["No", NAMES, IDS, IUS, "SALA"] if con_id else ["No", NAMES, IUS, "SALA"]
    datos = []
    for i, (nombre, ident) in enumerate(filas, start=1):
        fila = {"No": i, NAMES: nombre, IUS: f"IUS-{i}", "SALA": "SRVR"}
        if con_id:
            fila[IDS] = ident
        datos.append(fila)
    return pd.DataFrame(datos, columns=columnas)


def _filas(resultado):
    return resultado.df.to_dict("records")


# ---------------------------------------------------------------------
# Cantidad de cédulas (definición del cambio 6)
# ---------------------------------------------------------------------

@pytest.mark.parametrize("texto, cantidad", [
    ("12345678", 1), (GRUPO, 2), ("12.345.678\n87654321", 2), ("1.053.323.136", 1),
    ("123456 y 654321", 2), ("12345678.87654321", 2), ("CASO 003", 0), ("POR DETERMINAR", 0),
    ("1234567890123456789", 0), ("", 0), (None, 0), (12345678.0, 1),
])
def test_cantidad_de_cedulas(texto, cantidad):
    assert c.count_cedulas(texto) == cantidad


# ---------------------------------------------------------------------
# Separar por líneas (RF-22, RF-23, RF-27, RF-67)
# ---------------------------------------------------------------------

def test_lineas_dos_nombres_y_dos_cedulas_dan_dos_filas_con_el_grupo_completo():
    df = _df(("Ana Ruiz Diaz\nLuis Mora Paz", GRUPO))
    df.loc[0, IUS] = "IUS-1\nIUS-2"

    filas = _filas(c.separate(df))

    assert [f[NAMES] for f in filas] == ["Ana Ruiz Diaz", "Luis Mora Paz"]
    assert {f[IDS] for f in filas} == {GRUPO}
    assert {f[IUS] for f in filas} == {"IUS-1\nIUS-2"}
    assert {f["No"] for f in filas} == {1}
    assert {f["SALA"] for f in filas} == {"SRVR"}
    assert {f["ID REGISTRO"] for f in filas} == {1}
    assert [f["PERSONA N.º"] for f in filas] == [1, 2]
    assert {f["PERSONAS EN EL REGISTRO"] for f in filas} == {2}
    assert {f["SEPARACIÓN"] for f in filas} == {"SEPARADA"}


@pytest.mark.parametrize("ident", ["11111111", "CASO 003", "POR DETERMINAR", ""])
def test_lineas_con_otra_cantidad_de_cedulas_quedan_sin_confirmar(ident):
    filas = _filas(c.separate(_df(("Ana Ruiz Diaz\nLuis Mora Paz", ident))))

    assert len(filas) == 2
    assert {f[IDS] for f in filas} == {ident}
    assert {f["SEPARACIÓN"] for f in filas} == {"SEPARADA SIN CONFIRMAR"}


def test_lineas_cedulas_con_puntos_de_miles_cuentan_como_cedulas():
    filas = _filas(c.separate(_df(("Ana Ruiz Diaz\nLuis Mora Paz", "12.345.678\n87654321"))))

    assert {f["SEPARACIÓN"] for f in filas} == {"SEPARADA"}


def test_lineas_una_persona_sola_no_se_toca():
    df = _df(("Ana Ruiz Diaz", "11111111"))

    filas = _filas(c.separate(df))

    assert len(filas) == 1
    f = filas[0]
    assert (f[NAMES], f[IDS], f["ID REGISTRO"], f["PERSONA N.º"], f["PERSONAS EN EL REGISTRO"],
            f["SEPARACIÓN"]) == ("Ana Ruiz Diaz", "11111111", 1, 1, 1, "")


def test_lineas_conservan_el_orden_de_registros_y_de_personas():
    df = _df(("Ana Ruiz Diaz", "11111111"), ("Luis Mora Paz\nEva Rios Gil", GRUPO), ("Juan Paz Rey", "33333333"))

    filas = _filas(c.separate(df))

    assert [(f["ID REGISTRO"], f[NAMES]) for f in filas] == [
        (1, "Ana Ruiz Diaz"), (2, "Luis Mora Paz"), (2, "Eva Rios Gil"), (3, "Juan Paz Rey")]


def test_lineas_id_registro_sale_de_row_id_heredado():
    df = _df(("Luis Mora Paz\nEva Rios Gil", GRUPO))
    df["_row_id"] = [41]

    resultado = c.separate(df)

    assert list(resultado.df["_row_id"]) == [41, 41]
    assert list(resultado.df["_person"]) == [1, 2]
    assert set(resultado.df["ID REGISTRO"]) == {42}


def test_lineas_vacias_y_saltos_dobles_no_crean_personas():
    filas = _filas(c.separate(_df(("Ana Ruiz Diaz\n\n \nLuis Mora Paz\n", GRUPO))))

    assert [f[NAMES] for f in filas] == ["Ana Ruiz Diaz", "Luis Mora Paz"]
    assert {f["SEPARACIÓN"] for f in filas} == {"SEPARADA"}


def test_lineas_sin_columna_identificacion_se_separan_sin_confirmar():
    filas = _filas(c.separate(_df(("Ana Ruiz Diaz\nLuis Mora Paz", None), con_id=False)))

    assert [f[NAMES] for f in filas] == ["Ana Ruiz Diaz", "Luis Mora Paz"]
    assert {f["SEPARACIÓN"] for f in filas} == {"SEPARADA SIN CONFIRMAR"}


def test_lineas_cada_separacion_deja_su_rastro():
    resultado = c.separate(_df(("Ana Ruiz Diaz\nLuis Mora Paz", GRUPO)))

    assert resultado.traces == [c.Trace(0, "Ana Ruiz Diaz\nLuis Mora Paz", "Ana Ruiz Diaz | Luis Mora Paz",
                                        "varios nombres")]


# ---------------------------------------------------------------------
# Líneas que no son personas (RF-28, RF-29, RF-68)
# ---------------------------------------------------------------------

def test_lineas_referencia_de_caso_no_crea_persona():
    resultado = c.separate(_df(("Rosa Patiño\nCaso 007", "CASO 007")))

    filas = _filas(resultado)
    assert [f[NAMES] for f in filas] == ["Rosa Patiño"]
    assert filas[0]["SEPARACIÓN"] == ""
    assert c.Trace(0, "Rosa Patiño\nCaso 007", "Rosa Patiño", "línea que no es de persona") in resultado.traces


def test_lineas_asunto_completo_no_se_separa_y_se_marca():
    texto = "Autorizacion De Recepcion De Informes\n Caso 003"
    resultado = c.separate(_df((texto, "CASO 003")))

    filas = _filas(resultado)
    assert len(filas) == 1
    assert filas[0][NAMES] == texto
    assert filas[0]["SEPARACIÓN"] == ""
    assert resultado.marks[(0, 1)] == {c.NOT_A_PERSON}


@pytest.mark.parametrize("linea", ["Solicitud De Informacion", "Invitaciones A Audiencia", "Traslado Por Competencia"])
def test_lineas_palabras_de_asunto_en_singular_o_plural(linea):
    assert c.classify_line(linea) == c.SUBJECT


@pytest.mark.parametrize("linea, tipo", [
    ("Ana Ruiz Diaz", "persona"), ("Caso 003", "caso"), ("Cso 006", "caso"), ("Caso O03", "caso"),
    ("   ", "vacía"),
])
def test_lineas_clasificacion(linea, tipo):
    esperado = {"persona": c.PERSON, "caso": c.CASE_REFERENCE, "vacía": c.EMPTY}[tipo]
    assert c.classify_line(linea) == esperado


def test_lineas_y_otros_en_su_propia_linea():
    texto = "Ana Ruiz Montenegro\nY Otros (9)"
    resultado = c.separate(_df((texto, "11111111")))

    filas = _filas(resultado)
    assert [f[NAMES] for f in filas] == ["Ana Ruiz Montenegro"]
    assert resultado.marks[(0, 1)] == {c.MORE_UNNAMED}
    assert c.Trace(0, texto, "Ana Ruiz Montenegro", '"Y OTROS"') in resultado.traces


@pytest.mark.parametrize("texto", ["Ana Ruiz Diaz Y Otros", "Ana Ruiz Diaz y otros (4)", "Ana Ruiz Diaz Y 3 Personas Más",
                                   "Ana Ruiz Diaz y 12 personas mas"])
def test_lineas_y_otros_al_final_de_la_linea(texto):
    resultado = c.separate(_df((texto, "11111111")))

    assert [f[NAMES] for f in _filas(resultado)] == ["Ana Ruiz Diaz"]
    assert resultado.marks[(0, 1)] == {c.MORE_UNNAMED}


def test_lineas_y_otros_en_un_registro_separado_marca_a_cada_persona():
    resultado = c.separate(_df(("Ana Ruiz Diaz\nLuis Mora Paz Y Otros", GRUPO)))

    assert [f[NAMES] for f in _filas(resultado)] == ["Ana Ruiz Diaz", "Luis Mora Paz"]
    assert resultado.marks[(0, 1)] == resultado.marks[(0, 2)] == {c.MORE_UNNAMED}


# ---------------------------------------------------------------------
# Cambio 7: MESA solo al comienzo; números y una palabra + número no son personas
# ---------------------------------------------------------------------

@pytest.mark.parametrize("linea, tipo", [
    ("Pedro Pablo Mesa Duarte", c.PERSON), ("Mesa Departamental De Victimas", c.SUBJECT),
    ("Mesas De Trabajo", c.SUBJECT),
    ("12345678", c.OTHER_CATEGORY), ("No. 45", c.OTHER_CATEGORY), ("Rad 2020-123", c.OTHER_CATEGORY),
    ("Juan Perez CC 12345678", c.PERSON),
])
def test_lineas_cambio7_clasificacion(linea, tipo):
    assert c.classify_line(linea) == tipo


def test_lineas_un_numero_entre_personas_no_crea_persona():
    texto = "Ana Ruiz Diaz\nLuis Mora Paz\n12345678"
    resultado = c.separate(_df((texto, GRUPO)))

    filas = _filas(resultado)
    assert [f[NAMES] for f in filas] == ["Ana Ruiz Diaz", "Luis Mora Paz"]
    assert {f["SEPARACIÓN"] for f in filas} == {"SEPARADA"}
    assert c.Trace(0, texto, "Ana Ruiz Diaz | Luis Mora Paz", "línea que no es de persona") in resultado.traces


def test_lineas_celda_de_solo_otra_categoria_queda_como_esta_y_sin_marca():
    resultado = c.separate(_df(("No. 45", "11111111")))

    filas = _filas(resultado)
    assert [f[NAMES] for f in filas] == ["No. 45"]
    assert resultado.marks == {}
    assert resultado.traces == []


def test_lineas_asunto_con_otra_categoria_no_es_rf28():
    # RF-28 pide que TODAS las líneas sean asuntos o referencias de caso.
    resultado = c.separate(_df(("Solicitud De Informacion\nNo. 45", "")))

    assert resultado.marks == {}


# ---------------------------------------------------------------------
# T10: nombres pegados en una sola línea (RF-24, RF-25, RF-26, RF-69)
# ---------------------------------------------------------------------

PEGADO = "Mario Andres Lopez Diaz Pedro Luis Ruiz Ruiz"
CONOCIDOS = [("Mario Andres Lopez Diaz", "11111111"), ("Pedro Luis Ruiz Ruiz", "22222222")]


def _pegado(resultado, id_registro):
    return [f for f in _filas(resultado) if f["ID REGISTRO"] == id_registro]


def test_pegados_dos_nombres_conocidos_y_dos_cedulas_se_separan():
    resultado = c.separate(_df(*CONOCIDOS, (PEGADO, GRUPO)))

    filas = _pegado(resultado, 3)
    assert [f[NAMES] for f in filas] == ["Mario Andres Lopez Diaz", "Pedro Luis Ruiz Ruiz"]
    assert {f[IDS] for f in filas} == {GRUPO}
    assert {f["SEPARACIÓN"] for f in filas} == {"SEPARADA"}
    assert [f["PERSONA N.º"] for f in filas] == [1, 2]
    assert c.Trace(2, PEGADO, "Mario Andres Lopez Diaz | Pedro Luis Ruiz Ruiz", "varios nombres") in resultado.traces
    assert 2 not in resultado.pending


def test_pegados_sin_cedulas_quedan_pendientes_con_sugerencia():
    resultado = c.separate(_df(*CONOCIDOS, (PEGADO, "")))

    filas = _pegado(resultado, 3)
    assert len(filas) == 1
    assert filas[0][NAMES] == PEGADO
    assert filas[0]["SEPARACIÓN"] == "SIN SEPARAR"
    assert resultado.marks[(2, 1)] == {c.PENDING}
    assert resultado.pending[2] == "MARIO ANDRES LOPEZ DIAZ | PEDRO LUIS RUIZ RUIZ"


def test_pegados_otra_cantidad_de_cedulas_queda_pendiente_con_la_unica_division():
    resultado = c.separate(_df(*CONOCIDOS, (PEGADO, GRUPO + "\n33333333")))

    assert len(_pegado(resultado, 3)) == 1
    assert resultado.pending[2] == "MARIO ANDRES LOPEZ DIAZ | PEDRO LUIS RUIZ RUIZ"


def test_pegados_sin_columna_identificacion_no_aplica_rf24():
    resultado = c.separate(_df(*CONOCIDOS, (PEGADO, None), con_id=False))

    assert len(_pegado(resultado, 3)) == 1
    assert resultado.pending[2] == "MARIO ANDRES LOPEZ DIAZ | PEDRO LUIS RUIZ RUIZ"


def test_pegados_separador_y_sugiere_sin_aplicar():
    texto = "Ana Perez Gomez Y Luis Diaz Rojas"
    resultado = c.separate(_df((texto, GRUPO)))

    filas = _filas(resultado)
    assert len(filas) == 1 and filas[0]["SEPARACIÓN"] == "SIN SEPARAR"
    assert resultado.pending[0] == "ANA PEREZ GOMEZ | LUIS DIAZ ROJAS"


def test_pegados_diccionario_de_nombres_del_archivo_sugiere_division():
    personas = [("Maria Gil Ruiz", "1000001"), ("Maria Paz Ruiz", "1000002"), ("Maria Rey Ruiz", "1000003"),
                ("Juan Ortiz Soto", "1000004"), ("Juan Vega Soto", "1000005"), ("Juan Leon Soto", "1000006")]
    resultado = c.separate(_df(*personas, ("Maria Lopez Ruiz Juan Diaz Soto", GRUPO)))

    assert len(_pegado(resultado, 7)) == 1
    assert resultado.pending[6] == "MARIA LOPEZ RUIZ | JUAN DIAZ SOTO"


def test_pegados_dos_divisiones_posibles_sin_cedulas_no_sugieren_nada():
    conocidos = [("Ana Paz", "1000001"), ("Gil Rey Diaz Soto", "1000002"),
                 ("Ana Paz Gil", "1000003"), ("Rey Diaz Soto", "1000004")]
    resultado = c.separate(_df(*conocidos, ("Ana Paz Gil Rey Diaz Soto", "")))

    assert resultado.pending[4] == ""
    assert resultado.marks[(4, 1)] == {c.PENDING}


def test_pegados_con_cedulas_elige_la_division_con_tantas_partes():
    conocidos = [("Ana Paz", "1000001"), ("Gil Rey", "1000002"), ("Diaz Soto", "1000003"),
                 ("Ana Paz Gil", "1000004"), ("Rey Diaz Soto", "1000005")]
    resultado = c.separate(_df(*conocidos, ("Ana Paz Gil Rey Diaz Soto", "11111111\n22222222\n33333333")))

    # RF-24: una sola división en 3 nombres conocidos, como las 3 cédulas → se separa.
    assert [f[NAMES] for f in _pegado(resultado, 6)] == ["Ana Paz", "Gil Rey", "Diaz Soto"]


def test_pegados_particulas_no_cuentan_como_varios_nombres():
    resultado = c.separate(_df(("Jorge Ivan Mejia De La Torre", "11111111")))

    filas = _filas(resultado)
    assert len(filas) == 1 and filas[0]["SEPARACIÓN"] == ""
    assert resultado.pending == {}


def test_pegados_una_persona_corta_con_dos_cedulas_queda_pendiente_sin_sugerencia():
    resultado = c.separate(_df(("Ana Ruiz Diaz", GRUPO)))

    assert _filas(resultado)[0]["SEPARACIÓN"] == "SIN SEPARAR"
    assert resultado.pending == {0: ""}


def test_pegados_ninguna_celda_con_varios_nombres_queda_sin_aviso():
    df = _df(*CONOCIDOS, (PEGADO, GRUPO), (PEGADO, ""), ("Ana Ruiz Diaz", GRUPO), ("Uno Dos Tres Cuatro Cinco Seis", "1"))
    resultado = c.separate(df)

    for fila in _filas(resultado):
        if fila["ID REGISTRO"] >= 3:
            assert fila["SEPARACIÓN"] in ("SEPARADA", "SIN SEPARAR")


def test_pegados_cambio8_division_por_comas_con_partes_que_no_son_nombres_no_se_sugiere():
    # Una descripción con comas: trozos de 1 palabra y de más de 5.
    texto = "Pueblo Indigena, Uno, Dos Tres Cuatro Cinco Seis Siete Ocho"
    resultado = c.separate(_df((texto, GRUPO)))

    assert resultado.pending[0] == ""


def test_pegados_cambio8_una_celda_larga_de_otra_fila_no_es_nombre_conocido():
    largo = "Ana Paz Gil Rey Diaz Soto Luis Mora"          # 8 palabras: es ella misma una celda pegada
    resultado = c.separate(_df((largo, "1000001"), ("Pedro Ruiz", "1000002"),
                               (largo + " Pedro Ruiz", GRUPO)))

    assert len(_pegado(resultado, 3)) == 1
    assert resultado.pending[2] == ""


@pytest.mark.parametrize("palabras, forma", [
    ("ANA RUIZ", True), ("MARIA DEL CARMEN DE LA ROSA", True), ("ANA", False),
    ("UNO DOS TRES CUATRO CINCO SEIS", False),
])
def test_forma_de_nombre(palabras, forma):
    assert c._is_name_shape(palabras.split()) is forma


def test_lineas_sin_columna_de_nombres_no_cambia_nada():
    df = pd.DataFrame({"No": [1], IDS: [GRUPO]})

    resultado = c.separate(df)

    assert len(resultado.df) == 1
    assert resultado.df.loc[0, "PERSONAS EN EL REGISTRO"] == 1
    assert resultado.traces == []


# ---------------------------------------------------------------------
# Cambio 11: filas de compareciente que no son personas
# ---------------------------------------------------------------------

@pytest.mark.parametrize("linea", [
    "Caso 005 Norte Del Cauca", "Caso No. 01 Toma De Rehenes", "Caso001 Uraba", "CASO 04 Subcaso Uraba",
])
def test_cambio11_linea_que_empieza_con_un_caso_es_referencia_de_caso(linea):
    assert c.classify_line(linea) == c.CASE_REFERENCE


@pytest.mark.parametrize("linea", [
    "Medidas Cautelares", "Cementerio Central De Pueblo Viejo", "Retencion Ilegal De Personas Por Parte De Grupos",
    "Crímenes Cometidos Por Miembros", "Violencia Sexual Basada En Genero", "Fiscalía General De La Nación",
    "Fundacion Para La Memoria", "Comparecientes", "Abogada Victimas", "Dr. Carlos Vega Soto",
    '"Medidas Cautelares',
])
def test_cambio11_lista_de_asunto_ampliada(linea):
    assert c.classify_line(linea) == c.SUBJECT


@pytest.mark.parametrize("linea", [
    "Ana Ruiz Diaz Victima", "Juan Sala Ruiz", "Maria Magdalena Ruiz", "Luis Niño Paz", "Pedro Corte Gil",
    "Caso Ruiz Ana",
    # Revisión con MiniMax: un rol cuenta solo como primera palabra (puede ser apellido).
    "Juan Carlos Defensor", "Ana Ruiz Abogada",
])
def test_cambio11_lista_ampliada_no_toma_nombres_reales_como_asunto(linea):
    assert c.classify_line(linea) == c.PERSON


@pytest.mark.parametrize("linea", ["Caro 12 De Marzo", "Casa No 12 Ruiz", "Casino 12 De Oro"])
def test_cambio11_solo_caso_exacto_abre_una_referencia_de_caso_con_texto(linea):
    # Revisión con MiniMax: la tolerancia de una letra tomaba CARO o CASA como "Caso".
    assert c.classify_line(linea) != c.CASE_REFERENCE


@pytest.mark.parametrize("anotacion", ["(Carlos Vega Soto)", '"(Carlos Vega Soto', "( Carlos Vega Soto Alias El Mono )",
                                       "«(Carlos Vega Soto)»"])
def test_cambio11_anotacion_entre_parentesis_no_crea_fila(anotacion):
    texto = f"Luis Mora Rios\n{anotacion}"
    resultado = c.separate(_df((texto, "11111111")))

    filas = _filas(resultado)
    assert [f[NAMES] for f in filas] == ["Luis Mora Rios"]
    assert filas[0]["SEPARACIÓN"] == ""
    assert filas[0]["PERSONAS EN EL REGISTRO"] == 1
    assert resultado.marks[(0, 1)] == {c.LINES_REMOVED}
    assert c.Trace(0, texto, "Luis Mora Rios", "línea que no es de persona") in resultado.traces


def test_cambio11_anotacion_es_persona_si_las_cedulas_alcanzan():
    resultado = c.separate(_df(("Luis Mora Rios\n(Carlos Vega Soto)", GRUPO)))

    filas = _filas(resultado)
    assert [f[NAMES] for f in filas] == ["Luis Mora Rios", "(Carlos Vega Soto)"]
    assert {f["SEPARACIÓN"] for f in filas} == {"SEPARADA"}
    assert resultado.marks == {}


def test_cambio11_linea_entre_parentesis_sola_sigue_siendo_persona():
    resultado = c.separate(_df(("(Carlos Vega Soto)", "11111111")))

    assert [f[NAMES] for f in _filas(resultado)] == ["(Carlos Vega Soto)"]
    assert resultado.marks == {} and resultado.traces == []


def test_cambio11_rf68_marca_las_filas_de_una_celda_con_lineas_quitadas():
    resultado = c.separate(_df(("Ana Ruiz Diaz\nLuis Mora Paz\nMedidas Cautelares", GRUPO)))

    filas = _filas(resultado)
    assert [f[NAMES] for f in filas] == ["Ana Ruiz Diaz", "Luis Mora Paz"]
    assert resultado.marks[(0, 1)] == resultado.marks[(0, 2)] == {c.LINES_REMOVED}


@pytest.mark.parametrize("texto, sugerencia", [
    ("Juan\nPerez Gomez", "JUAN PEREZ GOMEZ"),
    ("Ana Ruiz Diaz\nLuis Mora\nPaz", "ANA RUIZ DIAZ | LUIS MORA PAZ"),
    ("Juan Perez\nGomez", "JUAN PEREZ GOMEZ"),
])
def test_cambio11_rf99_linea_de_una_palabra_queda_pendiente_con_sugerencia_de_unirla(texto, sugerencia):
    resultado = c.separate(_df((texto, "11111111")))

    filas = _filas(resultado)
    assert len(filas) == 1
    assert filas[0][NAMES] == texto
    assert filas[0]["SEPARACIÓN"] == "SIN SEPARAR"
    assert resultado.marks[(0, 1)] == {c.PENDING}
    assert resultado.pending[0] == sugerencia


def test_cambio11_rf99_aceptar_une_las_lineas():
    from src.parameters import Decisions
    texto = "Juan\nPerez Gomez"
    decisiones = Decisions(table=[(NAMES, texto, "ACEPTAR")], catalog=[])

    resultado = c.separate(_df((texto, "11111111")), decisions=decisiones)

    filas = _filas(resultado)
    assert [f[NAMES] for f in filas] == ["JUAN PEREZ GOMEZ"]
    assert resultado.pending == {}


@pytest.mark.parametrize("texto", ["Juan Perez y Ana Ruiz", "Juan Perez; Ana Ruiz"])
def test_cambio11_rf100_dos_nombres_unidos_por_y_quedan_pendientes(texto):
    # 4 palabras y una cédula: antes del cambio 11 no era celda con varios nombres.
    resultado = c.separate(_df((texto, "11111111")))

    filas = _filas(resultado)
    assert len(filas) == 1 and filas[0]["SEPARACIÓN"] == "SIN SEPARAR"
    assert resultado.pending[0] == "JUAN PEREZ | ANA RUIZ"


@pytest.mark.parametrize("texto", ["GOMEZ RUIZ, JUAN CARLOS", "Maria Gomez Y Ruiz"])
def test_cambio11_rf100_coma_de_apellidos_primero_o_partes_sin_forma_de_nombre_no_se_marcan(texto):
    resultado = c.separate(_df((texto, "11111111")))

    filas = _filas(resultado)
    assert len(filas) == 1 and filas[0]["SEPARACIÓN"] == ""
    assert resultado.pending == {}
