"""
Fixtures compartidas por los tests de la GUI, y un ajuste de Tcl en Windows.

Por qué el ajuste: en Windows, Tcl crea sus canales stdin/stdout/stderr una
sola vez por hilo, con los handles que devuelve GetStdHandle en ese momento,
y los deja en su lista de archivos abiertos (win/tclWinChan.c). La captura
por defecto de pytest (--capture=fd) hace os.dup2 sobre los fd 0/1/2 en cada
fase de cada test, lo que cierra esos handles, y Windows reusa sus valores
en los siguientes archivos que se abren. Si Tcl abre uno de sus scripts
(init.tcl, tclIndex, tk.tcl...) y le toca un valor reusado, lo confunde con
el canal estándar viejo:
  - con stdout/stderr el open falla sin motivo: "couldn't read file ...:
    no such file or directory" / "No error", o, si era tclIndex,
    'invalid command name "tcl_findLibrary"' al crear tk.Tk();
  - con stdin, `source` termina en Tcl_Panic y muere el proceso de pytest.

Solución, solo en los tests (gui/ no cambia):
  1. pytest_configure crea el primer intérprete Tcl del proceso con los
     handles estándar en NULL: Tcl no crea canales estándar en este hilo y
     ya no guarda ningún handle que pytest vaya a cerrar.
  2. Un solo tk.Tk() por sesión y un tk.Toplevel propio por test: cada
     tk.Tk() abre decenas de scripts de Tcl/Tk, así que uno por test era
     mucho más lento y multiplicaba las aperturas expuestas.

(Escrito en el worktree focused-swartz-8bc1b5 el 2026-09-25 y nunca
integrado; se trajo a la rama de la spec 002 en la T17, 2026-10-18, al
seguir viendo el error intermitente.)
"""
import sys
import tkinter as tk

import pytest

# STD_INPUT_HANDLE, STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
_STD_HANDLE_IDS = (-10, -11, -12)


def pytest_configure(config):
    if sys.platform == "win32":
        _init_tcl_without_std_channels()


def _init_tcl_without_std_channels():
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetStdHandle.argtypes = [ctypes.c_int]
    kernel32.GetStdHandle.restype = ctypes.c_void_p
    kernel32.SetStdHandle.argtypes = [ctypes.c_int, ctypes.c_void_p]

    saved = [kernel32.GetStdHandle(std_id) for std_id in _STD_HANDLE_IDS]
    for std_id in _STD_HANDLE_IDS:
        kernel32.SetStdHandle(std_id, None)
    try:
        # Tcl busca sus canales estándar la primera vez que un intérprete los
        # necesita (aquí, `chan names`) y no lo vuelve a intentar en este hilo.
        tk.Tcl().eval("chan names")
    finally:
        for std_id, handle in zip(_STD_HANDLE_IDS, saved):
            kernel32.SetStdHandle(std_id, handle)


@pytest.fixture(scope="session")
def tk_root():
    """Único intérprete Tk de la sesión, oculto. Los tests piden `root`."""
    shared = tk.Tk()
    shared.withdraw()
    yield shared
    shared.destroy()


@pytest.fixture
def root(tk_root):
    """Ventana propia de cada test (tk.Toplevel oculto) para pasarle a App."""
    window = tk.Toplevel(tk_root)
    window.withdraw()
    yield window
    # App deja programados _poll_queue y _tick_crawl con after(): se cancelan
    # para que el siguiente test no herede temporizadores en el intérprete.
    for timer in tk_root.tk.splitlist(tk_root.tk.call("after", "info")):
        tk_root.tk.call("after", "cancel", timer)
    window.destroy()
