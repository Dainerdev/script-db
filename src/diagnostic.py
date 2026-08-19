import pandas as pd

def check_columns(df):
    
    results = []
    
    for column in df.columns:
        
        serie = df[column]
        
        total = len(serie)
        nulls = serie.isnull().sum()
        unique = serie.nunique(dropna=True)
        
        results.append({
            "Columna": column,
            "Tipo": str(serie.dtype),
            "Total": total,
            "Nulos": nulls,
            "Porcentaje Nulos": round((nulls / total) * 100, 2),
            "Unicos": unique,
            "Duplicados": total - unique - nulls
        })
    
    return pd.DataFrame(results)
    
