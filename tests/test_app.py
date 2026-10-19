import pytest

from gui.app import App


# La fixture `root` (un tk.Toplevel por test) está en tests/conftest.py.

def test_app_constructs_without_error(root):
    app = App(root)
    assert app.select_button is not None
    assert str(app.process_button["state"]) == "disabled"
    assert str(app.select_button["state"]) == "normal"


def test_initial_state_is_idle(root):
    app = App(root)
    assert app.df is None
    assert app.process_result is None
    assert app.busy is False
    assert app.saved is True


def test_set_busy_disables_controls(root):
    app = App(root)
    app._set_busy(True)
    assert str(app.select_button["state"]) == "disabled"
    assert str(app.process_button["state"]) == "disabled"

    app._set_busy(False)
    assert str(app.select_button["state"]) == "normal"
    # process_button sigue deshabilitado: todavía no hay df cargado.
    assert str(app.process_button["state"]) == "disabled"


def test_cancel_button_hidden_unless_busy_and_cancellable(root):
    app = App(root)
    assert not app.cancel_button.grid_info()

    app._set_busy(True)  # ej. leyendo archivo: no cancelable
    assert not app.cancel_button.grid_info()
    app._set_busy(False)

    app._set_busy(True, cancellable=True)  # ej. Procesar
    assert app.cancel_button.grid_info()

    app._set_busy(False)
    assert not app.cancel_button.grid_info()


def test_cancel_click_sets_flag_and_disables_button(root):
    app = App(root)
    app._set_busy(True, cancellable=True)
    assert app.cancel_requested is False

    app._on_cancel_click()

    assert app.cancel_requested is True
    assert str(app.cancel_button["state"]) == "disabled"


def test_set_busy_cancellable_resets_stale_cancel_flag(root):
    app = App(root)
    app._set_busy(True, cancellable=True)
    app._on_cancel_click()
    app._set_busy(False)

    app._set_busy(True, cancellable=True)  # nueva operación
    assert app.cancel_requested is False  # no hereda el cancel anterior


def test_progress_crawl_moves_toward_target_without_reaching_it(root):
    app = App(root)
    app._start_progress_crawl(0.0, 0.5)
    assert app._crawl_active is True
    # _start_progress_crawl ya dispara el primer tick: se mueve, pero no
    # llega sola al objetivo.
    primer_valor = app.progress_bar["value"]
    assert 0.0 < primer_valor < 0.5

    app._tick_crawl()  # un tick manual más, sin esperar los 150ms reales
    segundo_valor = app.progress_bar["value"]
    assert primer_valor < segundo_valor < 0.5


def test_progress_stop_crawl_sets_exact_value_and_deactivates(root):
    app = App(root)
    app._start_progress_crawl(0.0, 0.5)
    app._tick_crawl()

    app._stop_progress_crawl(0.5)

    assert app._crawl_active is False
    assert app.progress_bar["value"] == 0.5

    valor_antes = app.progress_bar["value"]
    app._tick_crawl()  # ya inactivo: no debe seguir moviendo la barra
    assert app.progress_bar["value"] == valor_antes


def test_progress_crawl_step_is_linear_and_caps_below_target(root):
    app = App(root)
    app._start_progress_crawl(0.0, 1.0)

    valores = []
    for _ in range(200):  # muchos más ticks de los necesarios para llegar al tope
        app._tick_crawl()
        valores.append(app.progress_bar["value"])

    # Nunca alcanza el objetivo real (1.0) por sí sola.
    assert valores[-1] < 1.0
    assert valores[-1] == pytest.approx(app.CRAWL_CAP_FRACTION, abs=0.01)
    # El avance es parejo (pasos de tamaño similar), no se vuelve
    # imperceptible cerca del tope como con un decaimiento proporcional.
    paso_inicial = valores[1] - valores[0]
    paso_cerca_del_tope = valores[40] - valores[39]
    assert paso_cerca_del_tope == pytest.approx(paso_inicial, rel=0.05)


