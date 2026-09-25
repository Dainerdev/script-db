#exportartion.py
import copy as _copy
import re
import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter


def export_excel(df, file_path):
    """
    Function to export a DataFrame to an Excel file
    """
    
    try:
        # Export the DataFrame to an Excel file
        df.to_excel(file_path, index=False)

        wb = load_workbook(file_path)
        ws = wb.active
        
        fecha_col = None
        
        # Search for the "Fecha" column
        for cell in ws[1]:
            if str(cell.value).strip().upper() == "FECHA":
                fecha_col = cell.column
                break
        
        # Apply date formatting to the "Fecha" column
        if fecha_col is not None:
            for row in range(2, ws.max_row + 1):
                cell = ws.cell(row, fecha_col)
                
                if cell.value is not None:
                    cell.number_format = "DD/MM/YYYY"
            
        wb.save(file_path)
        
        print(f"\nArchivo de resultados guardado en: {file_path}")
    
    except Exception as e:
        print(f"Error exporting Excel file: {e}")


def read_header_style(source_path, source_sheet=None):
    """
    "Hay alguna forma de copiar el estilo original?"

    Lee del archivo original: fuente y alineación del encabezado, alto de
    la fila 1, y el ancho de cada columna INDEXADO POR NOMBRE (no por
    letra), para poder aplicarlo después aunque el archivo de salida tenga
    columnas nuevas o en otro orden. Para columnas que no existían en el
    original (ej. "Nombres", "Reparto_Categoria") se calcula un ancho
    promedio como valor por defecto, en vez de dejarlas con el ancho
    genérico de openpyxl.
    """
    wb = load_workbook(source_path)
    ws = wb[source_sheet] if source_sheet else wb.active
    header_row = list(ws[1])

    font_ref = _copy.copy(header_row[0].font) if header_row else None
    align_ref = _copy.copy(header_row[0].alignment) if header_row else None
    row_height = ws.row_dimensions[1].height

    anchos_por_nombre = {}
    for cell in header_row:
        if cell.value is not None:
            letra = cell.column_letter
            ancho = ws.column_dimensions[letra].width if letra in ws.column_dimensions else None
            anchos_por_nombre[str(cell.value).strip()] = ancho

    validos = [w for w in anchos_por_nombre.values() if w]
    ancho_default = sum(validos) / len(validos) if validos else None

    # "eso incluye los colores?" -> el encabezado azul + filas con banda
    # celeste NO es relleno manual de celda (fill quedó vacío en la lectura
    # de arriba): el original está definido como una Tabla de Excel con
    # nombre (ws.tables), con un estilo con nombre (ej. "TableStyleMedium2")
    # que Excel renderiza en tiempo real. Para replicar el color hay que
    # replicar la TABLA, no una celda.
    table_style = None
    banded_rows = True
    if ws.tables:
        primera_tabla = ws.tables[list(ws.tables.keys())[0]]
        if primera_tabla.tableStyleInfo:
            table_style = primera_tabla.tableStyleInfo.name
            banded_rows = bool(primera_tabla.tableStyleInfo.showRowStripes)

    return {
        "font": font_ref,
        "alignment": align_ref,
        "row_height": row_height,
        "anchos_por_nombre": anchos_por_nombre,
        "ancho_default": ancho_default,
        "table_style": table_style,
        "banded_rows": banded_rows,
    }


def apply_header_style(ws, columns, style_ref):
    """
    Aplica a `ws` el estilo leído con read_header_style(). Las columnas que
    existían en el archivo original (comparando por nombre) recuperan su
    mismo ancho; las columnas nuevas quedan con el ancho promedio de las
    originales, para no verse desproporcionadas. La fuente y alineación del
    encabezado se aplican a todas las columnas por igual, existan o no en
    el original.
    """
    if style_ref.get("row_height"):
        ws.row_dimensions[1].height = style_ref["row_height"]

    for i, col_name in enumerate(columns, start=1):
        letra = get_column_letter(i)
        cell = ws.cell(1, i)
        if style_ref.get("font"):
            cell.font = _copy.copy(style_ref["font"])
        if style_ref.get("alignment"):
            cell.alignment = _copy.copy(style_ref["alignment"])

        ancho = style_ref["anchos_por_nombre"].get(str(col_name).strip(), style_ref.get("ancho_default"))
        if ancho:
            ws.column_dimensions[letra].width = ancho


def export_multi_sheet_excel(sheets, file_path, table_style="TableStyleMedium2", ancho_min=10, ancho_max=50):
    """
    Exporta varios DataFrames a un mismo archivo Excel, un sheet por cada
    entrada de `sheets` (dict: nombre_de_hoja -> DataFrame). Aplica el
    formato DD/MM/YYYY a cualquier columna "FECHA" que encuentre, en
    cualquier hoja.
 
    ESTILO: cada hoja se convierte en una Tabla de Excel con nombre
    (encabezado azul, texto blanco en negrilla, filtro automático y
    filas con banda -igual a la imagen de referencia) usando un estilo
    ya integrado en Excel, en vez de leerlo de un archivo externo. Los
    estilos disponibles siguen el patrón "Table Style Light/Medium/Dark N"
    (N de 1 a 28 aprox.); "Table Style Medium 2" es el azul clásico.
    Cambia `table_style` si quieres otro color (ej. "Table Style Medium 7"
    para verde, "Table Style Medium 4" para gris).
 
    `ancho_columna`: ancho fijo (en caracteres) para todas las columnas.
    Pon None si no quieres que la función toque los anchos.
 
    NOTA DE RENDIMIENTO: usa el engine 'xlsxwriter' para escribir (mucho
    más rápido que 'openpyxl' en hojas grandes) y aplica formato POR
    COLUMNA COMPLETA (worksheet.set_column), no celda por celda.
    """
    try:
        with pd.ExcelWriter(
            file_path, engine="xlsxwriter",
            date_format="dd/mm/yyyy", datetime_format="dd/mm/yyyy",
        ) as writer:
            for sheet_name, data in sheets.items():
                safe_name = str(sheet_name)[:31]  # limite de Excel para nombres de hoja
 
                # Se escribe la data SIN encabezado propio (header=False,
                # startrow=1) y se deja que add_table() cree el
                # encabezado -así hereda el color y el filtro automático
                # del estilo elegido.
                data.to_excel(writer, sheet_name=safe_name, index=False, header=False, startrow=1)
                ws = writer.sheets[safe_name]
 
                ws.add_table(0, 0, len(data), len(data.columns) - 1, {
                    "style": table_style,
                    "banded_rows": True,
                    "columns": [{"header": str(c)} for c in data.columns],
                })
                
                ws.autofit()
 
                if ancho_min is not None or ancho_max is not None:
                    for i, col_name in enumerate(data.columns):
                        serie = data[col_name].astype(str)
                        largo = max(serie.str.len().max() if len(serie) else 0, len(str(col_name))) + 2
                        if ancho_min is not None:
                            largo = max(largo, ancho_min)
                        if ancho_max is not None:
                            largo = min(largo, ancho_max)
                        ws.set_column(i, i, largo)
 
        print(f"\nArchivo con {len(sheets)} hoja(s) guardado en: {file_path}")
 
    except Exception as e:
        print(f"Error exporting multi-sheet Excel file: {e}")
