import pandas as pd

# Read excel file
def read_excel_file(file_path, sheet_name = "Reparto", raise_errors = False):
    """
    Function to read an Excel file into a DataFrame

    OPTIMIZACIÓN: engine="calamine" (python-calamine, motor en Rust) en vez
    de "openpyxl". openpyxl es notoriamente lento leyendo archivos grandes
    (~185k filas); calamine es órdenes de magnitud más rápido para lectura.
    Requiere: pip install python-calamine

    raise_errors=False (default) preserva el comportamiento original:
    imprime el error y retorna None. Con raise_errors=True, además relanza
    la excepción original después de imprimirla, para que un caller (la
    GUI) pueda distinguir la causa exacta del fallo.
    """

    try:
        # Read the Excel file into a DataFrame
        df = pd.read_excel(file_path, sheet_name = sheet_name, engine="calamine")
        return df

    except FileNotFoundError:
        print(f"Error: File not found - {file_path}")
        if raise_errors:
            raise
        return None

    except Exception as e:
        print(f"Error reading Excel file: {e}")
        if raise_errors:
            raise
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