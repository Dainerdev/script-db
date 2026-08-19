import pandas as pd

def check_columns(df):
    """
    Check the columns of the DataFrame and return a summary of their characteristics.
    """
    
    result = []
    
    for column in df.columns:
        
        serie = df[column]
        
        total = len(serie)
        nulls = serie.isnull().sum()
        unique = serie.nunique(dropna=True)
        
        result.append({
            "Columna": column,
            "Tipo": str(serie.dtype),
            "Total": total,
            "Nulos": nulls,
            "Porcentaje Nulos": round((nulls / total) * 100, 2),
            "Unicos": unique,
            "Duplicados": total - unique - nulls
        })
    
    return pd.DataFrame(result)
    
def check_nulls(df):
    """
    Check for null values in the DataFrame and return a summary.
    """
    result = []
    
    for column in df.columns:        
        nulls = df[column].isnull().sum()
        total = len(df)
        
        percentage_nulls = (nulls / total) * 100 if total > 0 else 0
        
        result.append({
            "Columna": column,
            "Total": total,
            "Nulos": nulls,
            "Porcentaje Nulos": round(percentage_nulls, 2)
        })
    
    return pd.DataFrame(result)

def check_unique_values(df):
    """
    Check for unique values in the DataFrame and return a summary.
    """
    result = []
    
    for column in df.columns:
        unique_values = df[column].nunique(dropna=True)
        total = len(df)
        
        result.append({
            "Columna": column,
            "Total": total,
            "Unicos": unique_values,
            "Porcentaje Unicos": round((unique_values / total) * 100, 2) if total > 0 else 0
        })
    
    return pd.DataFrame(result)


def check_duplicates(df):
    """
    Check for duplicate rows in the DataFrame and return a summary.
    """
    mask = df.duplicated(keep=False)
    
    duplicate_rows = df[mask].copy()
    
    duplicate_rows.insert(0, "Fila Duplicada", duplicate_rows.index + 2)
    
    return duplicate_rows

def check_text_problems(df):
    """
    Check for text problems in the DataFrame and return a summary.
    """
    result = []
    
    for column in df.columns:
        
        serie = df[column]
        
        if not pd.api.types.is_string_dtype(serie):
            continue
        
        data = serie.dropna().astype(str)
        
        start_spaces = data.str.match(r"^\s+").sum()
        
        end_spaces = data.str.match(r".*\s+$").sum()
        
        double_spaces = data.str.contains(r"\s{2,}", regex=True).sum()
        
        result.append({
            "Columna": column,
            "Total": len(df),
            "Espacios Iniciales": start_spaces,
            "Espacios Finales": end_spaces,
            "Múltiples Espacios": double_spaces
        })
    
    return pd.DataFrame(result)

def check_lengths(df):
    """
    Check the lengths of string values in the DataFrame and return a summary.
    """
    result = []
    
    for column in df.columns:
        
        serie = df[column]
        
        if not pd.api.types.is_string_dtype(serie):
            continue
        
        data = serie.dropna().astype(str)
        
        min_length = data.str.len().min()
        max_length = data.str.len().max()
        avg_length = data.str.len().mean()
        
        result.append({
            "Columna": column,
            "Total": len(df),
            "Longitud Mínima": min_length,
            "Longitud Máxima": max_length,
            "Longitud Promedio": round(avg_length, 2)
        })
    
    return pd.DataFrame(result)