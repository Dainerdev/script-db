import unicodedata
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


# FUNCTIONS

# Function to standarize column names
def standarize_column_names(serie):
    """
    Function to standarize column names
    """    
    
    # Ensure the series is of string type
    serie = serie.astype(str)  
    
    # Remove leading and trailing whitespace
    serie = serie.str.strip()
    
    # Replace spaces with underscores
    serie = serie.str.replace(r"\s+", " ", regex=True)  # Replace multiple spaces with a single space
    
    # Convert to uppercase
    serie = serie.str.upper()
    
    # Normalize unicode characters to ASCII
    serie = serie.map(remove_accents)
    
    return serie

# Remove accents from a string
def remove_accents(s):
    """
    Function to remove accents from a string
    """
    
    # Normalize the string to NFKD form and encode to ASCII, ignoring errors
    return unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode("ASCII")


# IMPLMENTATION

# Standardize column names
df["Nombres"] = standarize_column_names(df["Nombres"])


