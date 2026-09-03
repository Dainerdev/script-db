import pandas as pd
import difflib
from collections import defaultdict

# ======================================================================================================
# Función principal: Recorre todas las funciones de diagnostico y analisis de duplicados
# ======================================================================================================

def run_similarity_report(df):
    """
    Corre las alertas de duplicados/similitud (IUS, cédulas con variantes
    de nombre, fuzzy matching) y las imprime. Solo reporte, no modifica df.
    """
    print("\nEJECUTANDO ANÁLISIS DE DUPLICADOS Y SIMILITUD (Reporte)\n")

    if "RADICADO IUS" in df.columns and "No" in df.columns:
        ius_por_registro = df.groupby("RADICADO IUS")["No"].nunique()
        ius_duplicados = ius_por_registro[ius_por_registro > 1]
        print(f"[*] Alerta: Se encontraron {len(ius_duplicados)} radicados IUS duplicados.")

    if "IDENTIFICACIÓN" in df.columns and "NOMBRES_APELLIDOS" in df.columns:
        nombres_por_cedula = check_duplicate_names_by_id(df, id_col="IDENTIFICACIÓN", name_col="NOMBRES_APELLIDOS")
        print(f"[*] Alerta: Se encontraron {len(nombres_por_cedula)} cédulas con múltiples variantes de nombre.")

    if "NOMBRES_APELLIDOS" in df.columns:
        nombres_fuzzy, _ = check_fuzzy_duplicate_names(df["NOMBRES_APELLIDOS"])
        print(f"[*] Alerta: Se encontraron {len(nombres_fuzzy)} posibles nombres duplicados por similitud (Fuzzy matching).")


# ===================================================
# Funciones de diagnostico y analisis de duplicados
# ===================================================

def run_diagnostics(df):
    """
    Reemplaza check_columns + check_nulls + check_unique_values +
    check_text_problems + check_lengths.

    OPTIMIZACIÓN: las 5 funciones originales recorrían df.columns por
    separado, recalculando lo mismo varias veces (isnull().sum() en 2
    funciones, nunique() en 2 funciones, dropna().astype(str) en 2
    funciones). nunique() en particular es caro en un dataset grande y se
    pagaba dos veces. Aquí se hace UN solo recorrido de columnas y cada
    cálculo se reutiliza para las tablas que lo necesiten.

    Retorna las mismas 5 tablas que antes, en el mismo orden:
    (result_col, result_nulls, result_uniques, result_text_problems, result_length)
    """
    total = len(df)
    filas_columns, filas_nulls, filas_unique = [], [], []
    filas_text, filas_length = [], []

    for column in df.columns:
        serie = df[column]
        nulls = serie.isnull().sum()
        unique = serie.nunique(dropna=True)
        pct_nulls = round((nulls / total) * 100, 2) if total > 0 else 0

        filas_columns.append({
            "Columna": column,
            "Tipo": str(serie.dtype),
            "Total": total,
            "Nulos": nulls,
            "Porcentaje Nulos": pct_nulls,
            "Unicos": unique,
            "Duplicados": total - unique - nulls
        })

        filas_nulls.append({
            "Columna": column,
            "Total": total,
            "Nulos": nulls,
            "Porcentaje Nulos": pct_nulls
        })

        filas_unique.append({
            "Columna": column,
            "Total": total,
            "Unicos": unique,
            "Porcentaje Unicos": round((unique / total) * 100, 2) if total > 0 else 0
        })

        es_texto = pd.api.types.is_string_dtype(serie) or serie.dtype == "object"
        if es_texto:
            # dropna().astype(str) se hace UNA sola vez y se reutiliza
            # para problemas de texto Y longitudes (antes se hacía 2 veces)
            data = serie.dropna().astype(str)

            filas_text.append({
                "Columna": column,
                "Total": total,
                "Espacios Iniciales": data.str.match(r"^\s+").sum(),
                "Espacios Finales": data.str.match(r".*\s+$").sum(),
                "Múltiples Espacios": data.str.contains(r"\s{2,}", regex=True).sum()
            })

            filas_length.append({
                "Columna": column,
                "Total": total,
                "Longitud Mínima": data.str.len().min(),
                "Longitud Máxima": data.str.len().max(),
                "Longitud Promedio": round(data.str.len().mean(), 2)
            })

    return (
        pd.DataFrame(filas_columns),
        pd.DataFrame(filas_nulls),
        pd.DataFrame(filas_unique),
        pd.DataFrame(filas_text),
        pd.DataFrame(filas_length),
    )