def test_new_crawl_cancels_the_previous_timer_chain(root):
    # T17 (revisión de OpenCode): desde la spec 002 el controlador manda un
    # progress_crawl por etapa sin un progress entre ellas; si cada uno deja
    # viva su cadena de after(), la barra corre varias veces más rápido y se
    # queda quieta el resto de la etapa.
    app = App(root)
    app._start_progress_crawl(0.0, 0.5)
    primera = app._crawl_after_id

    app._start_progress_crawl(0.5, 0.9)

    pendientes = root.tk.splitlist(root.tk.call("after", "info"))
    assert primera not in pendientes
    assert app._crawl_after_id in pendientes


def test_stop_crawl_cancels_its_pending_tick(root):
    app = App(root)
    app._start_progress_crawl(0.0, 0.5)
    pendiente = app._crawl_after_id

    app._stop_progress_crawl(0.5)

    assert pendiente not in root.tk.splitlist(root.tk.call("after", "info"))


def test_set_busy_false_stops_any_active_crawl(root):
    app = App(root)
    app._start_progress_crawl(0.0, 1.0)
    assert app._crawl_active is True

    app._set_busy(False)

    assert app._crawl_active is False


def test_handle_cancelled_reshows_save_button_if_result_pending(root):
    from gui.state import ProcessResult
    import pandas as pd

    app = App(root)
    app.process_result = ProcessResult(sheets={"A": pd.DataFrame()}, counts={"A": 0}, source_path="x.xlsx")
    app._handle_cancelled()
    assert app.save_button.grid_info()


def test_handle_diagnostic_without_missing_columns_enables_process(root, monkeypatch):
    from gui.state import ValidationResult, DiagnosticSummary
    import pandas as pd

    app = App(root)
    app.selected_path = "entrada.xlsx"
    validation = ValidationResult(sheet_ok=True, missing_columns=[], can_continue=True)
    diagnostic = DiagnosticSummary(
        total_rows=1, rows_with_extra_spaces=0, nulls_by_key_column={},
        duplicated_rows=0, ids_with_name_variants=0, duplicated_ius=0, fuzzy_similar_names=0,
    )
    df = pd.DataFrame({"A": [1]})

    app._handle_diagnostic(validation, diagnostic, df)

    assert app.df is df
    assert app.source_path == "entrada.xlsx"
    assert str(app.process_button["state"]) == "normal"


def test_handle_diagnostic_with_missing_columns_asks_and_cancels(root, monkeypatch):
    from gui.state import ValidationResult, DiagnosticSummary
    from tkinter import messagebox
    import pandas as pd

    app = App(root)
    app.selected_path = "entrada.xlsx"
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: False)  # el funcionario cancela

    validation = ValidationResult(sheet_ok=True, missing_columns=["FECHA"], can_continue=True)
    diagnostic = DiagnosticSummary(
        total_rows=1, rows_with_extra_spaces=0, nulls_by_key_column={},
        duplicated_rows=0, ids_with_name_variants=0, duplicated_ius=0, fuzzy_similar_names=0,
    )
    df = pd.DataFrame({"A": [1]})

    app._handle_diagnostic(validation, diagnostic, df)

    assert app.df is None  # se descartó al cancelar
    assert str(app.process_button["state"]) == "disabled"


# ---------------------------------------------------------------------
# RF-8/RF-9/RF-10: guardado automático, sobrescritura, cancelar el diálogo
# Ninguno de estos tests deja aparecer un diálogo real: se reemplaza
# filedialog.asksaveasfilename / messagebox.askyesno ANTES de llamar
# cualquier método, siguiendo el mismo patrón ya verificado en
# tests/test_app_integration.py.
# ---------------------------------------------------------------------

