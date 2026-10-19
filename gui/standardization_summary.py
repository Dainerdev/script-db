"""
Resumen de la estandarización que se muestra en la ventana al terminar de
procesar (spec 002: RF-43, RF-48, RF-53, RF-76, RF-77, RF-92, RF-95). Es la
versión corta del Resumen del Excel de revisión: mismos números, en texto.
Función pura (sin Tk) para poder probarla sin abrir ventanas.
"""
from src.parameters import AUTOMATIC, DECIDED, OBSERVATION, REVIEW, SUMMARY_UNCHANGED, TO_CONFIRM

# Orden en que se muestran los estados de cada columna.
_STATE_ORDER = [SUMMARY_UNCHANGED, AUTOMATIC, DECIDED, TO_CONFIRM, REVIEW]
_SEPARATION_LABELS = [("SEPARADA", "SEPARADA"), ("SEPARADA SIN CONFIRMAR", "SEPARADA SIN CONFIRMAR"),
                      ("SIN SEPARAR", "SIN SEPARAR"), ("", "no necesitaban separarse")]
MAX_PROBLEMS = 10       # decisiones no aplicadas que se listan; el resto está en el Excel


def _values(n: int) -> str:
    return f"{n:,} {'valor' if n == 1 else 'valores'}"


def _rows(n: int) -> str:
    return f"{n:,} {'fila' if n == 1 else 'filas'}"


def pending_phrase(values: int, rows: int) -> str:
    """ "Pendientes de revisión: 1 valor en 1 fila." / "…: 8,742 valores en 35,117 filas." (RF-50)."""
    return f"Pendientes de revisión: {_values(values)} en {_rows(rows)}."


def _states_line(column, states) -> str:
    """El primer estado lleva las unidades ("3 valores / 1,200 filas"); los demás, solo los números."""
    ordered = sorted(states.items(), key=lambda item: _STATE_ORDER.index(item[0])
                     if item[0] in _STATE_ORDER else len(_STATE_ORDER))
    parts = [f"{state} {_values(values)} / {_rows(rows)}" if i == 0 else f"{state} {values:,} / {rows:,}"
             for i, (state, (values, rows)) in enumerate(ordered)]
    return f"  {column}: " + " · ".join(parts)


def format_standardization(result) -> str:
    """Texto del resumen para un ProcessResult; vacío si no trae estandarización."""
    review = result.review
    if review is None:
        return ""
    lines = ["RESUMEN DE LA ESTANDARIZACIÓN"]
    if result.pending_values:
        lines.append(pending_phrase(result.pending_values, result.pending_rows)
                     + " Están pintados en el resultado y listados en el Excel de revisión.")
    else:
        lines.append("No quedaron valores pendientes de revisión.")

    lines.append("")
    lines.append("Estados por columna (valores / filas):")                                    # RF-43
    others = []
    for column, info in review.summary.items():
        lines.append(_states_line(column, info["estados"]))
        other_values, other_rows = info.get("otra categoría", (0, 0))
        if other_rows:
            others.append(f"{column} {_values(other_values)} / {_rows(other_rows)}")
    if others:
        lines.append("  De otra categoría: " + "; ".join(others))

    if review.totals:                                                                         # RF-92
        total = sum(next(iter(review.totals.values())).values())
        lines.append(f"Verificación de totales: cada una de las {len(review.totals)} columnas suma {total:,} filas.")
    if review.separation is not None:                                                          # RF-95
        parts = [f"{review.separation.get(status, 0):,} {label}" for status, label in _SEPARATION_LABELS]
        lines.append("Separación de comparecientes: " + " · ".join(parts)
                     + f"; el resultado tiene {review.separation.get('filas', 0):,} filas.")

    if review.decisions is not None or review.unmatched_decisions:                            # RF-77
        lines.append(f"Decisiones cargadas que no coincidieron con ningún valor: {review.unmatched_decisions:,}.")
    if review.invalid_decisions:                                                               # RF-48
        lines.append(f"Decisiones no aplicadas ({len(review.invalid_decisions)}):")
        lines.extend(f"  - {problem}" for problem in review.invalid_decisions[:MAX_PROBLEMS])
        rest = len(review.invalid_decisions) - MAX_PROBLEMS
        if rest > 0:
            lines.append(f"  y {rest} más (ver el Resumen del Excel de revisión).")
    if result.missing_columns:                                                                 # RF-53
        lines.append("Columnas estandarizadas que faltan en el archivo (se omitió solo su estandarización): "
                     + ", ".join(result.missing_columns) + ".")

    lines.append("")
    lines.append(f"Cómo leer el resultado: el relleno de color marca cada celda pendiente; la columna "        # RF-76
                 f"«{OBSERVATION}» dice por qué (pendiente de revisión, no es una persona, hay más "
                 "comparecientes sin nombrar).")
    return "\n".join(lines)