def check_duplicates(df, subset=None):
    """
    Check for duplicate rows in the DataFrame and return a summary.

    FIX (respecto a la version original): antes comparaba las 23 columnas
    completas, lo que con texto libre (OBSERVACIONES, DATOS RESOLUCION) casi
    nunca coincide caracter por caracter y da 0 duplicados aunque existan.
    Ahora acepta `subset` para comparar solo columnas clave. Si no se pasa
    subset, se comporta igual que antes (fila completa).
    """
    mask = df.duplicated(subset=subset, keep=False)
    duplicate_rows = df[mask].copy()
    duplicate_rows.insert(0, "Fila Duplicada", duplicate_rows.index + 2)
    return duplicate_rows


def check_duplicate_names_by_id(df, id_col="IDENTIFICACIÓN", name_col="NOMBRES_APELLIDOS_COMPARECIENTE"):
    """
    "Usar un filtro con identificaciones para comparar duplicados de nombres unicos"

    Agrupa por cedula (IDENTIFICACION) -ya que es un dato mas estable que el
    nombre- y detecta cedulas que aparecen escritas con mas de una variante
    de nombre. Pensada para correr DESPUES de standarize_column_spacing /
    standarize_column_names y despues de split_multiple_comparecientes,
    porque antes de eso una misma celda puede traer varios comparecientes
    empaquetados y el agrupamiento no tiene sentido.
    """
    temp = df[[id_col, name_col]].dropna().copy()
    temp[id_col] = temp[id_col].astype(str).str.strip()
    temp[name_col] = temp[name_col].astype(str).str.strip()

    # IMPORTANTE: IDENTIFICACION trae placeholders de texto en vez de cedula
    # real cuando no se conoce (ej. "Caso 003", "M.C."), usados por igual
    # para cientos de personas DISTINTAS. Agruparlos como si fueran una sola
    # identidad genera listas de miles de nombres sin relacion real entre
    # si (y celdas de Excel que exceden el limite de 32.767 caracteres).
    # Se descartan del analisis los valores que no son mayormente numericos.
    es_cedula_real = temp[id_col].str.match(r"^\d{5,15}$")
    excluidos = temp.loc[~es_cedula_real, id_col].nunique()
    if excluidos:
        print(f"  (check_duplicate_names_by_id: se excluyeron {excluidos} valores de "
              f"IDENTIFICACIÓN que no son cédula numérica real, ej. 'Caso 003' -no se "
              f"agrupan como si fueran una sola persona)")
    temp = temp[es_cedula_real]

    grouped = temp.groupby(id_col)[name_col].agg(lambda x: sorted(set(x)))
    inconsistentes = grouped[grouped.apply(len) > 1]

    result = pd.DataFrame({
        "IDENTIFICACION": inconsistentes.index,
        "Variantes_Nombre": inconsistentes.values,
        "N_Variantes": inconsistentes.apply(len)
    })
    return result.sort_values("N_Variantes", ascending=False).reset_index(drop=True)


def check_fuzzy_duplicate_names(names, threshold=0.90, block_size=8, max_block_size=300):
    """
    "Usar un fuzzy para comparar los posibles nombres repetidos"

    Compara nombres YA estandarizados (mayusculas, sin tildes, espacios
    limpios) usando difflib (libreria estandar, sin dependencias nuevas).
    Para que sea viable sobre un dataset de ~40 mil nombres unicos (que en
    O(n^2) puro serian ~800 millones de comparaciones):

    1. Agrupa por un bloque de las primeras `block_size` letras y solo
       compara dentro de cada bloque.
    2. Antes de llamar a difflib, descarta pares cuya diferencia de longitud
       ya haga imposible alcanzar el `threshold` (filtro barato, no cambia
       el resultado, solo evita trabajo innecesario).
    3. Los bloques con mas de `max_block_size` nombres (tipicamente
       prefijos muy comunes, ej. "MARIA " o "JUAN C") se SALTAN por costo y
       se reportan aparte -no se comparan en silencio-, porque incluso
       bloqueado, un bloque de miles de nombres puede tardar minutos.

    Limitacion conocida: no detecta variantes donde cambia el ORDEN de
    nombre/apellido (ej. "GARCIA PEREZ JUAN" vs "JUAN GARCIA PEREZ"), porque
    el bloqueo es por prefijo, no por conjunto de palabras. Para un analisis
    exhaustivo (todos los pares, sin bloqueo ni tope) o para tokenizar por
    palabra, la alternativa recomendada es instalar 'rapidfuzz' -mismo
    resultado conceptual, pero implementado en C y ordenes de magnitud mas
    rapido que difflib a esta escala.

    Retorna (DataFrame de pares posibles, lista de bloques omitidos por tamaño).
    """
    unique_names = pd.Series(names).dropna().unique()
    blocks = defaultdict(list)
    for n in unique_names:
        blocks[n[:block_size]].append(n)

    omitidos = []
    posibles = []
    for prefijo, candidatos in blocks.items():
        if len(candidatos) < 2:
            continue
        if len(candidatos) > max_block_size:
            omitidos.append({"Prefijo": prefijo, "N_Nombres": len(candidatos)})
            continue
        for i in range(len(candidatos)):
            a = candidatos[i]
            for j in range(i + 1, len(candidatos)):
                b = candidatos[j]
                # filtro barato: si la diferencia de longitud ya hace
                # imposible llegar al threshold, ni se llama a difflib
                longest = max(len(a), len(b))
                if longest == 0 or (1 - abs(len(a) - len(b)) / longest) < threshold:
                    continue
                score = difflib.SequenceMatcher(None, a, b).ratio()
                if score >= threshold:
                    posibles.append({"Nombre_A": a, "Nombre_B": b, "Similitud": round(score, 3)})

    cols = ["Nombre_A", "Nombre_B", "Similitud"]
    df_posibles = pd.DataFrame(posibles, columns=cols) if posibles else pd.DataFrame(columns=cols)
    df_posibles = df_posibles.sort_values("Similitud", ascending=False).reset_index(drop=True)

    omit_cols = ["Prefijo", "N_Nombres"]
    df_omitidos = pd.DataFrame(omitidos, columns=omit_cols) if omitidos else pd.DataFrame(columns=omit_cols)

    return df_posibles, df_omitidos