def test_handle_process_done_stores_result_and_triggers_prompt_save(root, monkeypatch):
    from gui.state import ProcessResult

    app = App(root)
    llamadas = {"n": 0}
    monkeypatch.setattr(app, "_prompt_save", lambda: llamadas.__setitem__("n", llamadas["n"] + 1))

    pr = ProcessResult(sheets={}, counts={}, source_path="entrada.xlsx")
    app._handle_process_done(pr)

    assert app.process_result is pr
    assert app.saved is False
    assert llamadas["n"] == 1


def test_prompt_save_cancelled_dialog_keeps_result_for_retry(root, monkeypatch):
    import gui.app as app_module
    from gui.state import ProcessResult

    app = App(root)
    app.source_path = "entrada.xlsx"
    app.process_result = ProcessResult(sheets={}, counts={}, source_path="entrada.xlsx")
    monkeypatch.setattr(app_module.filedialog, "asksaveasfilename", lambda **k: "")  # cancela

    app._prompt_save()

    assert app.process_result is not None  # RF-10: se conserva, no se reprocesa
    assert app.save_button.grid_info()      # botón de reintento visible
    assert app.busy is False


def test_prompt_save_same_path_as_source_asks_and_respects_no(root, monkeypatch):
    import gui.app as app_module
    from gui.state import ProcessResult
    from tkinter import messagebox

    app = App(root)
    app.source_path = "C:/entrada.xlsx"
    app.process_result = ProcessResult(sheets={}, counts={}, source_path="C:/entrada.xlsx")
    monkeypatch.setattr(app_module.filedialog, "asksaveasfilename", lambda **k: "C:/entrada.xlsx")
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: False)  # RF-9: dice "no"
    exportaciones = []
    monkeypatch.setattr(app, "_start_thread", lambda *a, **k: exportaciones.append(a))

    app._prompt_save()

    assert exportaciones == []  # no se disparó el guardado
    assert app.save_button.grid_info()


def test_prompt_save_confirms_overwrite_and_starts_export(root, monkeypatch):
    import gui.app as app_module
    from gui.state import ProcessResult
    from tkinter import messagebox

    app = App(root)
    app.source_path = "C:/entrada.xlsx"
    app.process_result = ProcessResult(sheets={}, counts={}, source_path="C:/entrada.xlsx")
    monkeypatch.setattr(app_module.filedialog, "asksaveasfilename", lambda **k: "C:/entrada.xlsx")
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)  # RF-9: confirma
    llamadas = []
    monkeypatch.setattr(app, "_start_thread", lambda target, *args: llamadas.append((target, args)))

    app._prompt_save()

    assert len(llamadas) == 1
    assert llamadas[0][0] == app._run_export


# ---------------------------------------------------------------------
# RF-13: advertencia antes de descartar un resultado sin guardar
# ---------------------------------------------------------------------

def test_select_file_warns_before_discarding_unsaved_result_and_respects_no(root, monkeypatch):
    import gui.app as app_module
    from gui.state import ProcessResult
    from tkinter import messagebox

    app = App(root)
    app.process_result = ProcessResult(sheets={}, counts={}, source_path="anterior.xlsx")
    app.saved = False
    monkeypatch.setattr(app_module.filedialog, "askopenfilename", lambda **k: "nuevo.xlsx")
    preguntas = {"n": 0}

    def responder_no(*a, **k):
        preguntas["n"] += 1
        return False

    monkeypatch.setattr(messagebox, "askyesno", responder_no)

    app._on_select_file()

    assert preguntas["n"] == 1
    assert app.process_result is not None  # no se descartó


def test_select_file_discards_and_proceeds_when_confirmed(root, monkeypatch):
    import gui.app as app_module
    from gui.state import ProcessResult
    from tkinter import messagebox

    app = App(root)
    app.process_result = ProcessResult(sheets={}, counts={}, source_path="anterior.xlsx")
    app.saved = False
    monkeypatch.setattr(app_module.filedialog, "askopenfilename", lambda **k: "nuevo.xlsx")
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    llamadas = []
    monkeypatch.setattr(app, "_start_thread", lambda target, *args: llamadas.append((target, args)))

    app._on_select_file()

    assert app.process_result is None  # se descartó (_reset_state)
    assert app.selected_path == "nuevo.xlsx"
    assert len(llamadas) == 1


