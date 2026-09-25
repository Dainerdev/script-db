import pandas as pd
import re
import unicodedata
import difflib
from collections import defaultdict
from rapidfuzz import process, fuzz

# ============================================================
# DIAGNÓSTICO GENERAL
# ============================================================

def run_diagnostics(df):
    """
    Ejecuta el diagnóstico general en un solo recorrido de columnas.
    Retorna:
    (columnas, nulos, únicos, problemas_texto, longitudes)
    """
    total = len(df)
    filas_columns, filas_nulls, filas_unique = [], [], []
    filas_text, filas_length = [], []

    for column in df.columns:
        serie = df[column]
        nulls = serie.isnull().sum()
        unique = serie.nunique(dropna=True)
        pct_nulls = round((nulls / total) * 100, 2) if total else 0

        filas_columns.append({
            "Columna": column,
            "Tipo": str(serie.dtype),
            "Total": total,
            "Nulos": nulls,
            "Porcentaje Nulos": pct_nulls,
            "Unicos": unique,
            "Duplicados": total - unique - nulls,
        })

        filas_nulls.append({
            "Columna": column,
            "Total": total,
            "Nulos": nulls,
            "Porcentaje Nulos": pct_nulls,
        })

        filas_unique.append({
            "Columna": column,
            "Total": total,
            "Unicos": unique,
            "Porcentaje Unicos": round((unique / total) * 100, 2) if total else 0,
        })

        es_texto = pd.api.types.is_string_dtype(serie) or serie.dtype == "object"

        if es_texto:
            data = serie.dropna().astype(str)

            filas_text.append({
                "Columna": column,
                "Total": total,
                "Espacios Iniciales": data.str.match(r"^\s+").sum(),
                "Espacios Finales": data.str.match(r".*\s+$").sum(),
                "Múltiples Espacios": data.str.contains(r"\s{2,}", regex=True).sum(),
            })

            filas_length.append({
                "Columna": column,
                "Total": total,
                "Longitud Mínima": data.str.len().min(),
                "Longitud Máxima": data.str.len().max(),
                "Longitud Promedio": round(data.str.len().mean(), 2),
            })

    return (
        pd.DataFrame(filas_columns),
        pd.DataFrame(filas_nulls),
        pd.DataFrame(filas_unique),
        pd.DataFrame(filas_text),
        pd.DataFrame(filas_length),
    )


# ============================================================
# NORMALIZACIÓN Y ANOMALÍAS
# ============================================================

def normalizar_texto(valor):
    if pd.isna(valor):
        return ""

    texto = str(valor).strip()
    return re.sub(r"\s+", " ", texto).upper()


def detectar_tipo_valor(valor):
    if pd.isna(valor):
        return "VACÍO"

    texto = str(valor).strip()

    if not texto:
        return "VACÍO"

    if re.fullmatch(r"\d+", texto):
        return "NUMÉRICO"

    if re.fullmatch(r"\d+[/-]\d+[/-]\d+", texto):
        return "FECHA"

    if re.search(r"\d", texto) and re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", texto):
        return "MIXTO"

    return "TEXTO"


def detectar_anomalia(valor, columna):
    tipo = detectar_tipo_valor(valor)

    columnas_nombres = [
        "NOMBRES_APELLIDOS",
        "MAGISTRADO",
        "FUNCIONARIO A CARGO",
        "DELEGADA",
    ]

    if columna in columnas_nombres:
        if tipo == "NUMÉRICO":
            return "POSIBLE NÚMERO EN COLUMNA DE TEXTO"
        if tipo == "FECHA":
            return "POSIBLE FECHA EN COLUMNA DE TEXTO"

    if columna == "IDENTIFICACIÓN" and tipo == "TEXTO":
        return "IDENTIFICACIÓN NO NUMÉRICA"

    return ""


# ============================================================
# NORMALIZACIÓN PARA SCORING (no afecta el valor propuesto)
# ============================================================
 
def _normalizar_para_score(valor):
    """
    Mayúsculas + sin tildes, SOLO para calcular similitud. El VALOR
    PROPUESTO sigue viniendo del parámetro/candidato original (bien
    escrito); esto solo evita que una diferencia de case/tilde cuente
    como si fuera un error de tipeo real.
    """
    return unicodedata.normalize("NFKD", str(valor).upper()).encode("ascii", "ignore").decode("utf-8")
 
 
