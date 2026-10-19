#exportartion.py
import copy as _copy
import datetime
import math
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter


def _nombre_estilo_tabla_xlsxwriter(nombre_openpyxl):
    """
    openpyxl guarda el estilo de tabla como "TableStyleMedium2";
    xlsxwriter espera "Table Style Medium 2" (con espacios). Inserta un
    espacio antes de cada mayúscula (que no sea la primera letra) y antes
    de cada dígito.
    """
    if not nombre_openpyxl:
        return None
    return re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=[0-9])", " ", nombre_openpyxl)

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
        # BUGFIX: la comparacion era case-sensitive ("Fecha" exacto) y la
        # columna real se llama "FECHA" (mayusculas) tanto en el archivo
        # original como despues de standarize_column_dates, asi que el
        # formato DD/MM/YYYY nunca se aplicaba (se veia en Excel como
        # 2019-03-29 en vez de 29/03/2019).
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


_XML = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
_R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_ESCAPE = re.compile(r"_x([0-9A-Fa-f]{4})_")


def _decode_xstring(text):
    """Excel escribe en el XML algunos caracteres como _xHHHH_ (un salto de línea es _x000a_)."""
    return _ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), text)


def _part(base_dir, target):
    """Ruta dentro del zip de un Target de relación (relativo a la carpeta de la parte, o absoluto)."""
    if target.startswith("/"):
        return target[1:]
    return posixpath.normpath(posixpath.join(base_dir, target))


def _relations(z, part):
    """{Id: (Type, ruta)} de las relaciones de una parte del .xlsx."""
    folder, name = posixpath.split(part)
    rels_path = posixpath.join(folder, "_rels", f"{name}.rels")
    if rels_path not in z.namelist():
        return {}
    root = ET.fromstring(z.read(rels_path))
    return {r.get("Id"): (r.get("Type", ""), _part(folder, r.get("Target", "")))
            for r in root.findall("rel:Relationship", _XML)}


def read_table_layout(source_path, source_sheet=None):
    """
    Lo mismo que read_header_style usa la exportación —alto de la fila 1,
    ancho de cada columna por nombre, ancho promedio, estilo de la tabla y si
    tiene bandas—, leído directo del XML del .xlsx (spec 002, T20). No carga
    las filas: read_header_style abre el libro completo con openpyxl y con el
    corte del 5 de agosto (130 MB de hoja más 111 MB de caché de una tabla
    dinámica) tardaba 414 s. Los nombres salen de la Tabla de Excel de la
    hoja; si la hoja no tiene tabla, o algo del XML no se entiende, usa
    read_header_style. A diferencia de openpyxl, una columna dentro de un
    rango (<col min="21" max="23">) toma el ancho del rango, como en el
    original (openpyxl solo se lo daba a la primera).
    """
    try:
        layout = _read_table_layout_xml(source_path, source_sheet)
    except (KeyError, ValueError, ET.ParseError, zipfile.BadZipFile):
        layout = None
    return layout if layout is not None else read_header_style(source_path, source_sheet)


