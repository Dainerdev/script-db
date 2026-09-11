import tkinter as tk

import pytest

from gui.app import App


@pytest.fixture
def root():
    r = tk.Tk()
    r.withdraw()
    yield r
    r.destroy()


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


def test_set_busy_false_stops_any_active_crawl(root):
    app = App(root)
    app._start_progress_crawl(0.0, 1.0)
    assert app._crawl_active is True

    app._set_busy(False)

    assert app._crawl_active is False


def test_handle_cancelled_reshows_save_button_if_result_pending():
    import tkinter as tk
    from gui.state import ProcessResult
    import pandas as pd

    r = tk.Tk()
    r.withdraw()
    try:
        app = App(r)
        app.process_result = ProcessResult(sheets={"A": pd.DataFrame()}, counts={"A": 0}, source_path="x.xlsx")
        app._handle_cancelled()
        assert app.save_button.grid_info()
    finally:
        r.destroy()


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
