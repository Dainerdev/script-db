import unicodedata
from datetime import date
import pandas as pd

# =================================================================
# Funciones de estandarización y limpieza de columnas
# =================================================================

def standardize_column_names(serie):
    """
    Function to standardize column names (mayusculas + sin tildes + espacios).
    Verificado: en pandas 3.x .astype(str) preserva los nulos reales (no los
    convierte al string "nan"), asi que esta funcion es segura tal cual
    estaba. Pensada para columnas de NOMBRE PROPIO: comparecientes,
    magistrado, funcionario a cargo.
    """
    serie = standardize_column_spacing(serie)
    serie = serie.str.upper()
    serie = serie.map(remove_accents)
    return serie


def remove_accents(s):
    """
    Function to remove accents from a string
    """
    if pd.isna(s):
        return s
    s = str(s)
    return unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode("ASCII")


def standardize_column_dates(serie):
    """
    Function to standardize column dates
    """
    serie = serie.astype(str).str.strip()
    dates = pd.to_datetime(serie, errors="coerce", dayfirst=True, format="mixed")
    return dates.dt.date


def standardize_column_spacing(serie):
    """
    "Aplicar funcion de espaciado en todas las columnas"

    Limpieza SOLO de espacios (recorta inicio/fin, colapsa espacios
    multiples a uno) sin tocar mayusculas ni tildes. A diferencia de
    standardize_column_names, esta si es segura para aplicar a TODAS las
    columnas de texto -incluidas las de texto libre como OBSERVACIONES o
    DATOS RESOLUCION- donde forzar mayusculas no tiene sentido.
    """
    serie = serie.astype(str)
    serie = serie.str.strip()
    serie = serie.str.replace(r"\s+", " ", regex=True)
    return serie


def split_multiple_comparecientes(df, name_col="NOMBRES_APELLIDOS_COMPARECIENTE", id_col="IDENTIFICACIÓN"):
    """
    "Aplicar un salto de linea a los nombres y comparar las longitudes para
    separar los grupos de nombres"

    Desdobla en varias filas las que empaquetan mas de un compareciente en
    una sola celda (nombre e identificacion separados por saltos de linea EN
    PARALELO). Solo desdobla cuando el numero de segmentos coincide
    EXACTAMENTE entre nombre e identificacion para esa fila (linea 1 de
    nombre <-> linea 1 de cedula, etc). Si no coincide, la fila se deja
    intacta y se marca en la columna nueva '_revisar_multiples' = True para
    revision manual, en vez de adivinar el emparejamiento.

    Nota: pensada para correr ANTES de standardize_column_names /
    standardize_column_spacing sobre estas dos columnas (splitea sobre el
    texto crudo, incluido el \\n).
    """
    df = df.copy()
    nom_split = df[name_col].astype(str).str.split("\n")
    id_split = df[id_col].astype(str).str.split("\n")

    n_nom = nom_split.str.len()
    n_id = id_split.str.len()
    tiene_multiples = (n_nom > 1) | (n_id > 1)
    segmentos_coinciden = n_nom == n_id

    df["_revisar_multiples"] = tiene_multiples & ~segmentos_coinciden

    idx_a_desdoblar = df.index[tiene_multiples & segmentos_coinciden]
    idx_simples = df.index[~(tiene_multiples & segmentos_coinciden)]

    filas_nuevas = []
    for idx in idx_a_desdoblar:
        row = df.loc[idx]
        nombres = [n.strip() for n in row[name_col].split("\n")]
        ids = [i.strip() for i in row[id_col].split("\n")]
        for nombre, ident in zip(nombres, ids):
            nueva = row.copy()
            nueva[name_col] = nombre
            nueva[id_col] = ident
            filas_nuevas.append(nueva)

    df_simples = df.loc[idx_simples]
    df_desdobladas = pd.DataFrame(filas_nuevas, columns=df.columns) if filas_nuevas else pd.DataFrame(columns=df.columns)

    resultado = pd.concat([df_simples, df_desdobladas], ignore_index=True)
    return resultado


