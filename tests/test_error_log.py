import re
from pathlib import Path

from gui.error_log import handle_unexpected_error, GENERIC_MESSAGE


def _boom():
    raise ValueError("algo salio mal")


def test_creates_log_with_full_traceback(tmp_path):
    logs_dir = tmp_path / "logs"
    try:
        _boom()
    except ValueError as exc:
        mensaje, ruta = handle_unexpected_error(exc, logs_dir=logs_dir)

    assert mensaje == GENERIC_MESSAGE
    assert ruta is not None
    contenido = Path(ruta).read_text(encoding="utf-8")
    assert "ValueError" in contenido
    assert "algo salio mal" in contenido


def test_creates_logs_dir_if_missing(tmp_path):
    logs_dir = tmp_path / "no_existe_todavia"
    assert not logs_dir.exists()

    try:
        _boom()
    except ValueError as exc:
        _, ruta = handle_unexpected_error(exc, logs_dir=logs_dir)

    assert logs_dir.exists()
    assert Path(ruta).exists()


def test_log_filename_matches_expected_format(tmp_path):
    logs_dir = tmp_path / "logs"
    try:
        _boom()
    except ValueError as exc:
        _, ruta = handle_unexpected_error(exc, logs_dir=logs_dir)

    assert re.match(r"error_\d{8}_\d{6}\.txt$", Path(ruta).name)


def test_returns_none_path_when_log_write_fails(tmp_path):
    # logs_dir apunta a un ARCHIVO existente, no a una carpeta -> falla el mkdir.
    bloqueada = tmp_path / "logs_bloqueada"
    bloqueada.write_text("soy un archivo, no una carpeta")

    try:
        _boom()
    except ValueError as exc:
        mensaje, ruta = handle_unexpected_error(exc, logs_dir=bloqueada)

    assert mensaje == GENERIC_MESSAGE
    assert ruta is None
