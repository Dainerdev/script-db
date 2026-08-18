from src.reading import *
from src.diagnostic import *
from src.exportation import *

def main():
    """
    Main function to execute the diagnostic process
    """
    
    # CONFIGURATION      
    # Excel base file
    FILE_EXCEL = "data/original/probando.xlsx"
    
    # Diagnostic results file
    FILE_DIAGNOSTIC = "data/processed/diagnostic_results.xlsx"
    
    
    # IMPLEMENTATION    
    # Read the Excel file
    df = read_excel_file(FILE_EXCEL)  
    
    # Get general information about the Excel file
    excel_general_information(df)
    
    # Standardize columns    
    # in the "Nombres" column of the DataFrame
    df["Nombres"] = standarize_column_names(df["Nombres"])
    
    # in the "Fecha" column of the DataFrame
    df["Fecha"] = standarize_column_dates(df["Fecha"])

    # Save the modified DataFrame to a new Excel file
    export_excel(df, FILE_DIAGNOSTIC)
    
if __name__ == "__main__":
    main()