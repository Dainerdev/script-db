from src.reading import *
from src.standardization import *
from src.exportation import *
from src.diagnostic import *

def main():
    """
    Main function to execute the diagnostic, cleaning, and separation process.
    """
    # CONFIGURATION
    FILE_EXCEL = "data/original/base_pasantes.xlsx"
    FILE_RESULTS = "data/processed/diagnostic_results.xlsx"

    # ============================================================
    # 1. LECTURA
    # ============================================================
    df = read_excel_file(FILE_EXCEL)
    excel_general_information(df)
    if df is None:
        return

    # ============================================================
    # 2. DIAGNÓSTICO INICIAL (Con los prints originales en consola)
    # ============================================================
    print("\nPROCESANDO ANÁLISIS DETALLADO\n")
    
    result_col = check_columns(df)
    print("\nANÁLISIS DE COLUMNAS\n")
    print(result_col.to_string(index=False))
    
    result_nulls = check_nulls(df)
    print("\nANÁLISIS DE VALORES NULOS\n")
    print(result_nulls.to_string(index=False))
    
    result_uniques = check_unique_values(df)
    print("\nANÁLISIS DE VALORES ÚNICOS\n")
    print(result_uniques.to_string(index=False))

    result_duplicates = check_duplicates(df)
    print("\nANÁLISIS DE FILAS DUPLICADAS\n")
    print(f"Registro total de filas duplicadas: {len(result_duplicates)}\n")
    if not result_duplicates.empty:
        print(result_duplicates.to_string(index=False))
    
    result_text_problems = check_text_problems(df)
    print("\nANÁLISIS DE PROBLEMAS EN TEXTO\n")
    print(result_text_problems.to_string(index=False))
    
    result_length = check_lengths(df)
    print("\nANÁLISIS DE LONGITUD DE TEXTO\n")
    print(result_length.to_string(index=False))

    # ============================================================
    # 3. ESTANDARIZACIÓN Y LIMPIEZA (Sin crear columnas basura)
    # ============================================================
    print("\nPROCESANDO ESTANDARIZACIÓN Y LIMPIEZA...\n")

    # 3.1. Desdoblar comparecientes múltiples
    print(" -> Desdoblando comparecientes múltiples por fila...")
    df = split_multiple_comparecientes(df)
    
    # Eliminar columna auxiliar creada por el desdoblamiento para no ensuciar el Excel
    if "_revisar_multiples" in df.columns:
        df = df.drop(columns=["_revisar_multiples"])

    # 3.2. Espaciado en todas las columnas de texto
    print(" -> Estandarizando espaciado en todas las columnas...")
    for col in df.columns:
        serie = df[col]
        if pd.api.types.is_string_dtype(serie) or serie.dtype == "object":
            df[col] = standardize_column_spacing(df[col])

    # 3.3. Formato de nombres propios (Sobreescribiendo columnas originales)
    print(" -> Aplicando formato a Nombres, Magistrados y Funcionario a cargo...")
    if "NOMBRES_APELLIDOS" in df.columns:
        df["NOMBRES_APELLIDOS"] = standardize_column_names(df["NOMBRES_APELLIDOS"])
    if "MAGISTRADO" in df.columns:
        df["MAGISTRADO"] = standardize_column_names(df["MAGISTRADO"])
    if "FUNCIONARIO A CARGO" in df.columns:
        df["FUNCIONARIO A CARGO"] = standardize_column_names(df["FUNCIONARIO A CARGO"])

    # 3.4. Formato de Fechas
    print(" -> Estandarizando formato de Fechas y Reparto...")
    if "FECHA" in df.columns:
        df["FECHA"] = standardize_column_dates(df["FECHA"])
    
    if "REPARTO" in df.columns:
        fecha_reparto, _ = standardize_reparto_column(df["REPARTO"])
        df["REPARTO"] = fecha_reparto  # Guardamos solo la fecha correcta

    # ============================================================
    # 4. ANÁLISIS AVANZADO (Solo reporte en consola, sin alterar Excel)
    # ============================================================
    print("\nEJECUTANDO ANÁLISIS DE DUPLICADOS Y SIMILITUD (Reporte)\n")
    
    # IUS
    if "RADICADO IUS" in df.columns and "No" in df.columns:
        ius_por_registro = df.groupby("RADICADO IUS")["No"].nunique()
        ius_duplicados = ius_por_registro[ius_por_registro > 1]
        print(f"[*] Alerta: Se encontraron {len(ius_duplicados)} radicados IUS duplicados.")

    # Nombres por Cedula
    if "IDENTIFICACIÓN" in df.columns and "NOMBRES_APELLIDOS" in df.columns:
        nombres_por_cedula = check_duplicate_names_by_id(df, id_col="IDENTIFICACIÓN", name_col="NOMBRES_APELLIDOS")
        print(f"[*] Alerta: Se encontraron {len(nombres_por_cedula)} cédulas con múltiples variantes de nombre.")

    # Fuzzy Matching
    if "NOMBRES_APELLIDOS" in df.columns:
        nombres_fuzzy, _ = check_fuzzy_duplicate_names(df["NOMBRES_APELLIDOS"])
        print(f"[*] Alerta: Se encontraron {len(nombres_fuzzy)} posibles nombres duplicados por similitud (Fuzzy matching).")

    # ============================================================
    # 5. FILTRADO Y SEPARACIÓN DE DATOS (Nuevos requerimientos)
    # ============================================================
    print("\nSEPARANDO DATOS: SIM, ARCHIVADOS Y RETIRADOS...\n")
    
    clasificacion = df["CLASIFICACIÓN DEL RADICADO"].astype(str).str.upper()
    
    # 5.1. Extraer los SIM
    mask_sim = clasificacion.str.contains("SIM", na=False)
    df_sim = df[mask_sim].copy()
    df_resto = df[~mask_sim].copy()

    # 5.2. Identificar Archivados
    clasificacion_resto = df_resto["CLASIFICACIÓN DEL RADICADO"].astype(str).str.upper()
    mask_archivado = clasificacion_resto.str.contains("ARCHIVADO", na=False)
    
    # 5.3. Separar archivados normales vs funcionarios retirados
    funcionario_cargo = df_resto["FUNCIONARIO A CARGO"].astype(str).str.upper()
    mask_retirados = mask_archivado & funcionario_cargo.str.contains("RETIRADOS", na=False)
    mask_archivados_normales = mask_archivado & ~mask_retirados

    df_retirados = df_resto[mask_retirados].copy()
    df_archivados = df_resto[mask_archivados_normales].copy()
    
    # 5.4. Lo que queda es la base activa limpia
    df_activos = df_resto[~mask_archivado].copy()

    print(f" -> Registros Base Activa (Reparto): {len(df_activos)}")
    print(f" -> Registros SIM: {len(df_sim)}")
    print(f" -> Registros Archivados Normales: {len(df_archivados)}")
    print(f" -> Registros Funcionarios Retirados: {len(df_retirados)}")

    # ============================================================
    # 6. EXPORTACIÓN MÚLTIPLE (Manteniendo formato visual original)
    # ============================================================
    hojas_exportar = {
        "Reparto_Activo": df_activos,
        "Archivados": df_archivados,
        "Funcionarios_Retirados": df_retirados,
        "SIM": df_sim
    }
    
    export_multi_sheet_excel(
        sheets=hojas_exportar, 
        file_path=FILE_RESULTS,
        style_reference_path=FILE_EXCEL,
        style_reference_sheet="Reparto"
    )

if __name__ == "__main__":
    main()