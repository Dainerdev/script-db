from src import catalog

# Similitudes (fuzz.ratio) de los valores de prueba, medidas con rapidfuzz:
#   cadena: ABCDE–ABCDEXX 83,3 · ABCDEXX–ABCDEXXYY 87,5 · ABCDE–ABCDEXXYY 71,4
#   empate: ABCDE–ABCDEXX 83,3 · ABCDE–XXABCDE 83,3 · ABCDEXX–XXABCDE 71,4
#   SR–SRV 80,0 · "1 DELEGADA"–"2 DELEGADA" 90,0 · "SIN CC"–"SIN C" 90,9


def test_group_cadena_no_encadena_c_con_la_apertura_de_a():
    grupos = catalog.group({"ABCDE": 10, "ABCDEXX": 5, "ABCDEXXYY": 1}, "SOLICITUD")

    assert grupos["ABCDE"] == "ABCDE"
    assert grupos["ABCDEXX"] == "ABCDE"
    # C se parece a B (87,5) pero no a la apertura A (71,4): abre su grupo.
    assert grupos["ABCDEXXYY"] == "ABCDEXXYY"


def test_group_numeros_distintos_nunca_van_al_mismo_grupo():
    grupos = catalog.group({"1 DELEGADA": 10, "2 DELEGADA": 5}, "DECISIÓN")

    assert grupos["1 DELEGADA"] != grupos["2 DELEGADA"]


def test_group_sala_no_agrupa_codigos_por_parecido():
    en_sala = catalog.group({"SRV": 10, "SR": 5}, "SALA")
    assert en_sala["SR"] == "SR"
    assert en_sala["SRV"] == "SRV"

    # Control: en una categoría, 80 alcanza para agrupar; en SALA lo impide RF-15.
    en_categoria = catalog.group({"SRV": 10, "SR": 5}, "SOLICITUD")
    assert en_categoria["SR"] == "SRV"


def test_group_identificacion_no_agrupa_por_parecido():
    grupos = catalog.group({"SIN CC": 10, "SIN C": 3}, "IDENTIFICACIÓN")

    assert grupos["SIN C"] == "SIN C"


def test_group_valor_con_similitud_menor_a_80_abre_grupo():
    grupos = catalog.group({"REQUERIMIENTO": 10, "AUDIENCIA": 5}, "DECISIÓN")

    assert grupos["AUDIENCIA"] == "AUDIENCIA"


def test_group_empate_va_al_grupo_con_mas_filas():
    primero = catalog.group({"ABCDEXX": 10, "XXABCDE": 8, "ABCDE": 1}, "SOLICITUD")
    assert primero["ABCDE"] == "ABCDEXX"

    # Mismas claves con las filas al revés: gana el otro, así que decide
    # la cantidad de filas y no el orden de llegada.
    al_reves = catalog.group({"ABCDEXX": 8, "XXABCDE": 10, "ABCDE": 1}, "SOLICITUD")
    assert al_reves["ABCDE"] == "XXABCDE"


def test_group_compara_contra_todas_las_aperturas_y_ve_typos_en_la_primera_letra():
    grupos = catalog.group(
        {"AUDIENCIA": 10, "ACREDITAR": 9, "REQUERIMIENTO": 8, "EQUERIMIENTO": 1},
        "DECISIÓN",
    )

    assert grupos["EQUERIMIENTO"] == "REQUERIMIENTO"


def test_group_suma_las_filas_de_las_variantes_de_formato():
    # "Fuerza Publica" + "fuerza pública" = 8 filas con la misma clave, más
    # que "FUERZA PUBLICAS" (6): esa clave abre el grupo y la otra se une.
    grupos = catalog.group(
        {"Fuerza Publica": 5, "fuerza pública": 3, "FUERZA PUBLICAS": 6},
        "PERTENECE",
    )

    assert grupos == {"FUERZA PUBLICA": "FUERZA PUBLICA", "FUERZA PUBLICAS": "FUERZA PUBLICA"}


def test_group_ignora_vacios():
    grupos = catalog.group({"  ": 4, "\xa0": 2, "SAI": 2}, "SALA")

    assert grupos == {"SAI": "SAI"}


# ---------------------------------------------------------------------
# Valor del catálogo de un grupo (RF-5 a RF-8, RF-62 a RF-64)
# ---------------------------------------------------------------------

def test_representative_prefiere_la_variante_con_tildes_aunque_tenga_menos_filas():
    valor = catalog.representative({"Fuerza Publica": 10, "Fuerza Pública": 2}, "PERTENECE")

    assert valor == "FUERZA PÚBLICA"


def test_representative_sin_tildes_elige_la_variante_de_mas_filas():
    # Misma clave; difieren en el guion: gana la escritura de más filas.
    valor = catalog.representative(
        {"Manifiesta ser FARC-EP": 10, "Manifiesta ser FARC EP": 3}, "PERTENECE"
    )

    assert valor == "MANIFIESTA SER FARC-EP"