# ============================================================
# Separación de datos por estado (Activos/Archivados/Retirados/SIM)
# y extracción de casos especiales
# ============================================================

def split_by_status(df):
    """
    Separa el DataFrame en Activos / Archivados / Funcionarios Retirados,
    y genera una COPIA (no extracción) de los registros SIM tomada desde
    la base activa -los SIM permanecen en Activos, no se mueven.

    Retorna un dict: {"activos", "archivados", "retirados", "sim"}
    """
    print("\nSEPARANDO DATOS: ARCHIVADOS Y RETIRADOS...\n")

    clasificacion = df["CLASIFICACIÓN DEL RADICADO"].astype(str).str.upper()
    funcionario_cargo = df["FUNCIONARIO A CARGO"].astype(str).str.upper()

    mask_archivado = clasificacion.str.contains("ARCHIVADO", na=False)
    mask_retirados = mask_archivado & funcionario_cargo.str.contains("RETIRADOS", na=False)
    mask_archivados_normales = mask_archivado & ~mask_retirados

    df_retirados = df.loc[mask_retirados].copy()
    df_archivados = df.loc[mask_archivados_normales].copy()
    df_activos = df.loc[~mask_archivado].copy()

    print("\nGENERANDO COPIA DE REGISTROS SIM (desde la base activa)...\n")
    clasificacion_activos = df_activos["CLASIFICACIÓN DEL RADICADO"].astype(str).str.upper()
    mask_sim = clasificacion_activos.str.contains("SIM", na=False)
    df_sim = df_activos.loc[mask_sim].copy()

    print(f" -> Registros Base Activa (Reparto): {len(df_activos)}")
    print(f" -> Registros SIM: {len(df_sim)}")
    print(f" -> Registros Archivados Normales: {len(df_archivados)}")
    print(f" -> Registros Funcionarios Retirados: {len(df_retirados)}")

    return {"activos": df_activos, "archivados": df_archivados, "retirados": df_retirados, "sim": df_sim}


def extract_multi_ius(df):
    """
    Extrae las filas de personas (por NOMBRES_APELLIDOS) que tienen más de
    un RADICADO IUS distinto, ordenadas por nombre y luego por IUS.
    """
    print("\nEXTRAYENDO CASOS: MISMO NOMBRE CON DISTINTO IUS...\n")

    if not ("NOMBRES_APELLIDOS" in df.columns and "RADICADO IUS" in df.columns):
        return pd.DataFrame()

    ius_por_nombre = df.groupby("NOMBRES_APELLIDOS")["RADICADO IUS"].nunique()
    nombres_con_varios_ius = ius_por_nombre[ius_por_nombre > 1].index
    df_multi_ius = df[df["NOMBRES_APELLIDOS"].isin(nombres_con_varios_ius)].copy()

    if not df_multi_ius.empty:
        df_multi_ius = df_multi_ius.sort_values(by=["NOMBRES_APELLIDOS", "RADICADO IUS"])

    print(f" -> Registros de Personas con múltiples IUS: {len(df_multi_ius)}")
    return df_multi_ius
