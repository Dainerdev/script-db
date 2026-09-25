from src.reading import *
from src.standardization import *
from src.exportation import *
from src.diagnostic import *
from src.parameters import *
from src.name_splitting import *

def main():
    """
    Realiza el proceso completo: lectura -> diagnóstico -> limpieza ->
    reporte de similitud -> separación por estado -> exportación.
    """
    # CONFIGURATION
    FILE_EXCEL = "data/original/base_pasantes.xlsx"
    FILE_RESULTS = "data/processed/diagnostic_results.xlsx"

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
        
    run_diagnostics(df)

    # ========================================================
    # 3. IDENTIFICACIÓN DE PARÁMETROS
    # ========================================================

    print("\n==============================")
    print("3. IDENTIFICACIÓN DE PARÁMETROS")
    print("==============================")

    resultados_parametros = {}
    resultados_similitudes = {}

    if "TIPO DE EXPEDIENTE" in df.columns:

        print("\n -> Analizando TIPO DE EXPEDIENTE...")

        resultados_parametros["Tipo_Expediente"] = (
            comparar_con_parametros(
                df,
                "TIPO DE EXPEDIENTE",
                PARAMETROS_TIPO_EXPEDIENTE,
                threshold=90,
            )
        )

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

        print(
            f"\n -> Buscando variantes en {columna}..."
        )

        resultados_similitudes[columna] = (
            crear_tabla_similitudes(
                df,
                columna,
                threshold=90,
            )
        )
    
    if "NOMBRES_APELLIDOS" in df.columns:

        print("\n -> Buscando variantes en NOMBRES_APELLIDOS...")

        resultados_similitudes["NOMBRES_APELLIDOS"] = (
            crear_tabla_similitudes(
                df,
                "NOMBRES_APELLIDOS",
                threshold=92,
                forzar_revision=True,
                block_size=4,
            )
        )

    # ============================================================
    # 4. LIMPIEZA Y ESTANDARIZACIÓN
    # ============================================================
    print("\n==============================")
    print("4. ESTANDARIZACIÓN")
    print("==============================")

    df = clean_and_standardize(df)
    
    #df = split_multiple_comparecientes(df)
    
    print("\n -> Separando nombres concatenados por espacios...")
    df = split_names_by_spacing(
        df,
        name_col="NOMBRES_APELLIDOS"
    )
    df_revision_nombres = df[
        df["_revisar_multiples_espacio"] == True
    ].copy()

    # ============================================================
    # 4. ANÁLISIS AVANZADO
    # ============================================================
    
    print("\n==============================")
    print("5. ANÁLISIS AVANZADO")
    print("==============================")

    run_similarity_report(df)


    # ============================================================
    # 5. FILTRADO Y SEPARACIÓN DE DATOS 
    # ============================================================
    grupos = split_by_status(df)
    df_multi_ius = extract_multi_ius(df)
    
    # 5.1. Radicado IUS Revisada (solo en Reparto_Activo)
    print("\nGENERANDO 'Radicado IUS Revisada' en Reparto_Activo...\n")
    grupos["activos"] = add_radicado_ius_revisada(grupos["activos"])
    grupos["archivados"] = add_radicado_ius_revisada(grupos["archivados"])
    grupos["retirados"] = add_radicado_ius_revisada(grupos["retirados"])
    grupos["sim"] = add_radicado_ius_revisada(grupos["sim"])
    df_multi_ius = add_radicado_ius_revisada(df_multi_ius)


    # ============================================================
    # 6. EXPORTACIÓN 
    # ============================================================
    
    print("\n==============================")
    print("6. EXPORTACIÓN")
    print("==============================")
    
    hojas_exportar = {
        "Reparto_Activo": grupos["activos"],
        "Archivados": grupos["archivados"],
        "Funcionarios_Retirados": grupos["retirados"],
        "SIM": grupos["sim"],
        "Multiples_IUS": df_multi_ius,
        "Revision_Nombres": df_revision_nombres,
        "Tipo_Expediente": resultados_parametros.get(
            "Tipo_Expediente",
            pd.DataFrame(),
        ),
    }
    
    for columna, resultado in resultados_similitudes.items():

        if resultado.empty:
            continue

        nombre_hoja = f"Sim_{columna[:20]}"
        hojas_exportar[nombre_hoja] = resultado
    
    export_multi_sheet_excel(
        sheets = hojas_exportar, 
        file_path = FILE_RESULTS,
    )

if __name__ == "__main__":
    main()