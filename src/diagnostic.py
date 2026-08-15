import pandas as pd
import numpy as np
import re


# CONFIGURATION

# Excel base file
ARCHIVE_EXCEL = "archive/probando.xlsx"

# Diagnostic results file
ARCHIVE_DIAGNOSTIC = "archive/diagnostic_results.xlsx"


# READ EXCEL FILES

try:
    # Read the Excel file into a DataFrame
    df = pd.read_excel(ARCHIVE_EXCEL, engine="openpyxl")

    # Display the first few rows of the DataFrame
    print("DataFrame loaded successfully:\n")
    print(df.head(n=5))  # Display the first 5 rows
    
except FileNotFoundError:
    print(f"Error: File not found - {ARCHIVE_EXCEL}")
    
except Exception as e:
    print(f"Error reading Excel file: {e}")
    exit()

# GENERAL INFORMATION

rows = len(df)
columns = len(df.columns)

print("\nINFORMACIÓN GENERAL\n") 

print(f"Filas: {rows:,}") 
print(f"Columnas: {columns:,}") 
print(f"Tamaño: {rows:,} x {columns:,}")