def _read_table_layout_xml(source_path, source_sheet):
    with zipfile.ZipFile(source_path) as z:
        workbook = ET.fromstring(z.read("xl/workbook.xml"))
        sheets = workbook.findall("m:sheets/m:sheet", _XML)
        if source_sheet is None:
            view = workbook.find("m:bookViews/m:workbookView", _XML)
            sheet = sheets[int(view.get("activeTab", 0)) if view is not None else 0]
        else:
            sheet = next(s for s in sheets if s.get("name") == source_sheet)
        sheet_part = _relations(z, "xl/workbook.xml")[sheet.get(_R_ID)][1]

        tables = [path for kind, path in _relations(z, sheet_part).values() if kind.endswith("/table")]
        if not tables:
            return None
        table = ET.fromstring(z.read(tables[0]))
        names = [_decode_xstring(c.get("name", "")) for c in table.findall("m:tableColumns/m:tableColumn", _XML)]
        first_column = column_index_from_string(re.match(r"[A-Z]+", table.get("ref")).group())
        style_info = table.find("m:tableStyleInfo", _XML)

        widths, row_height = {}, None
        with z.open(sheet_part) as stream:
            for event, element in ET.iterparse(stream, events=("start", "end")):
                tag = element.tag.rsplit("}", 1)[-1]
                if event == "end" and tag == "col" and element.get("width"):
                    for index in range(int(element.get("min")), int(element.get("max")) + 1):
                        widths[index] = float(element.get("width"))
                elif event == "start" and tag == "row":          # lo de antes de la primera fila ya pasó
                    if element.get("r", "1") == "1" and element.get("ht"):
                        row_height = float(element.get("ht"))
                    break

    anchos_por_nombre = {name.strip(): widths.get(first_column + i) for i, name in enumerate(names)}
    validos = [w for w in anchos_por_nombre.values() if w]
    return {
        "font": None,
        "alignment": None,
        "row_height": row_height,
        "anchos_por_nombre": anchos_por_nombre,
        "ancho_default": sum(validos) / len(validos) if validos else None,
        "table_style": style_info.get("name") if style_info is not None else None,
        "banded_rows": style_info.get("showRowStripes", "1") in ("1", "true") if style_info is not None else True,
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


class ExportCancelled(Exception):
    """El usuario canceló la exportación a mitad de camino (should_cancel)."""


# Relleno de las celdas con un valor pendiente de revisión (spec 002, RF-40).
PENDING_FILL = "#FFEB9C"


def _write_highlighted(ws, row, col, value, fill, date_fill):
    """Reescribe una celda ya escrita con el relleno de pendiente, conservando su tipo (texto, número, fecha, vacío)."""
    if value is None or value is pd.NaT:
        ws.write_blank(row, col, None, fill)
    elif isinstance(value, (datetime.datetime, datetime.date)):            # también pd.Timestamp
        ws.write_datetime(row, col, value, date_fill)
    else:
        if hasattr(value, "item") and not isinstance(value, (str, bytes)):
            value = value.item()                                            # numpy → tipo de Python
        if isinstance(value, float) and math.isnan(value):
            ws.write_blank(row, col, None, fill)
        else:
            ws.write(row, col, value, fill)


def export_multi_sheet_excel(sheets, file_path, style_reference_path=None, style_reference_sheet=None,
                              raise_errors=False, on_sheet_done=None, on_sheet_start=None, should_cancel=None,
                              highlight_cells=None):
    """
    Exporta varios DataFrames a un mismo archivo Excel, un sheet por cada
    entrada de `sheets` (dict: nombre_de_hoja -> DataFrame). Aplica el
    formato DD/MM/YYYY a cualquier columna "FECHA" que encuentre, en
    cualquier hoja. Si se pasa `style_reference_path`, además replica en
    cada hoja el estilo de encabezado (fuente, alineación, alto de fila,
    anchos de columna) de ese archivo -ver read_header_style().

    NOTA DE RENDIMIENTO (dos vueltas):
    1. La primera version releia el archivo completo con load_workbook()
       despues de escribirlo y recorria celda por celda con
       ws.cell(row, col) -no alcanzaba a terminar en una hoja de ~185 mil
       filas, asi que el formato quedaba sin aplicar aunque los datos si se
       guardaban.
    2. La segunda version ya no releia el archivo, pero seguia usando el
       engine 'openpyxl' para ESCRIBIR, que en la prueba tardó 79.6s solo
       para la hoja de 184.692 x 27 -sigue sin alcanzar a terminar dentro
       de un tiempo razonable sumando las otras 7 hojas. 'openpyxl'
       construye un objeto por cada celda; para escrituras grandes es
       conocido por ser mucho más lento que la alternativa.
    Esta version usa el engine 'xlsxwriter' (ya está en requirements.txt)
    para escribir, y aplica formato POR COLUMNA COMPLETA
    (worksheet.set_column) en vez de celda por celda -una sola llamada por
    columna en vez de una por cada fila.

    raise_errors=False (default) preserva el comportamiento original:
    imprime el error y retorna None sin guardar nada. Con
    raise_errors=True, además relanza la excepción original después de
    imprimirla, para que un caller (la GUI) sepa que el guardado falló en
    vez de asumir éxito.

    on_sheet_start(sheet_name, indice, total) se llama justo ANTES de
    empezar a escribir cada hoja (para que el caller pueda animar una
    barra de progreso mientras espera -la escritura en sí no tiene
    puntos de avance intermedios). on_sheet_done(sheet_name, indice, total)
    se llama justo despues de terminar -progreso real, no estimado.
    should_cancel (funcion sin argumentos que retorna bool) se revisa
    antes de cada hoja; si retorna True, se aborta lanzando
    ExportCancelled (subclase de Exception: sigue el mismo camino de
    raise_errors que cualquier otro error, pero el caller puede
    distinguirla con un except aparte).

    highlight_cells (spec 002, RF-40, Decisión #7; opcional, por defecto
    None: el archivo sale igual que antes) es un dict nombre_de_hoja ->
    lista de (posición de la fila en el DataFrame, nombre de la columna):
    esas celdas se reescriben con el relleno PENDING_FILL. Se pinta la
    celda exacta; un formato condicional no sabría qué columna de la fila
    quedó pendiente.
    """
    try:
        # T20: read_table_layout lee el XML sin cargar las filas (read_header_style tardaba 414 s con el corte).
        style_ref = read_table_layout(style_reference_path, style_reference_sheet) if style_reference_path else None
        estilo_tabla = _nombre_estilo_tabla_xlsxwriter(style_ref["table_style"]) if style_ref else None

        # date_format/datetime_format van en el CONSTRUCTOR de ExcelWriter:
        # to_excel() ya escribe las celdas de fecha con su propio formato
        # (por defecto "YYYY-MM-DD") en el momento en que las escribe; un
        # set_column() posterior no alcanza a sobreescribir celdas que ya
        # tienen formato propio. Puesto aquí, aplica a CUALQUIER columna de
        # tipo fecha en CUALQUIER hoja (FECHA, Reparto_Fecha, etc.).
        with pd.ExcelWriter(
            file_path, engine="xlsxwriter",
            date_format="dd/mm/yyyy", datetime_format="dd/mm/yyyy",
        ) as writer:
            workbook = writer.book
            total_hojas = len(sheets)
            fill = workbook.add_format({"bg_color": PENDING_FILL, "pattern": 1})
            date_fill = workbook.add_format({"bg_color": PENDING_FILL, "pattern": 1, "num_format": "dd/mm/yyyy"})

            for indice, (sheet_name, data) in enumerate(sheets.items(), start=1):
                if should_cancel and should_cancel():
                    raise ExportCancelled(f"Cancelado antes de escribir la hoja '{sheet_name}'")

                if on_sheet_start:
                    on_sheet_start(sheet_name, indice, total_hojas)

                safe_name = str(sheet_name)[:31]  # limite de Excel para nombres de hoja

                if estilo_tabla:
                    # el encabezado azul + filas con banda celeste del
                    # original NO es relleno manual de celda, es el estilo
                    # con nombre de una Tabla de Excel (ver
                    # read_header_style). Se escribe la data SIN encabezado
                    # propio (header=False, startrow=1) y se deja que
                    # add_table() cree el encabezado -asi hereda el color y
                    # el filtro automático igual que el original.
                    data.to_excel(writer, sheet_name=safe_name, index=False, header=False, startrow=1)
                    ws = writer.sheets[safe_name]
                    ws.add_table(0, 0, len(data), len(data.columns) - 1, {
                        "style": estilo_tabla,
                        "banded_rows": style_ref.get("banded_rows", True),
                        "columns": [{"header": str(c)} for c in data.columns],
                    })
                else:
                    data.to_excel(writer, sheet_name=safe_name, index=False)
                    ws = writer.sheets[safe_name]

                if style_ref and style_ref.get("row_height"):
                    ws.set_row(0, style_ref["row_height"])

                for i, col_name in enumerate(data.columns):
                    col_str = str(col_name).strip()
                    ancho = style_ref["anchos_por_nombre"].get(col_str, style_ref.get("ancho_default")) if style_ref else None
                    if ancho:
                        ws.set_column(i, i, ancho)

                if highlight_cells and highlight_cells.get(sheet_name):          # RF-40
                    position_of = {str(c): i for i, c in enumerate(data.columns)}
                    for row, column in highlight_cells[sheet_name]:
                        col = position_of[str(column)]
                        _write_highlighted(ws, row + 1, col, data.iat[row, col], fill, date_fill)

                if on_sheet_done:
                    on_sheet_done(sheet_name, indice, total_hojas)

        print(f"\nArchivo con {len(sheets)} hoja(s) guardado en: {file_path}")

    except Exception as e:
        print(f"Error exporting multi-sheet Excel file: {e}")
        if raise_errors:
            raise
