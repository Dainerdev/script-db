from src.reading import *
from src.standardization import *
from src.exportation import *
from src.diagnostic import *

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
    
    df = read_excel_file(FILE_EXCEL)
    excel_general_information(df)
    if df is None:
        return


    # ============================================================
    # 2. DIAGNÓSTICO INICIAL
    # ============================================================
    run_diagnostics(df)


    # ============================================================
    # 3. ESTANDARIZACIÓN Y LIMPIEZA 
    # ============================================================
    df = clean_and_standardize(df)
    

    # ============================================================
    # 4. ANÁLISIS AVANZADO (Reporte)
    # ============================================================
    run_similarity_report(df)

    # ============================================================
    # 5. FILTRADO Y SEPARACIÓN DE DATOS 
    # ============================================================
    grupos = split_by_status(df)
    df_multi_ius = extract_multi_ius(df)

    # ============================================================
    # 6. EXPORTACIÓN 
    # ============================================================
    print("\nEXPORTANDO RESULTADOS A EXCEL (varias hojas)...\n")
    
    hojas_exportar = {
        "Reparto_Activo": grupos["activos"],
        "Archivados": grupos["archivados"],
        "Funcionarios_Retirados": grupos["retirados"],
        "SIM": grupos["sim"],
        "Multiples_IUS": df_multi_ius
    }
    
    export_multi_sheet_excel(
        sheets=hojas_exportar, 
        file_path=FILE_RESULTS,
        style_reference_path=FILE_EXCEL,
        style_reference_sheet="Reparto"
    )

if __name__ == "__main__":
    main()