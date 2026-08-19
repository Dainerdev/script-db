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
