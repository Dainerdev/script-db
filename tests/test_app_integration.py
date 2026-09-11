"""
Integración de extremo a extremo: simula lo que dispararían los botones
reales de la GUI (seleccionar -> leer/diagnosticar -> procesar -> se
abre el diálogo de guardado automáticamente, RF-8 -> exportar), pero
llamando directamente al mismo código que usan los callbacks de
gui/app.py en vez de clics reales — no hay una herramienta de
automatización de apps nativas de Windows disponible en este entorno.

IMPORTANTE: esto corre en el escritorio Windows real del usuario (no un
sandbox aislado). _handle_process_done dispara _prompt_save()
AUTOMÁTICAMENTE al despachar el evento "done" (así implementa RF-8), así
que TODAS las funciones de diálogo (filedialog.asksaveasfilename,
messagebox.askyesno/showinfo) se neutralizan ANTES de despachar
cualquier evento — de lo contrario aparece un diálogo real en pantalla
(pasó una vez durante el desarrollo de este test; ver conversación).
También se neutraliza _start_thread para que el export ocurra síncrono
en vez de en un hilo real (no hay mainloop() en la prueba).

No reemplaza una pasada manual real con la app corriendo (ver T8/T9 en
tasks.md), pero sí prueba que el cableado completo entre gui/app.py,
gui/controller.py y src/ funciona con un archivo realista.
"""
import openpyxl
import pandas as pd
from tkinter import messagebox

from gui.app import App
from gui import controller


def _crear_excel_prueba(ruta):
    df = pd.DataFrame({
        "No": [1, 2, 3, 4, 5],
        "RADICADO IUS": ["E-2020-100001", "E-2020-100001", "E-2020-100002", "E-2020-100003", "E-2020-100004"],
        "IDENTIFICACIÓN": ["1000000001", "1000000001", "1000000002\n1000000003", "1000000004", "1000000004"],
        "NOMBRES_APELLIDOS": [
            "  juan pérez gómez  ",
            "JUAN PEREZ GOMEZ",
            "maria lopez\nana torres",
            "Carlos Ruiz",
            "carlos  ruiz",
        ],
        "FECHA": ["01/03/2021", "02/03/2021", "03/03/2021", "04/03/2021", "05/03/2021"],
        "REPARTO": ["Marzo 2021", "Marzo 2021", "Marzo 2021", "Marzo 2021", "Marzo 2021"],
        "CLASIFICACIÓN DEL RADICADO": ["ACTIVO", "ARCHIVADO", "ACTIVO", "ARCHIVADO", "SIM"],
        "FUNCIONARIO A CARGO": ["JUAN PEREZ", "FUNCIONARIOS RETIRADOS", "MARIA LOPEZ", "ANA TORRES", "JUAN PEREZ"],
        "MAGISTRADO": ["Pedro Suarez", "Pedro Suarez", "Ana Torres", "Ana Torres", "Pedro Suarez"],
    })
    df.to_excel(ruta, sheet_name="Reparto", index=False)


def test_flujo_completo_seleccion_diagnostico_procesar_guardar(tmp_path, monkeypatch):
    entrada = tmp_path / "base_prueba.xlsx"
    _crear_excel_prueba(entrada)
    salida = tmp_path / "resultado.xlsx"

    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    try:
        app = App(root)

        # Neutraliza TODO diálogo real y el threading ANTES de despachar
        # ningún evento — _handle_process_done llama _prompt_save() solo,
        # sin que el test lo pida explícitamente (así es RF-8).
        import gui.app as app_module
        monkeypatch.setattr(app_module.filedialog, "asksaveasfilename", lambda **k: str(salida))
        monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
        monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: None)
        monkeypatch.setattr(messagebox, "showerror", lambda *a, **k: None)
        monkeypatch.setattr(app, "_start_thread", lambda target, *args: target(*args))

        # --- "Seleccionar archivo" (RF-1/RF-2) ---
        app.selected_path = str(entrada)
        eventos = []
        controller.read_and_validate(str(entrada), eventos.append)
        for e in eventos:
            app._dispatch(e)

        assert app.df is not None, "El archivo de prueba debería leerse y validarse sin advertencias"
        assert str(app.process_button["state"]) == "normal"

        # --- "Procesar" (RF-5/RF-6/RF-7) -> dispara guardado automático (RF-8) ---
        eventos = []
        controller.process(app.df, app.source_path, eventos.append)
        for e in eventos:
            app._dispatch(e)

        assert app.process_result is not None
        counts = app.process_result.counts
        # SIM y Multiples_IUS son copias/extracciones que se solapan con
        # Reparto_Activo (ver src/diagnostic.py) — la partición exclusiva
        # real es Activos + Archivados + Retirados. split_multiple_comparecientes
        # desdobla la fila con 2 comparecientes -> 6 filas en vez de 5.
        assert counts["Reparto_Activo"] + counts["Archivados"] + counts["Funcionarios_Retirados"] == 6
        assert counts["SIM"] == 1
        assert counts["Multiples_IUS"] == 2

        # _run_export (disparado por el guardado automático de RF-8) puso
        # sus propios eventos en app.queue, no en la lista `eventos` de
        # arriba — se drenan para que _handle_export_done marque saved=True.
        while not app.queue.empty():
            app._dispatch(app.queue.get_nowait())

        assert salida.exists(), "export_multi_sheet_excel debería haber escrito el archivo de salida"
        wb = openpyxl.load_workbook(salida)
        assert set(wb.sheetnames) == {
            "Reparto_Activo", "Archivados", "Funcionarios_Retirados", "SIM", "Multiples_IUS",
        }
        assert app.saved is True
    finally:
        root.destroy()