def _score(a, b):
    """
    Máximo entre token_sort_ratio (tolera errores de tipeo) y
    token_set_ratio (tolera que falte una palabra, ej. un apellido).
    FIX: fuzz.ratio sobre las cadenas crudas era sensible a
    mayúsculas/tildes -'Fisico' vs 'FÍSICO' daba 16.67 en vez de ~100,
    y 'híbrido' en minúsculas llegaba a emparejarse mal con 'FÍSICO'
    (score 0, ganaba por ser el "menos malo" de una lista de puros
    ceros).
    """
    a2, b2 = _normalizar_para_score(a), _normalizar_para_score(b)
    return max(fuzz.token_sort_ratio(a2, b2), fuzz.token_set_ratio(a2, b2))
 
 
# ============================================================
# IDENTIFICACIÓN DE PARÁMETROS
# ============================================================

def comparar_con_parametros(df, columna, parametros, threshold=90):
    """
    Compara valores contra un catálogo conocido.
    >= threshold -> AUTOMÁTICO
    < threshold  -> PARA REVISAR
    """
    resultados = []
    
    serie = df[columna].dropna().astype(str).str.strip()
    frecuencias = serie.value_counts()  # una sola pasada, no una por valor

    for valor in frecuencias.index:
        resultado = process.extractOne(
            valor,
            parametros,
            scorer=fuzz.ratio,
        )

        if resultado is None:
            continue

        propuesta, score, _ = resultado

        resultados.append({
            "COLUMNA": columna,
            "VALOR ORIGINAL": valor,
            "VALOR PROPUESTO": propuesta,
            "SCORE": round(score, 2),
            "ESTADO": "AUTOMÁTICO" if score >= threshold else "PARA REVISAR",
            "FRECUENCIA": int(frecuencias[valor]),
            "ANOMALÍA": detectar_anomalia(valor, columna),
        })

    return pd.DataFrame(resultados)

# ============================================================
# DESCUBRIMIENTO DE VARIANTES (sin catálogo cerrado)
# ============================================================
def _agrupar_por_representante(valores, frecuencias, umbral):
    """
    Agrupa valores por similitud SIN transitividad (a diferencia de
    union-find). Cada grupo tiene un único "representante" fijo -el
    canónico- y un valor solo entra al grupo si se parece DIRECTAMENTE
    a ese representante, nunca por una cadena de intermediarios.
 
    Por qué no union-find: con columnas de texto libre (SOLICITUD,
    DECISIÓN...) que comparten vocabulario jurídico común, es muy fácil
    que A se parezca a B, B se parezca a C, y C se parezca a D, aunque A
    y D no tengan nada que ver -union-find los mete a todos en el mismo
    grupo igual (encadenamiento transitivo). Ejemplo real: "Abstenerse
    de dar tramite" terminaba agrupado con "Abstenerse de avocar
    conocimiento" (score real entre ambos: 68.97, muy por debajo del
    umbral) solo porque ambos pasaban por una cadena de valores
    intermedios que sí superaban el umbral entre sí.
 
    Se procesan los valores de MÁS a MENOS frecuente, así los
    representantes tienden a ser la forma más usada (probablemente la
    correcta) en vez de un valor aleatorio.
    """
    ordenados = sorted(valores, key=lambda v: (-frecuencias.get(v, 0), -len(v)))
    representantes = []  # lista de valores que actúan como ancla de un grupo
    miembros = defaultdict(list)  # representante -> [valores del grupo]
 
    for valor in ordenados:
        mejor_rep, mejor_score = None, -1
        for rep in representantes:
            score = _score(valor, rep)
            if score >= umbral and score > mejor_score:
                mejor_rep, mejor_score = rep, score
        if mejor_rep is None:
            representantes.append(valor)
            miembros[valor].append(valor)
        else:
            miembros[mejor_rep].append(valor)
 
    return miembros


