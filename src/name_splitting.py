import re
import pandas as pd

PARTICULAS = ("DE LA", "DE LOS", "DE LAS", "DEL", "DE")  # orden: más larga primero


def _unir_particulas(palabras):
    """
    Revisa desde cada posición si empieza una partícula (probando primero
    las de 2 palabras) y, de ser así, la pega con la(s) palabra(s)
    siguiente(s) como una sola unidad.
    """
    unidades = []
    i = 0
    n = len(palabras)
    while i < n:
        pegado = False
        for particula in PARTICULAS:
            tokens_particula = particula.split()
            k = len(tokens_particula)
            if palabras[i:i + k] == tokens_particula and i + k < n:
                # DE/DEL/DE LA/... + la palabra que sigue (el apellido en sí)
                unidades.append(" ".join(palabras[i:i + k + 1]))
                i += k + 1
                pegado = True
                break
        if not pegado:
            unidades.append(palabras[i])
            i += 1
    return unidades


def _dividir_en_bloques(unidades, tamano_bloque):
    return [unidades[i:i + tamano_bloque] for i in range(0, len(unidades), tamano_bloque)]


def separar_nombre_celda(nombre):
    """
    Intenta separar una celda con varios comparecientes concatenados por
    espacios en una lista de nombres individuales.

    Retorna (lista_de_nombres, necesita_revision: bool).
    Si necesita_revision=True, lista_de_nombres = [nombre] (sin tocar).
    """
    if pd.isna(nombre) or not str(nombre).strip():
        return [nombre], False

    palabras = str(nombre).strip().split()
    unidades = _unir_particulas(palabras)
    total = len(unidades)

    if total <= 4:
        # nombre normal (o corto), no hay nada que separar
        return [nombre], False

    if total % 4 == 0:
        bloques = _dividir_en_bloques(unidades, 4)
    elif total % 3 == 0:
        bloques = _dividir_en_bloques(unidades, 3)
    else:
        return [nombre], True

    return [" ".join(b) for b in bloques], False


def split_names_by_spacing(df, name_col="NOMBRES_APELLIDOS"):
    """
    Aplica separar_nombre_celda() a toda la columna `name_col` del
    DataFrame y desdobla en filas nuevas (duplicando el resto de columnas
    de la fila original, igual que hace split_multiple_comparecientes).
    Agrega '_revisar_multiples_espacio' = True en las filas que no se
    pudieron separar con confianza.

    OJO: a diferencia de split_multiple_comparecientes, aquí no hay una
    columna de IDENTIFICACIÓN paralela con la que emparejar -por eso el
    resultado desdoblado repite la MISMA identificación en todas las
    personas que salieron de una celda. Corre esto ANTES de confiar en
    IDENTIFICACIÓN para esas filas, o mejor, corre primero un vistazo
    manual de cuántas celdas caen en este caso (debería ser una minoría).
    """
    df = df.copy()
    df["_revisar_multiples_espacio"] = False

    filas_nuevas = []
    idx_a_quitar = []

    for idx, valor in df[name_col].items():
        nombres, revisar = separar_nombre_celda(valor)
        
        if revisar:
            df.at[idx, "_revisar_multiples_espacio"] = True
            continue
        
        if len(nombres) == 1:
            continue  # no hay nada que separar, se deja la fila tal cual
        
        idx_a_quitar.append(idx)
        fila_base = df.loc[idx]
        
        for nombre_individual in nombres:
            nueva = fila_base.copy()
            nueva[name_col] = nombre_individual
            filas_nuevas.append(nueva)

    df_resto = df.drop(index=idx_a_quitar)
    df_nuevas = pd.DataFrame(filas_nuevas, columns=df.columns) if filas_nuevas else pd.DataFrame(columns=df.columns)
    return pd.concat([df_resto, df_nuevas], ignore_index=True)