# ---------------------------------------------------------------------
# RF-15/RF-16: _run_export — limpieza al cancelar, progreso ponderado real
# ---------------------------------------------------------------------

def test_handle_export_done_shows_path_and_per_sheet_counts(root, monkeypatch):
    from tkinter import messagebox
    from gui.state import ProcessResult

    app = App(root)
    monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: None)
    app.process_result = ProcessResult(
        sheets={}, counts={"Reparto_Activo": 170002, "Archivados": 3833}, source_path="x.xlsx",
    )

    app._handle_export_done("C:/salida/resultado.xlsx")

    texto = app.summary_label["text"]
    assert "C:/salida/resultado.xlsx" in texto
    assert "Reparto_Activo" in texto and "170,002" in texto
    assert "Archivados" in texto and "3,833" in texto
    assert app.saved is True
    assert app.save_button.grid_info()


def test_run_export_cancelled_removes_partial_output_file(root, tmp_path):
    import queue as queue_module
    import pandas as pd
    from gui.state import ProcessResult

    app = App(root)
    app.queue = queue_module.Queue()
    salida = tmp_path / "salida.xlsx"
    pr = ProcessResult(
        sheets={"Hoja1": pd.DataFrame({"A": [1, 2]}), "Hoja2": pd.DataFrame({"A": [3]})},
        counts={"Hoja1": 2, "Hoja2": 1},
        source_path=None,
    )
    app.cancel_requested = True  # ya "canceló" antes de que arranque la escritura

    app._run_export(pr, str(salida))

    assert not salida.exists()  # RF-15: nada a medio escribir
    tags = [app.queue.get_nowait()[0] for _ in range(app.queue.qsize())]
    assert "cancelled" in tags


def test_run_export_progress_weighted_by_row_counts(root, tmp_path):
    import queue as queue_module
    import pandas as pd
    from gui.state import ProcessResult

    app = App(root)
    app.queue = queue_module.Queue()
    salida = tmp_path / "salida.xlsx"
    pr = ProcessResult(
        sheets={"Grande": pd.DataFrame({"A": range(90)}), "Chica": pd.DataFrame({"A": range(10)})},
        counts={"Grande": 90, "Chica": 10},
        source_path=None,
    )

    app._run_export(pr, str(salida))

    eventos = [app.queue.get_nowait() for _ in range(app.queue.qsize())]
    crawls = [e for e in eventos if e[0] == "progress_crawl"]
    # progresos[0] es el 0.0 inicial que _run_export pone antes del bucle;
    # los reales por hoja vienen después.
    progresos = [e[1] for e in eventos if e[0] == "progress"]
    assert progresos[0] == pytest.approx(0.0)

    # Al empezar "Grande" (90/100 filas): reptado de 0.0 hacia 0.9.
    assert crawls[0][1] == pytest.approx(0.0)
    assert crawls[0][2] == pytest.approx(0.9)
    # Al terminar "Grande": progreso real exacto 0.9 (no 0.5 por cantidad de hojas).
    assert progresos[1] == pytest.approx(0.9)
    # Al empezar "Chica": reptado de 0.9 hacia 1.0.
    assert crawls[1][1] == pytest.approx(0.9)
    assert crawls[1][2] == pytest.approx(1.0)
    # Al terminar todo: progreso real exacto 1.0.
    assert progresos[-1] == pytest.approx(1.0)


# ---------------------------------------------------------------------
# Spec 002, T17: resumen en la ventana, aviso de pendientes y guardado en
# par (RF-36, RF-43, RF-50, RF-55, RF-71, RF-80). Igual que arriba, todo
# diálogo se reemplaza antes de llamar cualquier método.
# ---------------------------------------------------------------------

