import pytest

from src import parameters as p

# Cédulas inventadas (principio 6).

ID_FORMAT = "formato de identificación"


# ---------------------------------------------------------------------
# Referencias de caso (RF-32)
# ---------------------------------------------------------------------

@pytest.mark.parametrize("original, final", [
    ("Caso O03", "CASO 003"),
    ("Cso 006", "CASO 006"),
    ("Caso001", "CASO 001"),
    ("Caso 3", "CASO 003"),
    ("CASO OO9", "CASO 009"),
    ("Casao 012", "CASO 012"),
])
def test_referencia_de_caso_mal_escrita_se_corrige(original, final):
    r = p.classify_identification(original)

    assert (r.final, r.state, r.motive) == (final, p.AUTOMATIC, ID_FORMAT)


@pytest.mark.parametrize("original, final", [
    ("Caso 003", "CASO 003"),
    ("caso 1234", "CASO 1234"),
    ("CASO-004", "CASO 004"),   # el guion es un signo: solo formato
])
def test_referencia_de_caso_solo_con_formato_distinto(original, final):
    r = p.classify_identification(original)

    assert r == p.Outcome(final, p.AUTOMATIC, "formato")


def test_referencia_de_caso_ya_correcta_no_cambia():
    assert p.classify_identification("CASO 003") == p.Outcome("CASO 003")


# ---------------------------------------------------------------------
# Familias de identificador de reemplazo (RF-33, cambio 4)
# ---------------------------------------------------------------------

@pytest.mark.parametrize("original, final, motive", [
    ("sin cc", "SIN CC", "formato"),
    ("Sin C.C.", "SIN CC", ID_FORMAT),
    ("Sin cédula", "SIN CC", ID_FORMAT),
    ("Sin identificación", "SIN CC", ID_FORMAT),
    ("M.c.", "M.C.", "formato"),
    ("M:C", "M.C.", "formato"),
    ("MC", "M.C.", ID_FORMAT),
    ("No aplica", "NO APLICA", "formato"),
    ("N/A", "NO APLICA", ID_FORMAT),
])
def test_familias_de_reemplazo_a_un_solo_formato(original, final, motive):
    r = p.classify_identification(original)

    assert (r.final, r.state, r.motive) == (final, p.AUTOMATIC, motive)


@pytest.mark.parametrize("ya_correcto", ["SIN CC", "M.C.", "NO APLICA"])
def test_familia_ya_escrita_bien_no_cambia(ya_correcto):
    assert p.classify_identification(ya_correcto) == p.Outcome(ya_correcto)


# ---------------------------------------------------------------------
# Identificaciones inválidas (RF-34)
# ---------------------------------------------------------------------

# Desde el cambio 5, los errores de Excel ("#¡VALOR!", "#N/A") y lo que es
# solo letras ("No registra", "Medida Cautelar", "Movice", "CASO") quedan
# POR DETERMINAR: lo prueba tests/test_parameters_cambio5.py.
@pytest.mark.parametrize("original", [
    "SC8076405",
    "TD 6149",
    "1812",                     # menos de 5 dígitos
    "12345678901234567890",     # más de 15 dígitos
    "Caso 003 y 004",
    "Caso 001-003",
    "CASO 003 Y CASO 004",
    "MACRO CASO 003",
    "12345678.",                # no es "solo dígitos"
    "123456-78901",             # un número con guion no son dos cédulas
    "12.345.678",
])
def test_identificacion_invalida_queda_pendiente_sin_sugerencia(original):
    r = p.classify_identification(original)

    assert r == p.Outcome(original, p.REVIEW, "identificación inválida")
    assert r.pending


def test_identificacion_invalida_conserva_el_texto_de_un_numero():
    # 1812 llega como número: se conserva su texto, sin ".0".
    assert p.classify_identification(1812.0) == p.Outcome("1812", p.REVIEW, "identificación inválida")


# ---------------------------------------------------------------------
# Cédulas (RF-35) y vacíos (RF-21)
# ---------------------------------------------------------------------

@pytest.mark.parametrize("original", [" 12345678 ", 12345678.0, 12345678, "12345678"])
def test_cedula_sin_espacios_ni_decimales(original):
    r = p.classify_identification(original)

    assert r.final == "12345678"
    assert not r.pending


def test_cedula_con_espacios_alrededor_es_solo_formato():
    assert p.classify_identification(" 12345678 ") == p.Outcome("12345678", p.AUTOMATIC, "formato")


def test_cedula_guardada_como_numero_no_cambia():
    assert p.classify_identification(12345678.0) == p.Outcome("12345678")


@pytest.mark.parametrize("original", ["12345", "123456789012345"])
def test_cedula_de_5_a_15_digitos(original):
    assert p.classify_identification(original) == p.Outcome(original)


@pytest.mark.parametrize("vacio", [None, float("nan"), "", "   ", "-"])
def test_vacio_es_por_determinar(vacio):
    # Cambio 6 (RF-21): antes quedaba vacío sin marca. "-" cuenta como
    # vacío porque solo tiene signos (clave de formato vacía, desde T5).
    assert p.classify_identification(vacio) == p.Outcome("POR DETERMINAR", p.AUTOMATIC, "vacío")


# ---------------------------------------------------------------------
# Varias líneas o varias cédulas en una celda
# ---------------------------------------------------------------------

def test_varias_cedulas_por_linea_se_conservan():
    r = p.classify_identification("12345678\n 87654321 ")

    assert r == p.Outcome("12345678\n87654321", p.AUTOMATIC, "formato")


def test_varias_cedulas_separadas_por_espacio_se_conservan():
    assert p.classify_identification("12345678 87654321") == p.Outcome("12345678 87654321")


def test_cada_linea_se_escribe_con_su_formato():
    r = p.classify_identification("Caso O03\n12345678")

    assert (r.final, r.state, r.motive) == ("CASO 003\n12345678", p.AUTOMATIC, ID_FORMAT)


def test_una_linea_invalida_deja_pendiente_toda_la_celda():
    r = p.classify_identification("12345678\nNo registra")

    assert r == p.Outcome("12345678\nNo registra", p.REVIEW, "identificación inválida")
