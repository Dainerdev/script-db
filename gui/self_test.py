"""
Autoprueba del .exe empaquetado (spec 002, T21):

    LimpiezaJEP.exe --autoprueba entrada.xlsx salida.xlsx

Hace lo mismo que los botones "Procesar" y "Guardar resultado..." —leer y
validar, procesar, guardar el resultado y el Excel de revisión— sin abrir
ventanas ni diálogos, para comprobar que el .exe trae todo lo que necesita
(rapidfuzz, calamine, xlsxwriter…). El .exe se empaqueta con --windowed y no
tiene consola: el resultado queda en `<salida>.autoprueba.txt` y en el
código de salida (0 bien, 1 mal). Sin ese argumento, el .exe abre la ventana
como siempre.
"""
import traceback
from pathlib import Path

import rapidfuzz

from gui import controller
from src import pipeline


def run_self_test(input_path, output_path) -> int:
    report = Path(f"{output_path}.autoprueba.txt")
    try:
        events = []
        controller.read_and_validate(input_path, events.append)
        if events[-1][0] != "diagnostic":
            raise RuntimeError(f"No se pudo leer la entrada: {events[-1][1]}")
        df = events[-1][3]

        events = []
        controller.process(df, input_path, events.append)
        if events[-1][0] != "done":
            raise RuntimeError(f"El proceso terminó con «{events[-1][0]}»: {events[-1][1:]}")
        result = events[-1][1]

        result_path, review_path = pipeline.save(result, output_path, style_reference_path=input_path)
        lines = ["OK", f"resultado: {result_path}", f"revisión: {review_path}",
                 *(f"{sheet}: {count}" for sheet, count in result.counts.items()),
                 f"pendientes: {result.pending_values} valores, {result.pending_rows} filas",
                 f"rapidfuzz: {rapidfuzz.__version__}"]
        code = 0
    except Exception:
        lines = ["ERROR", traceback.format_exc()]
        code = 1
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return code