PEGADO = "Ana Perez Gomez Y Luis Diaz Rojas"


def _resultado_real(pendiente=True):
    """Un ProcessResult de verdad, sacado del controlador con un archivo sintético."""
    import dataclasses
    import pandas as pd
    from gui import controller

    df = pd.DataFrame({
        "No": [1, 2],
        # Dos cédulas para una línea de nombres: celda SIN SEPARAR, pendiente (RF-25).
        "NOMBRES_APELLIDOS": [PEGADO if pendiente else "Ana Perez Gomez", "Luis Mora Paz"],
        "IDENTIFICACIÓN": ["10000001\n10000002" if pendiente else "10000001", "10000003"],
        "CLASIFICACIÓN DEL RADICADO": ["ACTIVO", "ACTIVO"],
        "SOLICITUD": ["Devolución", "DEVOLUCIÓN"],
    })
    eventos = []
    controller.process(df, "entrada.xlsx", eventos.append)
    assert eventos[-1][0] == "done"
    # Sin archivo de referencia de estilo, como en los tests de exportación de arriba.
    return dataclasses.replace(eventos[-1][1], source_path=None)


def _eventos(app):
    return [app.queue.get_nowait() for _ in range(app.queue.qsize())]


def test_handle_process_done_shows_standardization_summary(root, monkeypatch):
    app = App(root)
    monkeypatch.setattr(app, "_prompt_save", lambda: None)

    app._handle_process_done(_resultado_real())

    texto = app.standardization_text.get("1.0", "end")
    assert "Estados por columna" in texto and "SOLICITUD" in texto      # RF-43
    assert "Separación de comparecientes" in texto                       # RF-95
    assert str(app.standardization_text["state"]) == "disabled"          # solo lectura


def test_prompt_save_warns_about_pending_once_and_still_saves(root, monkeypatch):
    import gui.app as app_module
    from tkinter import messagebox

    app = App(root)
    app.source_path = "entrada.xlsx"
    avisos, dialogos = [], []
    monkeypatch.setattr(messagebox, "showwarning", lambda titulo, texto, **k: avisos.append(texto))
    monkeypatch.setattr(app_module.filedialog, "asksaveasfilename", lambda **k: dialogos.append(1) or "")
    monkeypatch.setattr(app, "_start_thread", lambda *a, **k: None)
    app.process_result = _resultado_real()
    app._pending_warned = False

    app._prompt_save()          # RF-50: avisa y abre igual el diálogo de guardar
    app._prompt_save()          # reintento (RF-10): ya no vuelve a avisar

    assert len(avisos) == 1 and "1 valor en 1 fila" in avisos[0]
    assert len(dialogos) == 2


def test_prompt_save_without_pending_does_not_warn(root, monkeypatch):
    import gui.app as app_module
    from tkinter import messagebox

    app = App(root)
    app.source_path = "entrada.xlsx"
    avisos = []
    monkeypatch.setattr(messagebox, "showwarning", lambda *a, **k: avisos.append(a))
    monkeypatch.setattr(app_module.filedialog, "asksaveasfilename", lambda **k: "")
    app.process_result = _resultado_real(pendiente=False)
    app._pending_warned = False

    app._prompt_save()

    assert app.process_result.pending_values == 0
    assert avisos == []


def test_run_export_saves_result_and_review_together(root, tmp_path):
    import queue as queue_module
    import openpyxl
    import pandas as pd

    app = App(root)
    app.queue = queue_module.Queue()
    salida = tmp_path / "resultado.xlsx"

    app._run_export(_resultado_real(), str(salida))

    revision = tmp_path / "resultado_revision.xlsx"
    eventos = _eventos(app)
    assert eventos[-1] == ("export_done", str(salida), str(revision))                     # RF-36
    assert ("stage", "Guardando el Excel de revisión...") in eventos
    assert sorted(p.name for p in tmp_path.iterdir()) == ["resultado.xlsx", "resultado_revision.xlsx"]
    resumen = pd.read_excel(revision, sheet_name="Resumen", dtype=str)
    assert "resultado_revision.xlsx" in set(resumen["Valores"])                            # RF-71
    hoja = openpyxl.load_workbook(salida)["Reparto_Activo"]
    encabezados = [c.value for c in hoja[1]]
    celda = hoja.cell(2, encabezados.index("NOMBRES_APELLIDOS") + 1)
    assert celda.fill.patternType == "solid"                                               # RF-40


