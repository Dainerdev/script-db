import pandas as pd
from src.reading import *
from src.standardization import *
from src.exportation import *
from src.diagnostic import *
from src.parameters import *
from src.name_splitting import split_names_by_spacing


def main():
    """
    Orden del pipeline: lectura -> diagnóstico -> ESTANDARIZACIÓN Y
    LIMPIEZA (mayúsculas/sin tilde/espaciado en TODAS las columnas) ->
    SEPARAR REGISTROS (comparecientes múltiples) -> SIMILITUDES ->
    GENERAR PARÁMETROS -> análisis avanzado -> separación por estado ->
    exportación.
 
    Se limpia ANTES de calcular similitudes a propósito: así "Físico" /
    "FISICO" / "físico" llegan a crear_tabla_similitudes/
    comparar_con_parametros como el MISMO texto exacto (no dependen de
    que el fuzzy matching las reconozca como iguales -eso se reserva
    para variantes reales de ortografía, como "FISICO"/"FICICO").
    """
    # CONFIGURATION
    FILE_EXCEL = "data/original/base_pasantes.xlsx"
    FILE_RESULTS = "data/processed/diagnostic_results.xlsx"
 
    hojas_exportar = {}
 
    # ============================================================
    # 1. LECTURA
    # ============================================================
 
    print("\n==============================")
    print("1. LECTURA")
    print("==============================")
 
    df = read_excel_file(FILE_EXCEL)
 
    if df is None:
        return
 
    excel_general_information(df)
 
    # ============================================================
    # 2. DIAGNÓSTICO INICIAL
    # ============================================================
 
    print("\n==============================")
    print("2. DIAGNÓSTICO INICIAL")
    print("==============================")
 
    columnas_diag, nulos_diag, unicos_diag, texto_diag, longitud_diag = run_diagnostics(df)
    hojas_exportar["Diagnostico_General"] = columnas_diag
    hojas_exportar["Diagnostico_Textos"] = texto_diag
 
    # ============================================================
    # 3. ESTANDARIZACIÓN Y LIMPIEZA
    # ============================================================
 
    print("\n==============================")
    print("3. ESTANDARIZACIÓN Y LIMPIEZA")
    print("==============================")
 
    col_tipo = encontrar_columna(df, "TIPO DE EXPEDIENTE")
    extra = [col_tipo] if col_tipo else []
 
    df = clean_and_standardize(df, ya_desdoblado=True, columnas_extra_mayuscula=extra)
 
    # ============================================================
    # 4. SEPARAR REGISTROS
    # ============================================================
 
    print("\n==============================")
    print("4. SEPARAR REGISTROS")
    print("==============================")
 
    if "NOMBRES_APELLIDOS" in df.columns and "IDENTIFICACIÓN" in df.columns:
        print(" -> Desdoblando comparecientes múltiples por fila (salto de línea)...")
        antes = len(df)
        df = split_multiple_comparecientes(df, name_col="NOMBRES_APELLIDOS")
        if "_revisar_multiples" in df.columns:
            print(f"    Filas: {antes} -> {len(df)} "
                  f"({int(df['_revisar_multiples'].sum())} quedaron para revisión manual)")
            df = df.drop(columns=["_revisar_multiples"])
 
    if "NOMBRES_APELLIDOS" in df.columns:
        print(" -> Separando nombres concatenados por espacio...")
        antes = len(df)
        df = split_names_by_spacing(df, name_col="NOMBRES_APELLIDOS")
        n_revisar_espacio = int(df.get("_revisar_multiples_espacio", pd.Series(dtype=bool)).sum())
        print(f"    Filas: {antes} -> {len(df)} "
              f"({n_revisar_espacio} quedaron para revisión manual)")
 
    # ============================================================
    # 5. SIMILITUDES Y PARÁMETROS
    # ============================================================
 
    print("\n==============================")
    print("5. SIMILITUDES Y PARÁMETROS")
    print("==============================")
 
    resultados_parametros = {}
    resultados_similitudes = {}
    listados_parametros = {}
 
    if col_tipo:
        print(f"\n -> Analizando {col_tipo}...")
 
        resultados_parametros["Tipo_Expediente"] = comparar_con_parametros(
            df,
            col_tipo,
            PARAMETROS_TIPO_EXPEDIENTE,
            threshold=90,
        )

        # Primero se genera el listado usando los valores originales
        listados_parametros["TIPO_EXPEDIENTE"] = generar_listado_parametros(
            df,
            col_tipo,
            valores_fijos=PARAMETROS_TIPO_EXPEDIENTE,
            threshold=90,
        )

        # Después se aplican las correcciones al DataFrame
        df = aplicar_correcciones_automaticas(
            df,
            col_tipo,
            resultados_parametros["Tipo_Expediente"],
        )
    else:
        print("\n[!] No se encontró ninguna columna que empiece con 'TIPO DE EXPEDIENTE'")
 
    columnas_descubrir = [
        "SALA",
        "SOLICITUD",
        "DECISIÓN",
        "PERTENECE",
        "MAGISTRADO",
        "DELEGADA",
        "FUNCIONARIO A CARGO",
    ]
 
    for columna in columnas_descubrir:
 
        if columna not in df.columns:
            continue
 
        print(f"\n -> Buscando variantes en {columna}...")
 
        resultados_similitudes[columna] = crear_tabla_similitudes(
            df, columna, threshold=90,
        )
        df = aplicar_correcciones_automaticas(df, columna, resultados_similitudes[columna])
        listados_parametros[columna] = generar_listado_parametros(
            df, columna, threshold=90,
        )

    if "NOMBRES_APELLIDOS" in df.columns:
 
        print("\n -> Buscando variantes en NOMBRES_APELLIDOS...")
 
        resultados_similitudes["NOMBRES_APELLIDOS"] = crear_tabla_similitudes(
            df, "NOMBRES_APELLIDOS", threshold=92,
            forzar_revision=True, block_size=4,
        )
        listados_parametros["NOMBRES_APELLIDOS"] = generar_listado_parametros(
            df, "NOMBRES_APELLIDOS", threshold=92,
            forzar_revision=True, block_size=4,
        )
 
    # ============================================================
    # 6. ANÁLISIS AVANZADO
    # ============================================================
 
    print("\n==============================")
    print("6. ANÁLISIS AVANZADO")
    print("==============================")
 
    run_similarity_report(df)
 
    # ============================================================
    # 7. FILTRADO Y SEPARACIÓN DE DATOS
    # ============================================================
 
    print("\n==============================")
    print("7. FILTRADO Y SEPARACIÓN DE DATOS")
    print("==============================")
 
    grupos = split_by_status(df)
    df_multi_ius = extract_multi_ius(df)
 
    print("\nGENERANDO 'Radicado IUS Revisada' en cada grupo...\n")
    grupos["activos"] = add_radicado_ius_revisada(grupos["activos"])
    grupos["archivados"] = add_radicado_ius_revisada(grupos["archivados"])
    grupos["retirados"] = add_radicado_ius_revisada(grupos["retirados"])
    grupos["sim"] = add_radicado_ius_revisada(grupos["sim"])
    df_multi_ius = add_radicado_ius_revisada(df_multi_ius)
 
    # ============================================================
    # 8. EXPORTACIÓN
    # ============================================================
 
    print("\n==============================")
    print("8. EXPORTACIÓN")
    print("==============================")
 
    hojas_exportar.update({
        "Reparto_Activo": grupos["activos"],
        "Archivados": grupos["archivados"],
        "Funcionarios_Retirados": grupos["retirados"],
        "SIM": grupos["sim"],
        "Multiples_IUS": df_multi_ius,
    })
 
    if "Tipo_Expediente" in resultados_parametros:
        hojas_exportar["Sim_Tipo_Expediente"] = resultados_parametros["Tipo_Expediente"]
 
    for columna, resultado in resultados_similitudes.items():
        if resultado.empty:
            continue
        hojas_exportar[f"Sim_{columna[:20]}"] = resultado
 
    for columna, listado in listados_parametros.items():
        if listado.empty:
            continue
        hojas_exportar[f"Parametros_{columna[:18]}"] = listado
 
    export_multi_sheet_excel(
        sheets=hojas_exportar,
        file_path=FILE_RESULTS,
    )


if __name__ == "__main__":
    main()