def test_representative_typo_elige_la_de_mas_filas():
    valor = catalog.representative({"Requerimiento": 10, "Rewquerimiento": 1}, "DECISIÓN")

    assert valor == "REQUERIMIENTO"


def test_representative_toma_tildes_de_otra_variante_del_grupo():
    # RF-7: "con las tildes que traiga alguna variante del grupo".
    valor = catalog.representative({"Accion de tutela": 10, "Acción de tutelar": 2}, "SOLICITUD")

    assert valor == "ACCIÓN DE TUTELA"


def test_representative_prefiere_la_mas_completa():
    valor = catalog.representative(
        {"MANIFIESTA SER FARC": 10, "MANIFIESTA SER FARC EP": 4}, "PERTENECE"
    )

    assert valor == "MANIFIESTA SER FARC EP"


def test_representative_entre_varias_mas_completas_la_de_mas_filas():
    valor = catalog.representative(
        {"SOMETIMIENTO": 10, "SOMETIMIENTO JEP": 3, "SOMETIMIENTO A LA JEP": 5}, "SOLICITUD"
    )

    assert valor == "SOMETIMIENTO A LA JEP"


def test_representative_nombre_con_variantes_solo_de_formato_se_escribe_como_rf8():
    valor = catalog.representative(
        {"José Wilmer Cardona Sánchez": 5, "JOSE WILMER CARDONA SANCHEZ": 3}, "MAGISTRADO"
    )

    # En nombres no se prefiere la variante con tildes: RF-8 las quita.
    assert valor == "JOSE WILMER CARDONA SANCHEZ"


def test_representative_nombre_prefiere_la_enie_aunque_tenga_menos_filas():
    valor = catalog.representative(
        {"MARCELA VALERIO MUNOZ": 10, "Marcela Valerio Muñoz": 3}, "MAGISTRADO"
    )

    assert valor == "MARCELA VALERIO MUÑOZ"


def test_representative_conserva_la_dieresis_en_nombres():
    valor = catalog.representative({"Luis Argüello": 2}, "NOMBRES_APELLIDOS")

    assert valor == "LUIS ARGÜELLO"


def test_representative_grupo_vacio():
    assert catalog.representative({"  ": 3}, "SALA") == ""


def test_representative_palabra_repetida_no_es_mas_completa():
    # Cambio 2 (RF-62): "FARC-EP-EP" repite "EP"; no agrega una palabra distinta.
    valor = catalog.representative(
        {"Manifiesta ser FARC-EP": 50, "Manifiesta ser FARC-EP-EP": 1}, "PERTENECE"
    )

    assert valor == "MANIFIESTA SER FARC-EP"


# ---------------------------------------------------------------------
# Cambio 2 (T23): negación y palabras de más (RF-82, RF-83)
# Similitudes: AVOCAR/NO AVOCAR 92,7 · AVOCAR EL/NO AVOCAR 86,4 ·
# REQUERIMIENTO/+PGN 86,7 · ACREDITACION (DE) VICTIMAS 93,3 · ANA MANUELA
# PARRA/+ARIAS 85,0 — todas ≥80: solo las reglas nuevas pueden separarlas.
# ---------------------------------------------------------------------

def test_group_nunca_junta_un_valor_con_su_negacion():
    grupos = catalog.group({"AVOCAR CONOCIMIENTO": 10, "NO AVOCAR CONOCIMIENTO": 5}, "DECISIÓN")

    assert grupos["NO AVOCAR CONOCIMIENTO"] == "NO AVOCAR CONOCIMIENTO"


def test_group_negacion_aunque_un_articulo_iguale_la_cantidad_de_palabras():
    grupos = catalog.group({"AVOCAR EL CONOCIMIENTO": 10, "NO AVOCAR CONOCIMIENTO": 5}, "DECISIÓN")

    assert grupos["NO AVOCAR CONOCIMIENTO"] == "NO AVOCAR CONOCIMIENTO"


def test_group_categoria_no_junta_valores_con_palabras_de_mas():
    grupos = catalog.group({"REQUERIMIENTO": 10, "REQUERIMIENTO PGN": 5}, "DECISIÓN")

    assert grupos["REQUERIMIENTO PGN"] == "REQUERIMIENTO PGN"


def test_group_categoria_las_particulas_no_cuentan_como_palabras():
    grupos = catalog.group({"ACREDITACION VICTIMAS": 10, "ACREDITACION DE VICTIMAS": 5}, "SOLICITUD")

    assert grupos["ACREDITACION DE VICTIMAS"] == "ACREDITACION VICTIMAS"


def test_group_nombres_si_juntan_el_nombre_incompleto_con_el_completo():
    # RF-83 es solo para categorías: en nombres todo typo va a revisión, y el
    # incompleto tiene que poder sugerir el completo (RF-62).
    grupos = catalog.group(
        {"ANA MANUELA PARRA ARIAS": 10, "ANA MANUELA PARRA": 2}, "MAGISTRADO"
    )

    assert grupos["ANA MANUELA PARRA"] == "ANA MANUELA PARRA ARIAS"
