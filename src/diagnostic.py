import unicodedata
import pandas as pd

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
    
    # Ensure the series is of string type and remove leading/trailing whitespace 
    serie = serie.astype(str).str.strip()
    
    dates = pd.to_datetime(serie, errors="coerce", dayfirst=True, format="mixed")
    
    # Normalize to remove time component
    return dates.dt.normalize()