def crear_tabla_similitudes(df, columna, threshold=90, limit=5, block_size=None, max_block_size=500, forzar_revision=False):
    """
    Descubre variantes similares dentro de una misma columna y las agrupa
    en UN solo parámetro por grupo. No modifica los datos.
 
    `forzar_revision=True`: marca TODO como "PARA REVISAR" (nunca
    "AUTOMÁTICO"), sin importar el score. Pensado para NOMBRES_APELLIDOS
    y otras columnas de nombres propios donde fusionar dos valores por
    error no es solo una categoría mal escrita, sino potencialmente
    mezclar la identidad de dos personas distintas -eso siempre debe
    confirmarlo una persona, incluso con score 100.
 
    FIX (2 rondas):
    1. La versión con top-5 vecinos por fila no resolvía a un único
       parámetro -un mismo valor podía terminar con varias propuestas
       distintas.
    2. La versión con union-find sí resolvía a un único parámetro, pero
       el encadenamiento transitivo mezclaba valores que en realidad no
       se parecen (ver docstring de _agrupar_por_representante). Ahora
       cada valor se compara SOLO contra el representante de cada grupo,
       nunca contra un miembro cualquiera -sin cadenas.
 
    OJO con columnas de nombres propios (NOMBRES_APELLIDOS, MAGISTRADO,
    FUNCIONARIO A CARGO): sin un diccionario que valide ortografía, el
    desempate por longitud puede favorecer una variante mal escrita si
    por azar tiene una letra de más. Con frecuencias muy parejas (pocos
    registros por persona) trata el resultado como PARA REVISAR siempre,
    sin importar el score -apóyate mejor en check_duplicate_names_by_id,
    que usa la cédula como referencia real.
 
    `limit` se deja por compatibilidad con la firma anterior; ya no se
    usa (no hay múltiples filas por valor que limitar).
 
    RENDIMIENTO (`block_size`): _agrupar_por_representante compara cada
    valor nuevo contra TODOS los representantes ya creados -si casi nada
    se agrupa (columnas de texto libre con miles de valores realmente
    distintos, ej. NOMBRES_APELLIDOS), eso se acerca a O(n²) y se vuelve
    lento (6.000 nombres sin nada en común: ~40s en la prueba). Con
    `block_size` (ej. 4) se agrupan primero los valores por sus primeras
    N letras (usando la misma normalización de mayúsculas/tildes del
    score) y solo se comparan entre sí los de un mismo bloque -igual
    estrategia que ya usas en check_fuzzy_duplicate_names. Limitación
    conocida (la misma que ya documentaste allá): un error de tipeo en
    la PRIMERA letra ("Iuan Perez" en vez de "Juan Perez") no se
    detecta, porque cae en otro bloque. Para columnas con pocos valores
    únicos (SALA, TIPO DE EXPEDIENTE) deja `block_size=None`, no lo
    necesitan.
    """

    valores = [
        v for v in df[columna].dropna().astype(str).str.strip().unique().tolist() if v
    ]
    frecuencias = df[columna].astype(str).str.strip().value_counts()
 
    if block_size:
        bloques = defaultdict(list)
        for v in valores:
            bloques[_normalizar_para_score(v)[:block_size]].append(v)
 
        grupos_por_rep = {}
        for candidatos in bloques.values():
            if len(candidatos) > max_block_size:
                print(f"  (crear_tabla_similitudes: bloque de {len(candidatos)} valores "
                      f"omitido por tamaño en '{columna}' -sube max_block_size si quieres "
                      f"incluirlo, o revisa ese prefijo aparte)")
                for v in candidatos:
                    grupos_por_rep[v] = [v]  # se dejan como grupo propio, sin comparar
                continue
            grupos_por_rep.update(_agrupar_por_representante(candidatos, frecuencias, threshold))
    else:
        grupos_por_rep = _agrupar_por_representante(valores, frecuencias, threshold)
 
    resultados = []
    for canonico, grupo in grupos_por_rep.items():
        for valor in grupo:
            score = 100.0 if valor == canonico else _score(valor, canonico)
            es_el_mismo = valor == canonico
            if forzar_revision and not es_el_mismo:
                estado = "PARA REVISAR"
            else:
                estado = "AUTOMÁTICO" if score >= threshold else "PARA REVISAR"
            resultados.append({
                "COLUMNA": columna,
                "VALOR ORIGINAL": valor,
                "VALOR PROPUESTO": canonico,
                "SCORE": round(score, 2),
                "ESTADO": estado,
                "FRECUENCIA ORIGINAL": int(frecuencias.get(valor, 0)),
                "FRECUENCIA PROPUESTA": int(frecuencias.get(canonico, 0)),
                "ANOMALÍA": detectar_anomalia(valor, columna),
            })
 
    if not resultados:
        return pd.DataFrame(columns=[
            "COLUMNA", "VALOR ORIGINAL", "VALOR PROPUESTO",
            "SCORE", "ESTADO", "FRECUENCIA ORIGINAL",
            "FRECUENCIA PROPUESTA", "ANOMALÍA"
        ])
 
    return (
        pd.DataFrame(resultados)
        .sort_values(["ESTADO", "FRECUENCIA ORIGINAL"], ascending=[True, False])
        .reset_index(drop=True)
    )


