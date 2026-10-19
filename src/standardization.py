import unicodedata
import pandas as pd
import re
from datetime import date

from src.text_keys import LINE_SEPARATED_COLUMNS

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


def standardize_column_spacing(serie, keep_line_breaks=False):
    """
    "Aplicar funcion de espaciado en todas las columnas"

    Limpieza SOLO de espacios (recorta inicio/fin, colapsa espacios
    multiples a uno) sin tocar mayusculas ni tildes. A diferencia de
    standardize_column_names, esta si es segura para aplicar a TODAS las
    columnas de texto -incluidas las de texto libre como OBSERVACIONES o
    DATOS RESOLUCION- donde forzar mayusculas no tiene sentido.

    Con keep_line_breaks=True (NOMBRES_APELLIDOS e IDENTIFICACIÓN, spec 002,
    Decisión #9) los saltos de línea se conservan, porque la separación de
    comparecientes cuenta las líneas: cada línea se recorta y se colapsa por
    dentro, "\\r\\n" pasa a "\\n" y se quitan las líneas vacías.
    """
    serie = serie.astype(str)
    if keep_line_breaks:
        serie = serie.str.replace(r"\r\n?", "\n", regex=True)
        serie = serie.str.replace(r"[^\S\n]+", " ", regex=True)
        serie = serie.str.replace(r" ?\n[\n ]*", "\n", regex=True)
        return serie.str.strip()
    serie = serie.str.strip()
    serie = serie.str.replace(r"\s+", " ", regex=True)
    return serie



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
    Etapa de limpieza del pipeline: espaciado en todas las columnas de texto
    y estandarización de fechas (FECHA y REPARTO). Retorna el df limpio.

    Desde la spec 002 ya no separa comparecientes ni da formato a los
    nombres propios: las dos cosas pasan a "Estandarizando parámetros..."
    (src/pipeline.py, Decisiones #9 y #10; el formato viejo convertía la Ñ
    en N). En NOMBRES_APELLIDOS e IDENTIFICACIÓN el espaciado conserva los
    saltos de línea, y las columnas _ORIGINAL (RF-87) no se tocan.
    """
    print("\nPROCESANDO ESTANDARIZACIÓN Y LIMPIEZA...\n")

    print(" -> Estandarizando espaciado en todas las columnas...")
    df = df.copy()
    for col in df.columns:
        serie = df[col]
        if str(col).endswith("_ORIGINAL"):
            continue
        if pd.api.types.is_string_dtype(serie) or serie.dtype == "object":
            df[col] = standardize_column_spacing(serie, keep_line_breaks=col in LINE_SEPARATED_COLUMNS)

    print(" -> Estandarizando formato de Fechas y Reparto...")
    if "FECHA" in df.columns:
        df["FECHA"] = standardize_column_dates(df["FECHA"])
    if "REPARTO" in df.columns:
        fecha_reparto, _ = standardize_reparto_column(df["REPARTO"])
        df["REPARTO"] = fecha_reparto

    return df

def add_radicado_ius_revisada(df, ius_col="RADICADO IUS", new_col="Radicado IUS Revisada"):
    """
    "Radicado IUS Revisada: columna con código únicos por compareciente"

    Crea new_col INMEDIATAMENTE A LA DERECHA de ius_col (no reemplaza el
    original).

    Se asume que el código "más avanzado" es el que realmente le
    pertenece al compareciente. Para celdas con un solo código, se copia
    tal cual (ej. "E-2018-610050" -> "E-2018-610050").

    "Más avanzado" se determina extrayendo todos los números del código
    (ej. "E-2018-615759" -> (2018, 615759)) y comparando esas tuplas
    elemento por elemento (año primero, luego consecutivo) -evita el
    problema de comparar como texto plano, donde "20000" podría ganarle
    a "9999" por ser mas corto en algunos casos.

    Si falta ius_col, retorna df sin modificar (no agrega new_col).
    """
    if ius_col not in df.columns:
        return df.copy()

    def normalizar_espaciado(celda_texto):
        # cierra espacios pegados a un guion: "E-2020 -611813" -> "E-2020-611813"
        return re.sub(r"\s*-\s*", "-", celda_texto)

    def clave_orden(codigo):
        numeros = re.findall(r"\d+", codigo)
        return tuple(int(n) for n in numeros) if numeros else (0,)

    def mas_avanzado(celda):
        if pd.isna(celda):
            return celda
        texto = normalizar_espaciado(str(celda).strip())
        codigos = texto.split() 
        if not codigos:
            return celda
        if len(codigos) == 1:
            return codigos[0]
        return max(codigos, key=clave_orden)

    revisada = df[ius_col].apply(mas_avanzado)

    df = df.copy()
    if new_col in df.columns:
        df = df.drop(columns=[new_col])

    pos = df.columns.get_loc(ius_col) + 1
    df.insert(pos, new_col, revisada)
    return df
