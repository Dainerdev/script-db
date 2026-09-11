import traceback
from datetime import datetime
from pathlib import Path

GENERIC_MESSAGE = "Ocurrió un problema inesperado al procesar el archivo."


def handle_unexpected_error(exc: BaseException, logs_dir: Path | str = "logs") -> tuple[str, str | None]:
    """
    RF-12: arma el mensaje genérico (nunca un traceback en pantalla) e
    intenta escribir el detalle técnico completo en
    `logs_dir/error_<AAAAMMDD_HHMMSS>.txt` (formato de fecha: Decisión
    técnica #5 del plan). Si la escritura del log también falla (ej. sin
    permisos), retorna el mensaje genérico + None en vez de propagar un
    segundo error.
    """
    logs_dir = Path(logs_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"error_{timestamp}.txt"

    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            encoding="utf-8",
        )
        return GENERIC_MESSAGE, str(log_path)
    except OSError:
        return GENERIC_MESSAGE, None