# ============================================================
# IDENTIFICACIÓN EXACTA DE IDENTIFICACIONES
# ============================================================

def normalizar_identificacion(serie):
    """
    Normaliza identificaciones sin utilizar fuzzy matching.
    Se eliminan espacios, puntos y guiones.
    """
    return (
        serie.astype("string")
        .str.strip()
        .str.replace(r"[\s.\-]", "", regex=True)
    )


# ============================================================
# DUPLICADOS
# ============================================================

def check_duplicates(df, subset=None):
    mask = df.duplicated(subset=subset, keep=False)
    duplicate_rows = df[mask].copy()
    duplicate_rows.insert(0, "Fila Duplicada", duplicate_rows.index + 2)
    return duplicate_rows


def check_duplicate_names_by_id(
    df,
    id_col="IDENTIFICACIÓN",
    name_col="NOMBRES_APELLIDOS",
):
    temp = df[[id_col, name_col]].dropna().copy()

    temp[id_col] = normalizar_identificacion(temp[id_col])
    temp[name_col] = (
        temp[name_col].astype(str).str.strip()
    )

    es_cedula_real = temp[id_col].str.match(r"^\d{5,15}$", na=False)
    temp = temp[es_cedula_real]

    grouped = temp.groupby(id_col)[name_col].agg(
        lambda x: sorted(set(x))
    )
    inconsistentes = grouped[grouped.apply(len) > 1]

    result = pd.DataFrame({
        "IDENTIFICACION": inconsistentes.index,
        "Variantes_Nombre": inconsistentes.values,
        "N_Variantes": inconsistentes.apply(len),
    })

    return (
        result
        .sort_values("N_Variantes", ascending=False)
        .reset_index(drop=True)
    )


def check_fuzzy_duplicate_names(
    names,
    threshold=0.90,
    block_size=8,
    max_block_size=300,
):
    """
    Mantiene el análisis anterior de nombres, usando difflib.
    RapidFuzz se utiliza en los nuevos análisis de parámetros.
    """
    unique_names = pd.Series(names).dropna().astype(str).unique()

    blocks = defaultdict(list)
    for name in unique_names:
        blocks[name[:block_size]].append(name)

    omitidos = []
    posibles = []

    for prefijo, candidatos in blocks.items():
        if len(candidatos) < 2:
            continue

        if len(candidatos) > max_block_size:
            omitidos.append({
                "Prefijo": prefijo,
                "N_Nombres": len(candidatos),
            })
            continue

        for i in range(len(candidatos)):
            a = candidatos[i]

            for j in range(i + 1, len(candidatos)):
                b = candidatos[j]

                longest = max(len(a), len(b))
                if longest == 0:
                    continue

                if (
                    1 - abs(len(a) - len(b)) / longest
                ) < threshold:
                    continue

                score = difflib.SequenceMatcher(
                    None, a, b
                ).ratio()

                if score >= threshold:
                    posibles.append({
                        "Nombre_A": a,
                        "Nombre_B": b,
                        "Similitud": round(score, 3),
                    })

    df_posibles = pd.DataFrame(
        posibles,
        columns=["Nombre_A", "Nombre_B", "Similitud"],
    )

    if not df_posibles.empty:
        df_posibles = df_posibles.sort_values(
            "Similitud",
            ascending=False,
        ).reset_index(drop=True)

    df_omitidos = pd.DataFrame(
        omitidos,
        columns=["Prefijo", "N_Nombres"],
    )

    return df_posibles, df_omitidos