def test_run_export_keeps_an_existing_review_and_says_so(root, tmp_path, monkeypatch):
    import queue as queue_module
    from tkinter import messagebox

    app = App(root)
    app.queue = queue_module.Queue()
    monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: None)
    salida = tmp_path / "resultado.xlsx"
    vieja = tmp_path / "resultado_revision.xlsx"
    vieja.write_text("con decisiones", encoding="utf-8")
    app.process_result = _resultado_real()

    app._run_export(app.process_result, str(salida))
    _, ruta_resultado, ruta_revision = _eventos(app)[-1]
    app._handle_export_done(ruta_resultado, ruta_revision)

    assert ruta_revision.endswith("resultado_revision (2).xlsx")                         # RF-71
    assert vieja.read_text(encoding="utf-8") == "con decisiones"
    texto = app.summary_label["text"]
    assert "resultado_revision (2).xlsx" in texto and "no se reemplazó" in texto


def test_export_summary_fits_in_few_lines(root, monkeypatch):
    # T18 (demo con la ventana real): rutas largas y una línea por hoja dejaban
    # poco lugar al resumen de la estandarización. RF-11 sigue: ruta completa
    # del resultado y registros por hoja.
    from tkinter import messagebox
    from gui.state import ProcessResult

    app = App(root)
    monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: None)
    app.process_result = ProcessResult(sheets={}, counts={"Reparto_Activo": 13, "SIM": 3}, source_path="x.xlsx")

    app._handle_export_done("C:/una/carpeta/larga/resultado.xlsx", "C:/una/carpeta/larga/resultado_revision.xlsx")

    texto = app.summary_label["text"]
    assert "C:/una/carpeta/larga/resultado.xlsx" in texto
    assert "Excel de revisión (en la misma carpeta): resultado_revision.xlsx" in texto
    assert "Registros por hoja: Reparto_Activo 13 · SIM 3" in texto
    assert len(texto.splitlines()) == 3


def test_run_export_cancelled_leaves_neither_file(root, tmp_path):
    import queue as queue_module

    app = App(root)
    app.queue = queue_module.Queue()
    app.cancel_requested = True

    app._run_export(_resultado_real(), str(tmp_path / "resultado.xlsx"))

    assert list(tmp_path.iterdir()) == []                                                  # RF-80
    assert _eventos(app)[-1] == ("cancelled",)


def test_run_export_cancelled_after_the_first_sheet_leaves_no_files(root, tmp_path):
    # RF-15/RF-80 con un archivo temporal ya a medio escribir (revisión de OpenCode).
    import queue as queue_module

    app = App(root)

    class Cola(queue_module.Queue):
        def put(self, item, *a, **k):
            super().put(item, *a, **k)
            if item[0] == "progress" and item[1] > 0:     # terminó la primera hoja
                app.cancel_requested = True

    app.queue = Cola()

    app._run_export(_resultado_real(), str(tmp_path / "resultado.xlsx"))

    eventos = _eventos(app)
    assert any(e[0] == "progress" and e[1] > 0 for e in eventos)     # sí alcanzó a escribir una hoja
    assert eventos[-1] == ("cancelled",)
    assert list(tmp_path.iterdir()) == []                             # ni resultado, ni revisión, ni ~tmp_


