import pandas as pd

from gui.state import ValidationResult

# Columnas que el proceso espera (RF-3 de specs/001-gui-limpieza-excel/spec.md).
EXPECTED_COLUMNS = [
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

# Qué parte del proceso se omite si falta cada columna, en línea con las
# guardas agregadas a src/ en T3 (specs/001-gui-limpieza-excel/plan.md).
OMITTED_STEPS_BY_COLUMN = {
    "RADICADO IUS": "no se agregará 'Radicado IUS Revisada' ni se detectarán radicados IUS duplicados o personas con múltiples IUS",
    "NOMBRES_APELLIDOS": "no se desdoblarán comparecientes múltiples por celda, ni se detectarán nombres similares (fuzzy) o personas con múltiples IUS",
    "IDENTIFICACIÓN": "no se desdoblarán comparecientes múltiples por celda, ni se detectarán cédulas con variantes de nombre",
    "FECHA": "no se estandarizará el formato de la columna FECHA",
    "REPARTO": "no se estandarizará el formato de la columna REPARTO",
    "CLASIFICACIÓN DEL RADICADO": "no se podrá separar el archivo en Activos/Archivados/Retirados/SIM; todo quedará en Activos",
    "FUNCIONARIO A CARGO": "no se podrán distinguir los Funcionarios Retirados dentro de los archivados",
    "MAGISTRADO": "no se aplicará formato de nombre propio a la columna MAGISTRADO",
    "No": "no se podrán contar los radicados IUS duplicados",
}


def validate(df: pd.DataFrame | None) -> ValidationResult:
    """
    RF-2/RF-3: valida que la hoja tenga datos reconocibles y que estén
    las columnas que el proceso espera. No lee el archivo — eso es
    responsabilidad de gui/controller.py, que traduce la causa específica
    de un fallo de lectura vía read_excel_file(..., raise_errors=True).
    """
    if df is None or len(df.columns) == 0:
        return ValidationResult(sheet_ok=False, missing_columns=[], can_continue=False)

    missing = [col for col in EXPECTED_COLUMNS if col not in df.columns]
    return ValidationResult(sheet_ok=True, missing_columns=missing, can_continue=True)


def describe_missing(missing_columns: list[str]) -> list[str]:
    """Traduce cada columna faltante a una frase en español de qué se
    omite, para el mensaje de advertencia de RF-3."""
    return [OMITTED_STEPS_BY_COLUMN[col] for col in missing_columns if col in OMITTED_STEPS_BY_COLUMN]
