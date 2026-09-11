import queue
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from src.exportation import export_multi_sheet_excel, ExportCancelled

from gui import controller
from gui.error_log import handle_unexpected_error
from gui.validation import describe_missing

WINDOW_TITLE = "Limpieza de base de datos - Procuraduría/JEP"
POLL_INTERVAL_MS = 100


class App:
    """
    Ventana Tkinter (RF-1 a RF-13 de specs/001-gui-limpieza-excel/spec.md).
    El trabajo pesado (leer, procesar, exportar) corre en threading.Thread
    y se comunica con esta clase por medio de self.queue — nunca toca
    widgets desde otro hilo. self.queue se sondea con root.after (RF-6/RF-7).
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        # Ventana fija demasiado chica recortaba el resumen final (varias
        # líneas: ruta + 5 hojas) — ver captura de la Dra. Mauren.
        self.root.geometry("820x480")
        self.root.minsize(760, 440)

        self.queue: queue.Queue = queue.Queue()
        self.selected_path: str | None = None
        self.df = None
        self.source_path: str | None = None
        self.process_result = None
        self.busy = False
        self.saved = True  # False si hay un ProcessResult sin guardar (RF-13)
        self.cancel_requested = False
        self._crawl_active = False
        self._crawl_value = 0.0
        self._crawl_target = 0.0

        self._build_widgets()
        self._poll_queue()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_widgets(self):
        self._set_window_icon()

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        frame = ttk.Frame(self.root, padding=12)
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)

        WRAP = 720

        self.select_button = ttk.Button(frame, text="Seleccionar archivo", command=self._on_select_file)
        self.select_button.grid(row=0, column=0, sticky="w")

        self.path_label = ttk.Label(frame, text="Ningún archivo seleccionado.", wraplength=WRAP)
        self.path_label.grid(row=0, column=1, sticky="w", padx=8)

        self.diagnostic_label = ttk.Label(frame, justify="left", text="", wraplength=WRAP)
        self.diagnostic_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        botones_frame = ttk.Frame(frame)
        botones_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.process_button = ttk.Button(botones_frame, text="Procesar", command=self._on_process_click, state="disabled")
        self.process_button.grid(row=0, column=0)

        self.save_button = ttk.Button(botones_frame, text="Guardar resultado...", command=self._on_save_click)
        self.save_button.grid(row=0, column=1, padx=(8, 0))
        self.save_button.grid_remove()

        self.cancel_button = ttk.Button(botones_frame, text="Cancelar", command=self._on_cancel_click)
        self.cancel_button.grid(row=0, column=2, padx=(8, 0))
        self.cancel_button.grid_remove()

        self.stage_label = ttk.Label(frame, text="", wraplength=WRAP)
        self.stage_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.progress_bar = ttk.Progressbar(frame, orient="horizontal", length=WRAP, mode="determinate", maximum=1.0)
        self.progress_bar.grid(row=4, column=0, columnspan=2, sticky="we")

        self.summary_label = ttk.Label(frame, justify="left", text="", wraplength=WRAP)
        self.summary_label.grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _set_window_icon(self):
        # Si assets/icon.ico no existe todavía, la ventana se ve con el
        # ícono por defecto de Tk sin romper nada (no es un error).
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
        if icon_path.exists():
            try:
                self.root.iconbitmap(str(icon_path))
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # RF-1/RF-2/RF-3/RF-4: selección, lectura, validación, diagnóstico
    # ------------------------------------------------------------------

    def _on_select_file(self):
        path = filedialog.askopenfilename(
            title="Seleccionar Excel de reparto",
            filetypes=[("Archivos de Excel", "*.xlsx *.xls")],
        )
        if not path:
            return

        if self.process_result is not None and not self.saved:
            if not messagebox.askyesno(
                "Resultado sin guardar",
                "Tienes un resultado procesado que no has guardado. "
                "¿Deseas descartarlo y seleccionar un archivo nuevo?",
            ):
                return

        self._reset_state()
        self.selected_path = path
        self.path_label.config(text=path)
        self._set_busy(True)
        self._start_thread(controller.read_and_validate, path, self.queue.put)

    def _reset_state(self):
        self.df = None
        self.source_path = None
        self.process_result = None
        self.saved = True
        self.diagnostic_label.config(text="")
        self.summary_label.config(text="")
        self.process_button.config(state="disabled")
        self.save_button.grid_remove()

    def _handle_diagnostic(self, validation, diagnostic, df):
        self.diagnostic_label.config(text=self._format_diagnostic(diagnostic))

        if validation.missing_columns:
            detalle = "\n".join(f"- {d}" for d in describe_missing(validation.missing_columns))
            continuar = messagebox.askyesno(
                "Faltan columnas esperadas",
                "Al archivo le faltan estas columnas:\n"
                + ", ".join(validation.missing_columns)
                + "\n\nSi continúas:\n"
                + detalle
                + "\n\n¿Deseas continuar de todas formas?",
            )
            if not continuar:
                self._reset_state()
                self.path_label.config(text="Ningún archivo seleccionado.")
                return

        self.df = df
        self.source_path = self.selected_path
        self.process_button.config(state="normal")

    @staticmethod
    def _format_diagnostic(diagnostic) -> str:
        return (
            f"Diagnóstico: {diagnostic.total_rows:,} filas totales, "
            f"{diagnostic.rows_with_extra_spaces:,} con espacios sobrantes, "
            f"{diagnostic.duplicated_rows:,} filas duplicadas, "
            f"{diagnostic.ids_with_name_variants:,} cédulas con variantes de nombre, "
            f"{diagnostic.duplicated_ius:,} radicados IUS duplicados, "
            f"{diagnostic.fuzzy_similar_names:,} nombres similares."
        )

    # ------------------------------------------------------------------
    # RF-5/RF-6/RF-7: procesamiento
    # ------------------------------------------------------------------

    def _on_process_click(self):
        self._set_busy(True, cancellable=True)
        self._start_thread(
            controller.process, self.df, self.source_path, self.queue.put,
            lambda: self.cancel_requested,
        )

    def _handle_process_done(self, process_result):
        self.process_result = process_result
        self.saved = False
        self._prompt_save()

    # ------------------------------------------------------------------
    # RF-8/RF-9/RF-10/RF-11: guardado y resumen final
    # ------------------------------------------------------------------

    def _on_save_click(self):
        self._prompt_save()

    def _prompt_save(self):
        sugerido = self._suggested_output_name(self.source_path)
        output_path = filedialog.asksaveasfilename(
            title="Guardar resultado como",
            initialfile=sugerido,
            defaultextension=".xlsx",
            filetypes=[("Archivos de Excel", "*.xlsx")],
        )
        if not output_path:
            self.save_button.grid()
            self._set_busy(False)
            return

        if Path(output_path).resolve() == Path(self.source_path).resolve():
            if not messagebox.askyesno(
                "Vas a reemplazar tu archivo original",
                "La ruta elegida es la misma del archivo de entrada. "
                "¿Seguro que quieres reemplazarlo?",
            ):
                self.save_button.grid()
                self._set_busy(False)
                return

        self.save_button.grid_remove()
        self._set_busy(True, cancellable=True)
        self._start_thread(self._run_export, self.process_result, output_path)

    @staticmethod
    def _suggested_output_name(source_path: str) -> str:
        # Decisión técnica #5 del plan: AAAAMMDD_HHMMSS, ordenable y válido en Windows.
        marca = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = Path(source_path).stem
        return f"{base}_resultado_{marca}.xlsx"

    def _run_export(self, process_result, output_path):
        # Método (no función libre): ya tiene self.queue, no necesita
        # recibir on_event como los de gui/controller.py.
        total_filas = sum(process_result.counts.values()) or 1
        filas_hechas = 0

        def on_sheet_start(sheet_name, indice, total):
            # Escribir una hoja no tiene puntos de avance intermedios (una
            # sola llamada bloqueante de xlsxwriter) — sin esto la barra se
            # ve congelada mientras escribe Reparto_Activo (la más grande).
            # "progress_crawl" hace que la GUI la anime sola hacia el
            # siguiente punto real mientras espera (Decisión #12 del plan).
            objetivo = (filas_hechas + process_result.counts.get(sheet_name, 0)) / total_filas
            self.queue.put(("stage", f"Exportando resultados... ({indice}/{total}: {sheet_name})"))
            self.queue.put(("progress_crawl", filas_hechas / total_filas, objetivo))

        def on_sheet_done(sheet_name, indice, total):
            nonlocal filas_hechas
            filas_hechas += process_result.counts.get(sheet_name, 0)
            self.queue.put(("progress", filas_hechas / total_filas))

        try:
            self.queue.put(("stage", "Exportando resultados..."))
            self.queue.put(("progress", 0.0))
            export_multi_sheet_excel(
                sheets=process_result.sheets,
                file_path=output_path,
                style_reference_path=process_result.source_path,
                style_reference_sheet="Reparto",
                raise_errors=True,
                on_sheet_start=on_sheet_start,
                on_sheet_done=on_sheet_done,
                should_cancel=lambda: self.cancel_requested,
            )
            self.queue.put(("export_done", output_path))
        except ExportCancelled:
            Path(output_path).unlink(missing_ok=True)  # no dejar un .xlsx a medio escribir
            self.queue.put(("cancelled",))
        except Exception as exc:
            mensaje, log_path = handle_unexpected_error(exc)
            self.queue.put(("export_error", mensaje, log_path))

    def _handle_export_done(self, output_path):
        self.saved = True
        counts = self.process_result.counts
        resumen = "\n".join(f"- {hoja}: {cantidad:,} registros" for hoja, cantidad in counts.items())
        self.summary_label.config(text=f"Guardado en: {output_path}\n{resumen}")
        messagebox.showinfo("Proceso terminado", f"Archivo guardado en:\n{output_path}")
        self.save_button.grid()

    # ------------------------------------------------------------------
    # RF-12: errores no previstos (comparten manejo en process y en export)
    # ------------------------------------------------------------------

    def _handle_error(self, mensaje, log_path):
        if log_path:
            texto = f"{mensaje}\n\nDetalle técnico guardado en:\n{log_path}"
        else:
            texto = f"{mensaje}\n\nNo fue posible generar un registro técnico; contacta a soporte con la hora exacta del error."
        messagebox.showerror("Ocurrió un error", texto)

    def _handle_read_error(self, mensaje):
        messagebox.showerror("No se pudo leer el archivo", mensaje)
        self._reset_state()
        self.path_label.config(text="Ningún archivo seleccionado.")

    # ------------------------------------------------------------------
    # Hilos y cola de eventos (RF-6/RF-7)
    # ------------------------------------------------------------------

    def _start_thread(self, target, *args):
        thread = threading.Thread(target=target, args=args, daemon=True)
        thread.start()

    CRAWL_TICK_MS = 120
    CRAWL_STEPS_TO_CAP = 55   # ~6.6s (55 * 120ms) para llegar al tope del tramo
    CRAWL_CAP_FRACTION = 0.92  # nunca llega sola al 100% del tramo

    def _start_progress_crawl(self, start: float, target: float):
        # Decisión técnica #12 del plan: sin puntos de avance reales
        # dentro de una hoja, se anima la barra acercándose al siguiente
        # punto conocido (nunca lo alcanza sola) para que nunca se vea
        # congelada mientras escribe una hoja grande. Paso LINEAL fijo
        # (no un porcentaje de lo restante) para que el movimiento se
        # note parejo de principio a fin, en vez de volverse imperceptible
        # cerca del tope como pasaba con la versión anterior (decaimiento
        # proporcional — daba la sensación de quedarse quieta otra vez).
        self._crawl_value = start
        self._crawl_target = start + (target - start) * self.CRAWL_CAP_FRACTION
        self._crawl_step = (self._crawl_target - start) / self.CRAWL_STEPS_TO_CAP
        self._crawl_active = True
        self._tick_crawl()

    def _tick_crawl(self):
        if not self._crawl_active:
            return
        if self._crawl_value < self._crawl_target:
            self._crawl_value = min(self._crawl_value + self._crawl_step, self._crawl_target)
            self.progress_bar["value"] = self._crawl_value
        self.root.after(self.CRAWL_TICK_MS, self._tick_crawl)

    def _stop_progress_crawl(self, final_value: float):
        self._crawl_active = False
        self.progress_bar["value"] = final_value

    def _on_cancel_click(self):
        self.cancel_requested = True
        self.cancel_button.config(state="disabled")
        self.stage_label.config(text="Cancelando... (se detiene en el próximo punto seguro)")

    def _handle_cancelled(self):
        self.stage_label.config(text="Proceso cancelado por el usuario.")
        self.progress_bar["value"] = 0
        if self.process_result is not None:
            self.save_button.grid()  # reintentar guardar (RF-10) sin reprocesar

    def _set_busy(self, busy: bool, cancellable: bool = False):
        # cancellable=True solo en "Procesar" y en la exportación que le
        # sigue automáticamente (RF-8) — cancelar la simple lectura del
        # archivo no aporta nada (ya es rápida) y solo confundiría.
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.select_button.config(state=state)
        self.process_button.config(state="disabled" if busy or self.df is None else "normal")
        if busy and cancellable:
            self.cancel_requested = False
            self.cancel_button.grid()
            self.cancel_button.config(state="normal")
        else:
            self.cancel_button.grid_remove()
        if not busy:
            self._crawl_active = False  # nunca dejar el ticker corriendo de más
            self.stage_label.config(text="")

    def _poll_queue(self):
        try:
            while True:
                event = self.queue.get_nowait()
                self._dispatch(event)
        except queue.Empty:
            pass
        self.root.after(POLL_INTERVAL_MS, self._poll_queue)

    def _dispatch(self, event):
        tag = event[0]
        if tag == "stage":
            self.stage_label.config(text=event[1])
        elif tag == "progress":
            self._stop_progress_crawl(event[1])
        elif tag == "progress_crawl":
            self._start_progress_crawl(event[1], event[2])
        elif tag == "read_error":
            self._set_busy(False)
            self._handle_read_error(event[1])
        elif tag == "diagnostic":
            self._set_busy(False)
            self._handle_diagnostic(event[1], event[2], event[3])
        elif tag == "done":
            self._set_busy(False)
            self._handle_process_done(event[1])
        elif tag == "error":
            self._set_busy(False)
            self._handle_error(event[1], event[2])
        elif tag == "export_done":
            self._set_busy(False)
            self._handle_export_done(event[1])
        elif tag == "export_error":
            self._set_busy(False)
            self._handle_error(event[1], event[2])
        elif tag == "cancelled":
            self._set_busy(False)
            self._handle_cancelled()

    # ------------------------------------------------------------------
    # Cierre
    # ------------------------------------------------------------------

    def _on_close(self):
        if self.busy or (self.process_result is not None and not self.saved):
            if not messagebox.askyesno(
                "¿Salir?",
                "Hay un procesamiento en curso o un resultado sin guardar. "
                "¿Seguro que quieres salir?",
            ):
                return
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