def test_run_export_progress_with_review_saves_the_last_stretch_for_it(root, tmp_path):
    import queue as queue_module
    from gui.app import REVIEW_PROGRESS_START

    app = App(root)
    app.queue = queue_module.Queue()

    app._run_export(_resultado_real(), str(tmp_path / "resultado.xlsx"))

    eventos = _eventos(app)
    puntos = [x for e in eventos if e[0] in ("progress", "progress_crawl") for x in e[1:]]
    antes_de_la_revision = eventos[:eventos.index(("stage", "Guardando el Excel de revisión..."))]
    assert max(e[1] for e in antes_de_la_revision if e[0] == "progress") == pytest.approx(REVIEW_PROGRESS_START)
    assert ("progress_crawl", REVIEW_PROGRESS_START, 1.0) in eventos
    assert puntos == sorted(puntos) and puntos[-1] == 1.0


def test_run_export_review_failure_leaves_neither_file(root, tmp_path, monkeypatch):
    import queue as queue_module
    from src import pipeline

    def falla(ruta, datos):
        raise OSError("disco lleno")

    app = App(root)
    app.queue = queue_module.Queue()
    monkeypatch.setattr(pipeline, "write_review", falla)       # el guardado vive en pipeline.save (T19)
    monkeypatch.chdir(tmp_path)               # el registro técnico va a ./logs
    salida = tmp_path / "salida"
    salida.mkdir()

    app._run_export(_resultado_real(), str(salida / "resultado.xlsx"))

    assert list(salida.iterdir()) == []                                                    # RF-80
    assert _eventos(app)[-1][0] == "export_error"


def test_export_error_shows_retry_button(root, monkeypatch):
    from tkinter import messagebox

    app = App(root)
    monkeypatch.setattr(messagebox, "showerror", lambda *a, **k: None)
    app.process_result = _resultado_real()
    app.saved = False                            # como queda después de procesar
    app._set_busy(True, cancellable=True)

    app._dispatch(("export_error", "No se pudo guardar.", None))

    assert app.save_button.grid_info()          # se puede reintentar sin reprocesar (como RF-10)
    assert app.saved is False


def test_run_export_file_open_in_another_program_says_so(root, tmp_path, monkeypatch):
    import queue as queue_module
    from src import pipeline

    def abierto(*a, **k):
        raise PermissionError(13, "Permission denied")

    app = App(root)
    app.queue = queue_module.Queue()
    monkeypatch.setattr(pipeline, "save_pair", abierto)        # el guardado vive en pipeline.save (T19)
    monkeypatch.chdir(tmp_path)

    app._run_export(_resultado_real(), str(tmp_path / "resultado.xlsx"))

    tag, mensaje, _ = _eventos(app)[-1]
    assert tag == "export_error"
    assert "abierto en otro programa" in mensaje


# ---------------------------------------------------------------------
# Spec 002, T18: botón "Cargar revisión" (RF-44, RF-47, RF-49, RF-59, RF-79)
# ---------------------------------------------------------------------

def _app_con_archivo(root):
    import pandas as pd

    app = App(root)
    app.df = pd.DataFrame({"A": [1]})
    app.source_path = "entrada.xlsx"
    app._set_busy(False)
    return app


def test_load_review_button_needs_a_file_and_is_off_while_busy(root):
    app = App(root)
    assert str(app.review_button["state"]) == "disabled"            # RF-49: sin archivo

    app = _app_con_archivo(root)
    assert str(app.review_button["state"]) == "normal"

    app._set_busy(True, cancellable=True)
    assert str(app.review_button["state"]) == "disabled"            # RF-79: durante un proceso


def test_load_review_warns_before_discarding_an_unsaved_result(root, monkeypatch):
    import gui.app as app_module
    from tkinter import messagebox

    app = _app_con_archivo(root)
    app.process_result = _resultado_real()
    app.saved = False
    preguntas, dialogos, hilos = [], [], []
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: preguntas.append(a) or False)   # dice "no"
    monkeypatch.setattr(app_module.filedialog, "askopenfilename", lambda **k: dialogos.append(1) or "rev.xlsx")
    monkeypatch.setattr(app, "_start_thread", lambda *a, **k: hilos.append(a))

    app._on_load_review_click()

    assert len(preguntas) == 1                                       # RF-59
    assert dialogos == [] and hilos == []
    assert app.process_result is not None


