import pandas as pd

from gui.state import ValidationResult
from src.parameters import canonical_column
from src.text_keys import COLUMN_TYPES

# Columnas que el proceso espera (RF-3 de specs/001-gui-limpieza-excel/spec.md),
# más las estandarizadas de la spec 002 que no estaban (RF-53).
_SPEC_001_COLUMNS = [
    "RADICADO IUS",
    "NOMBRES_APELLIDOS",
    "IDENTIFICACIÓN",
    "FECHA",
    "REPARTO",
    "CLASIFICACIÓN DEL RADICADO",
    "FUNCIONARIO A CARGO",
    "MAGISTRADO",
    "No",
]
EXPECTED_COLUMNS = _SPEC_001_COLUMNS + [col for col in COLUMN_TYPES if col not in _SPEC_001_COLUMNS]

# Qué parte del proceso se omite si falta cada columna, en línea con las
# guardas agregadas a src/ en T3 (specs/001-gui-limpieza-excel/plan.md) y
# con RF-53 de la spec 002 (se omite solo la estandarización de esa columna).
OMITTED_STEPS_BY_COLUMN = {
    "RADICADO IUS": "no se agregará 'Radicado IUS Revisada' ni se detectarán radicados IUS duplicados o personas con múltiples IUS",
    "NOMBRES_APELLIDOS": "no se separarán comparecientes ni se estandarizarán los nombres, ni se detectarán nombres similares (fuzzy) o personas con múltiples IUS",
    "IDENTIFICACIÓN": "no se estandarizará la identificación, la separación de comparecientes no se podrá confirmar con las cédulas (quedará SEPARADA SIN CONFIRMAR) y no se detectarán cédulas con variantes de nombre",
    "FECHA": "no se estandarizará el formato de la columna FECHA",
    "REPARTO": "no se estandarizará el formato de la columna REPARTO",
    "CLASIFICACIÓN DEL RADICADO": "no se podrá separar el archivo en Activos/Archivados/Retirados/SIM; todo quedará en Activos",
    "FUNCIONARIO A CARGO": "no se podrán distinguir los Funcionarios Retirados dentro de los archivados, ni se estandarizará la columna FUNCIONARIO A CARGO",
    "MAGISTRADO": "no se estandarizará la columna MAGISTRADO",
    "No": "no se podrán contar los radicados IUS duplicados",
}
OMITTED_STEPS_BY_COLUMN.update({col: f"no se estandarizará la columna {col}"
                                for col in COLUMN_TYPES if col not in OMITTED_STEPS_BY_COLUMN})


def validate(df: pd.DataFrame | None) -> ValidationResult:
    """
    RF-2/RF-3: valida que la hoja tenga datos reconocibles y que estén
    las columnas que el proceso espera. No lee el archivo — eso es
    responsabilidad de gui/controller.py, que traduce la causa específica
    de un fallo de lectura vía read_excel_file(..., raise_errors=True).
    TIPO DE EXPEDIENTE se reconoce aunque el encabezado traiga texto extra
    (RF-54 de la spec 002), igual que al estandarizar.
    """
    if df is None or len(df.columns) == 0:
        return ValidationResult(sheet_ok=False, missing_columns=[], can_continue=False)

    present = set(df.columns) | {canonical_column(col) for col in df.columns}
    missing = [col for col in EXPECTED_COLUMNS if col not in present]
    return ValidationResult(sheet_ok=True, missing_columns=missing, can_continue=True)


def describe_missing(missing_columns: list[str]) -> list[str]:
    """Traduce cada columna faltante a una frase en español de qué se
    omite, para el mensaje de advertencia de RF-3 (y RF-53 de la spec 002)."""
    return [OMITTED_STEPS_BY_COLUMN[col] for col in missing_columns if col in OMITTED_STEPS_BY_COLUMN]
