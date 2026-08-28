import pandas as pd

# Read excel file
def read_excel_file(file_path, sheet_name = "Reparto"):
    """
    Function to read an Excel file into a DataFrame
    """
    
    try:
        # Read the Excel file into a DataFrame
        df = pd.read_excel(file_path, sheet_name = sheet_name, engine="openpyxl")
        return df
    
    except FileNotFoundError:
        print(f"Error: File not found - {file_path}")
        return None
    
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return None

# Get general information about an Excel file
def excel_general_information(df, sheet_name = "Reparto"):
    """
    Function to get information about an Excel file
    """
    
    if df is not None:
        # Display general information about the DataFrame
        rows = len(df)
        columns = len(df.columns)

        print("\nINFORMACIÓN GENERAL - HOJA '{sheet_name}'\n") 

        print(f"Filas: {rows:,}") 
        print(f"Columnas: {columns:,}") 
        print(f"Tamaño: {rows:,} x {columns:,}")