def test_load_review_cancelled_dialog_does_nothing(root, monkeypatch):
    import gui.app as app_module

    app = _app_con_archivo(root)
    hilos = []
    monkeypatch.setattr(app_module.filedialog, "askopenfilename", lambda **k: "")
    monkeypatch.setattr(app, "_start_thread", lambda *a, **k: hilos.append(a))

    app._on_load_review_click()

    assert hilos == []
    assert app.busy is False


def test_load_review_reads_the_file_in_a_thread(root, monkeypatch):
    import gui.app as app_module
    from gui import controller

    app = _app_con_archivo(root)
    hilos = []
    monkeypatch.setattr(app_module.filedialog, "askopenfilename", lambda **k: "C:/rev/revision.xlsx")
    monkeypatch.setattr(app, "_start_thread", lambda target, *args: hilos.append((target, args)))

    app._on_load_review_click()

    assert hilos == [(controller.read_review, ("C:/rev/revision.xlsx", app.queue.put))]
    assert app.busy is True
    assert str(app.review_button["state"]) == "disabled"


def test_review_error_shows_a_clear_message_and_changes_nothing(root, monkeypatch):
    from tkinter import messagebox

    app = _app_con_archivo(root)
    anterior = _resultado_real()
    app.process_result = anterior
    errores = []
    monkeypatch.setattr(messagebox, "showerror", lambda titulo, texto, **k: errores.append(texto))
    app._set_busy(True)

    app._dispatch(("review_error", "El archivo elegido no es un Excel de revisión ni una tabla de parámetros revisados."))

    assert errores and "no es un Excel de revisión" in errores[0]   # RF-47
    assert app.process_result is anterior
    assert app.busy is False and str(app.review_button["state"]) == "normal"


def test_review_loaded_reprocesses_with_its_decisions(root, monkeypatch):
    from gui import controller
    from src import review_excel as rx

    app = _app_con_archivo(root)
    app._review_path = "C:/rev/revision.xlsx"
    revision = rx.ReviewFile(table=None, has_decisions=True)
    hilos = []
    monkeypatch.setattr(app, "_start_thread", lambda target, *args, **kw: hilos.append((target, args, kw)))

    app._dispatch(("review_loaded", revision))                      # RF-44

    (target, args, kwargs), = hilos
    assert target == app._process_with_review
    assert args == (revision,)
    assert app.busy is True and app.cancel_button.grid_info()


def test_done_after_a_review_says_which_review_was_applied(root, monkeypatch):
    app = _app_con_archivo(root)
    monkeypatch.setattr(app, "_prompt_save", lambda: None)
    app._applied_review = "C:/rev/revision.xlsx"

    app._handle_process_done(_resultado_real())

    assert app.standardization_text.get("1.0", "end").startswith("Revisión aplicada: revision.xlsx")


def test_plain_process_forgets_the_applied_review(root, monkeypatch):
    app = _app_con_archivo(root)
    app._applied_review = "C:/rev/revision.xlsx"
    monkeypatch.setattr(app, "_start_thread", lambda *a, **k: None)

    app._on_process_click()

    assert app._applied_review is None


def test_cancel_during_processing_never_opens_the_save_dialog(root, monkeypatch):
    import gui.app as app_module

    app = App(root)
    dialogos = []
    monkeypatch.setattr(app_module.filedialog, "asksaveasfilename", lambda **k: dialogos.append(1) or "")
    app._set_busy(True, cancellable=True)

    app._dispatch(("stage", "Estandarizando parámetros..."))
    app._dispatch(("cancelled",))                                                          # RF-55

    assert dialogos == []
    assert app.process_result is None
    assert not app.save_button.grid_info()
