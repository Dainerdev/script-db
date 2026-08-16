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
def read_excel_file(file_path):
    """
    Function to read an Excel file into a DataFrame
    """
    
    try:
        # Read the Excel file into a DataFrame
        df = pd.read_excel(file_path, engine="openpyxl")
        return df
    
    except FileNotFoundError:
        print(f"Error: File not found - {file_path}")
        return None
    
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return None


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

# Function to standarize column dates
def standarize_column_dates(serie):
    """
    Function to standarize column dates
    """
    
    # Convert the series to datetime, coercing errors and assuming day-first format
    dates = pd.to_datetime(serie, errors="coerce", dayfirst=True)
    
    return dates.dt.strftime("%d-%m-%Y")


