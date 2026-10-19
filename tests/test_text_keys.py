import math

import pytest

from src import text_keys as tk


# ---------------------------------------------------------------------
# Clave de formato (definición "diferencia solo de formato" de la spec)
# ---------------------------------------------------------------------

@pytest.mark.parametrize("a, b", [
    ("Fuerza Publica", "  fuerza   pública. "),
    ("Victima", "Víctima"),
    ("COORDINACIÓN", "cOORDINACIón"),
    ("Manifiesta ser FARC-EP", "MANIFIESTA SER FARC EP"),
    ("SAI", "SAI\xa0"),
    ("Andrés", "ANDRES"),
])
def test_format_key_iguala_diferencias_solo_de_formato(a, b):
    assert tk.format_key(a) == tk.format_key(b)


def test_format_key_quita_tildes_de_vocales_pero_no_la_enie_ni_la_dieresis():
    assert tk.format_key("Muñoz") == "MUÑOZ"
    assert tk.format_key("Argüello") == "ARGÜELLO"
    assert tk.format_key("José Sánchez") == "JOSE SANCHEZ"


def test_format_key_munoz_y_munoz_sin_enie_no_son_el_mismo_valor():
    assert tk.format_key("MUÑOZ") != tk.format_key("MUNOZ")


def test_format_key_puntuacion_y_espacios_invisibles_a_un_solo_espacio():
    assert tk.format_key("ARCHIVADO-DEVOLUCIÓN-NO MISIONAL") == "ARCHIVADO DEVOLUCION NO MISIONAL"
    assert tk.format_key("#¡VALOR!") == "VALOR"
    assert tk.format_key("\xa0") == ""
    assert tk.format_key("S​AI") == "SAI"


def test_format_key_saltos_de_linea_son_espacio_en_columnas_comunes():
    assert tk.format_key("Regimen de\nCondicionalidad", "SOLICITUD") == "REGIMEN DE CONDICIONALIDAD"
    assert tk.format_key("Ana Torres\nPedro Ruiz", "MAGISTRADO") == "ANA TORRES PEDRO RUIZ"


@pytest.mark.parametrize("column", ["NOMBRES_APELLIDOS", "IDENTIFICACIÓN"])
def test_format_key_conserva_saltos_de_linea_donde_separan_personas(column):
    assert tk.format_key("  juan  pérez \n\n ana gómez ", column) == "JUAN PEREZ\nANA GOMEZ"


def test_format_key_numeros_sin_decimal_cero():
    assert tk.format_key(12345678.0) == "12345678"
    assert tk.format_key(44317) == "44317"


@pytest.mark.parametrize("vacio", [None, float("nan"), "", "   "])
def test_format_key_de_vacios_es_texto_vacio(vacio):
    assert tk.format_key(vacio) == ""


# ---------------------------------------------------------------------
# Texto de un valor crudo (RF-35: sin ".0" cuando Excel guarda un número)
# ---------------------------------------------------------------------

def test_to_text_numeros_enteros_sin_decimales():
    assert tk.to_text(12345678.0) == "12345678"
    assert tk.to_text(44317) == "44317"
    assert tk.to_text(44468.0076) == "44468.0076"


def test_to_text_vacios():
    assert tk.to_text(None) == ""
    assert tk.to_text(math.nan) == ""


# ---------------------------------------------------------------------
# Firma de números (RF-17)
# ---------------------------------------------------------------------

def test_firma_de_numeros_distingue_delegadas():
    assert tk.number_signature("1 DELEGADA") != tk.number_signature("2 DELEGADA")


def test_firma_de_numeros_compara_valores_no_ceros_a_la_izquierda():
    assert tk.number_signature("CASO 003") == tk.number_signature("CASO 3") == (3,)


def test_firma_de_numeros_vacia_sin_digitos():
    assert tk.number_signature("SOLICITUD DE INFORMACION") == ()


# ---------------------------------------------------------------------
# Similitud con fuzz.ratio (Decisión #2) — ejemplos de referencia de la spec
# ---------------------------------------------------------------------

def _sim(a, b, column=None):
    return tk.similarity(tk.format_key(a, column), tk.format_key(b, column))


def test_similitud_marcelo_marcela_es_90_o_mas():
    assert _sim("Marcelo Valerio Muñoz", "Marcela Valerio Muñoz", "MAGISTRADO") >= 90


def test_similitud_rewquerimiento_requerimiento_es_90_o_mas():
    assert _sim("Rewquerimiento", "Requerimiento", "DECISIÓN") >= 90


def test_similitud_delegadas_es_alta_pero_la_firma_las_separa():
    # Por esto existe RF-17: la similitud sola los unificaría.
    assert _sim("1 DELEGADA", "2 DELEGADA") >= 90
    assert tk.number_signature(tk.format_key("1 DELEGADA")) != tk.number_signature(tk.format_key("2 DELEGADA"))


def test_similitud_identica_es_100_y_es_simetrica():
    assert tk.similarity("REQUERIMIENTO", "REQUERIMIENTO") == 100
    assert tk.similarity("SRV", "SR") == tk.similarity("SR", "SRV")


# ---------------------------------------------------------------------
# Escritura final por tipo de columna (RF-7, RF-8, RF-35)
# ---------------------------------------------------------------------

def test_render_categoria_mayusculas_conservando_tildes_y_signos():
    assert tk.render("Víctima", "PERTENECE") == "VÍCTIMA"
    assert tk.render("  Fuerza  Pública ", "PERTENECE") == "FUERZA PÚBLICA"
    assert tk.render("Manifiesta ser FARC-EP", "PERTENECE") == "MANIFIESTA SER FARC-EP"
    assert tk.render("Regimen de\nCondicionalidad", "SOLICITUD") == "REGIMEN DE CONDICIONALIDAD"


def test_render_nombre_propio_sin_tildes_con_enie_y_dieresis():
    assert tk.render("Muñóz", "MAGISTRADO") == "MUÑOZ"
    assert tk.render("José Wilmer Cardona Sánchez", "MAGISTRADO") == "JOSE WILMER CARDONA SANCHEZ"
    assert tk.render("Argüello", "FUNCIONARIO A CARGO") == "ARGÜELLO"


def test_render_nombres_apellidos_conserva_una_linea_por_persona():
    assert tk.render(" maría  josé \n\n ana ", "NOMBRES_APELLIDOS") == "MARIA JOSE\nANA"


def test_render_identificacion_cedula_sin_decimales_ni_espacios():
    assert tk.render(12345678.0, "IDENTIFICACIÓN") == "12345678"
    assert tk.render(" 12345678 ", "IDENTIFICACIÓN") == "12345678"


def test_render_vacio_queda_vacio():
    assert tk.render(None, "SALA") == ""


# ---------------------------------------------------------------------
# Tipos de columna (definiciones de la spec)
# ---------------------------------------------------------------------

def test_tipos_de_las_diez_columnas_estandarizadas():
    assert tk.COLUMN_TYPES == {
        "TIPO DE EXPEDIENTE": "fixed_list",
        "DELEGADA": "fixed_list",
        "SALA": "short_code",
        "SOLICITUD": "category",
        "DECISIÓN": "category",
        "PERTENECE": "category",
        "NOMBRES_APELLIDOS": "proper_name",
        "MAGISTRADO": "proper_name",
        "FUNCIONARIO A CARGO": "proper_name",
        "IDENTIFICACIÓN": "identification",
    }
