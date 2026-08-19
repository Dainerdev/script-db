from src.reading import *
from src.cleaning import *
from src.exportation import *
from src.diagnostic import *

def main():
    """
    Main function to execute the diagnostic process
    """
    
    # CONFIGURATION      
    # Excel base file
    FILE_EXCEL = "data/original/base_pasantes.xlsx"
    
    # Diagnostic results file
    FILE_DIAGNOSTIC = "data/processed/diagnostic_results.xlsx"
    
    
    # IMPLEMENTATION    
    # Read the Excel file
    df = read_excel_file(FILE_EXCEL)  
    
    # Get general information about the Excel file
    excel_general_information(df)
    
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
    print(result_duplicates.to_string(index=False))
    
    result_text_problems = check_text_problems(df)
    print("\nANÁLISIS DE PROBLEMAS EN TEXTO\n")
    print(result_text_problems.to_string(index=False))
    
    result_length = check_lengths(df)
    print("\nANÁLISIS DE LONGITUD DE TEXTO\n")
    print(result_length.to_string(index=False))

    # Standardize columns    
    # in the "Nombres" column of the DataFrame
    #df["Nombres"] = standarize_column_names(df["NOMBRES_APELLIDOS_COMPARECIENTE"])
    
    # in the "Fecha" column of the DataFrame
    #df["FECHA"] = standarize_column_dates(df["FECHA"])

    # Save the modified DataFrame to a new Excel file
    #export_excel(df, FILE_DIAGNOSTIC)
    
if __name__ == "__main__":
    main()