def standardize_reparto_column(serie, min_year=2017, max_year=None):
    """
    "Aplicar funcion de formato de fecha en col reparto"

    Convierte REPARTO a fecha. A diferencia de un pd.to_datetime() directo,
    valida el resultado antes de aceptarlo: se encontraron 1.208 filas
    (0,86% de las que "parsean bien") que en realidad son basura -
    artefactos de epoch de Excel (ej. datetime(1900, 1, 11), typeados por
    error en una celda con formato de fecha), texto con el año truncado
    (ej. "1/6/223"), o valores que son solo una HORA sin fecha, que
    pd.to_datetime rellena en silencio con la fecha de hoy. Se descartan
    con un rango de año plausible en vez de confiar en que "si parseo, es
    valido".

    Reglas, en orden:
    1. Parsea directo Y el año cae en [min_year, max_year] Y no es una hora
       suelta -> se usa tal cual (categoria "fecha_directa").
    2. Texto "Mes Año" (ej. "Julio 2018") -> día 1 de ese mes/año
       (categoria "periodo_mes_anio").
    3. Rango de días (ej. "1-10 de agosto") -> el texto no trae año, así
       que NO se adivina: queda en NaT, categoria
       "periodo_rango_dias_sin_anio", para resolver a mano (son solo 4
       filas en todo el dataset).
    4. Cualquier otro caso (incluida una fecha con año fuera de rango, o
       una hora suelta) -> NaT, categoria "no_reconocido".

    Retorna (serie_fecha, serie_categoria) para poder auditar cada fila.
    """
    if max_year is None:
        max_year = date.today().year

    s = serie.astype(str).str.strip()
    meses_map = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    }
    meses_pat = "|".join(meses_map.keys())

    parsed_directo = pd.to_datetime(s, errors="coerce", dayfirst=True, format="mixed")
    es_solo_hora = s.str.match(r"^\d{1,2}:\d{2}(:\d{2})?$", na=False)
    directo_valido = parsed_directo.notna() & parsed_directo.dt.year.between(min_year, max_year) & ~es_solo_hora

    mes_anio = s.str.extract(rf"(?i)^({meses_pat})\s+(\d{{4}})$")
    es_mes_anio = mes_anio[0].notna() & ~directo_valido

    rango = s.str.match(rf"(?i)^\d{{1,2}}\s*-\s*\d{{1,2}}\s+(de\s+)?({meses_pat})$", na=False)
    es_rango = rango & ~directo_valido & ~es_mes_anio

    fecha_final = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    categoria = pd.Series("no_reconocido", index=s.index)

    fecha_final.loc[directo_valido] = parsed_directo.loc[directo_valido]
    categoria.loc[directo_valido] = "fecha_directa"

    if es_mes_anio.any():
        meses_num = mes_anio.loc[es_mes_anio, 0].str.lower().map(meses_map)
        anios_num = mes_anio.loc[es_mes_anio, 1].astype(int)
        fecha_final.loc[es_mes_anio] = pd.to_datetime(
            pd.DataFrame({"year": anios_num, "month": meses_num, "day": 1})
        )
        categoria.loc[es_mes_anio] = "periodo_mes_anio"

    categoria.loc[es_rango] = "periodo_rango_dias_sin_anio"
    categoria.loc[s.isin(["nan", "NaT", ""])] = "vacio"

    return fecha_final.dt.date, categoria


def clean_and_standardize(df):
    """
    Etapa 3 del pipeline: desdoblado de comparecientes, espaciado en todas
    las columnas de texto, formato de nombres propios, y estandarización
    de fechas (FECHA y REPARTO). Retorna el df limpio.
    """
    print("\nPROCESANDO ESTANDARIZACIÓN Y LIMPIEZA...\n")

    print(" -> Desdoblando comparecientes múltiples por fila...")
    df = split_multiple_comparecientes(df, name_col="NOMBRES_APELLIDOS")
    if "_revisar_multiples" in df.columns:
        df = df.drop(columns=["_revisar_multiples"])

    print(" -> Estandarizando espaciado en todas las columnas...")
    for col in df.columns:
        serie = df[col]
        if pd.api.types.is_string_dtype(serie) or serie.dtype == "object":
            df[col] = standardize_column_spacing(df[col])

    # OPTIMIZACIÓN: ya no se llama a standardize_column_names (que vuelve a
    # espaciar por dentro); el espaciado ya se aplicó arriba a todas las
    # columnas de texto, incluidas estas 3. Solo falta mayúsculas + tildes.
    print(" -> Aplicando formato a Nombres, Magistrados y Funcionario a cargo...")
    for col in ("NOMBRES_APELLIDOS", "MAGISTRADO", "FUNCIONARIO A CARGO"):
        if col in df.columns:
            df[col] = df[col].str.upper().map(remove_accents)

    print(" -> Estandarizando formato de Fechas y Reparto...")
    if "FECHA" in df.columns:
        df["FECHA"] = standardize_column_dates(df["FECHA"])
    if "REPARTO" in df.columns:
        fecha_reparto, _ = standardize_reparto_column(df["REPARTO"])
        df["REPARTO"] = fecha_reparto

    return df