# ============================================================
# REPORTE DE SIMILITUD
# ============================================================

def run_similarity_report(df):
    print("\nEJECUTANDO ANÁLISIS DE DUPLICADOS Y SIMILITUD...\n")

    if "RADICADO IUS" in df.columns and "No" in df.columns:
        ius_por_registro = df.groupby("RADICADO IUS")["No"].nunique()
        ius_duplicados = ius_por_registro[ius_por_registro > 1]
        print(
            f"[*] Radicados IUS duplicados: "
            f"{len(ius_duplicados)}"
        )

    if (
        "IDENTIFICACIÓN" in df.columns
        and "NOMBRES_APELLIDOS" in df.columns
    ):
        nombres_por_cedula = check_duplicate_names_by_id(df)
        print(
            f"[*] Cédulas con múltiples variantes de nombre: "
            f"{len(nombres_por_cedula)}"
        )

    if "NOMBRES_APELLIDOS" in df.columns:
        nombres_fuzzy, omitidos = check_fuzzy_duplicate_names(
            df["NOMBRES_APELLIDOS"]
        )
        print(
            f"[*] Posibles nombres duplicados por similitud: "
            f"{len(nombres_fuzzy)}"
        )
        print(
            f"[*] Bloques de nombres omitidos por tamaño: "
            f"{len(omitidos)}"
        )


# ============================================================
# SEPARACIÓN POR ESTADO
# ============================================================

def split_by_status(df):
    print("\nSEPARANDO DATOS: ARCHIVADOS Y RETIRADOS...\n")

    clasificacion = (
        df["CLASIFICACIÓN DEL RADICADO"].astype(str).str.upper()
    )
    funcionario_cargo = (
        df["FUNCIONARIO A CARGO"].astype(str).str.upper()
    )

    mask_retirados = funcionario_cargo.str.contains(
        "RETIRADOS", na=False
    )

    mask_archivado = (
        (
            clasificacion.str.contains("ARCHIVADO", na=False)
            | funcionario_cargo.str.contains("ARCHIVADO", na=False)
        )
        & ~mask_retirados
    )

    df_retirados = df.loc[mask_retirados].copy()
    df_archivados = df.loc[mask_archivado].copy()
    df_activos = df.loc[
        ~mask_archivado & ~mask_retirados
    ].copy()

    clasificacion_activos = (
        df_activos["CLASIFICACIÓN DEL RADICADO"]
        .astype(str)
        .str.upper()
    )
    mask_sim = clasificacion_activos.str.contains(
        "SIM", na=False
    )

    df_sim = df_activos.loc[mask_sim].copy()

    print(f" -> Registros Base Activa: {len(df_activos)}")
    print(f" -> Registros SIM: {len(df_sim)}")
    print(f" -> Registros Archivados: {len(df_archivados)}")
    print(f" -> Registros Retirados: {len(df_retirados)}")

    return {
        "activos": df_activos,
        "archivados": df_archivados,
        "retirados": df_retirados,
        "sim": df_sim,
    }


def extract_multi_ius(df):
    if not (
        "NOMBRES_APELLIDOS" in df.columns
        and "RADICADO IUS" in df.columns
    ):
        return pd.DataFrame()

    ius_por_nombre = (
        df.groupby("NOMBRES_APELLIDOS")["RADICADO IUS"]
        .nunique()
    )

    nombres_con_varios_ius = ius_por_nombre[
        ius_por_nombre > 1
    ].index

    df_multi_ius = df[
        df["NOMBRES_APELLIDOS"].isin(nombres_con_varios_ius)
    ].copy()

    if not df_multi_ius.empty:
        df_multi_ius = df_multi_ius.sort_values(
            by=["NOMBRES_APELLIDOS", "RADICADO IUS"]
        )

    print(
        f" -> Registros de Personas con múltiples IUS: "
        f"{len(df_multi_ius)}"
    )

    return df_multi_ius
