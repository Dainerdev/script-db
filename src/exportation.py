import pandas as pd
from openpyxl import load_workbook

def export_excel(df, file_path):
    """
    Function to export a DataFrame to an Excel file
    """
    
    try:
        # Export the DataFrame to an Excel file
        df.to_excel(file_path, index=False)

        wb = load_workbook(file_path)
        ws = wb.active
        
        # Search for the "Fecha" column
        for cell in ws[1]:
            if cell.value == "Fecha":
                fecha_col = cell.column
                break
        
        # Apply date formatting to the "Fecha" column
        for row in range(2, ws.max_row + 1):
            ws.cell(row, fecha_col).number_format = "DD/MM/YYYY"
            
        wb.save(file_path)
        
        print(f"\nArchivo de resultados guardado en: {file_path}")
    
    except Exception as e:
        print(f"Error exporting Excel file: {e}")