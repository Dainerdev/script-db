# AGENTS.md — script-db

## Proyecto
Herramienta para la Procuraduría/JEP que limpia, estandariza y separa en
hojas los registros de una base de datos de reparto almacenada en Excel
(~185k filas). El núcleo de procesamiento (`src/`) ya está desarrollado,
probado y en producción vía `main.py`. El trabajo activo de SDD en
`specs/` cubre EXCLUSIVAMENTE una GUI de escritorio para que funcionarios
sin conocimientos de programación ejecuten ese núcleo sin usar la terminal.

## Módulo existente: `src/` (dependencia resuelta, no se re-especifica aquí)
- `src/reading.py` — `read_excel_file`, `excel_general_information`: lectura
  del Excel fuente (hoja "Reparto", engine `calamine`).
- `src/diagnostic.py` — `run_diagnostics`, `check_duplicates`,
  `check_duplicate_names_by_id`, `check_fuzzy_duplicate_names`,
  `run_similarity_report`, `split_by_status`, `extract_multi_ius`:
  diagnóstico de calidad de datos y separación en
  Activos/Archivados/Retirados/SIM/Múltiples IUS.
- `src/standardization.py` — `clean_and_standardize`,
  `split_multiple_comparecientes`, `standardize_column_spacing`,
  `standardize_column_names`, `standardize_column_dates`,
  `standardize_reparto_column`, `add_radicado_ius_revisada`: limpieza y
  normalización de texto, fechas y nombres.
- `src/exportation.py` — `export_multi_sheet_excel`, `export_excel`:
  exportación a Excel multi-hoja replicando el estilo del archivo original.
- `main.py` orquesta el pipeline completo: lectura → diagnóstico →
  limpieza → reporte de similitud → separación → exportación.

**Regla:** la GUI es una capa fina que INVOCA estas funciones tal como
están. Ningún cambio de comportamiento en `src/` se hace dentro del
alcance de la spec de GUI — eso requeriría su propia spec.

## Comandos
- Ejecutar pipeline actual (sin GUI): `python main.py`
- Ejecutar GUI (desarrollo): `python run_gui.py`
- Empaquetar GUI a `.exe`: `pyinstaller --onefile --windowed --name LimpiezaJEP --icon=assets/icon.ico run_gui.py`
- Tests: `pytest -q` (aún no hay suite; se crea con la primera tarea de GUI
  que la requiera, ver `specs/001-gui-limpieza-excel/tasks.md`)

## Estilo y convenciones
- Python 3, Pandas. Identificadores de código en inglés; mensajes al
  usuario, docstrings y comentarios en español (convención ya usada en
  `src/`).
- GUI: Tkinter (stdlib), sin frameworks web. Empaquetado final a `.exe`
  con PyInstaller (ver `specs/001-gui-limpieza-excel/plan.md`).

## Reglas
- Lee `docs/constitution.md` y la spec activa en `specs/` antes de tocar
  código de la GUI.
- En `src/`, solo se permiten los cambios ADITIVOS documentados en
  `docs/constitution.md` (principio 3) y en
  `specs/001-gui-limpieza-excel/plan.md` (sección "Cambios aditivos en
  `src/`"). No modifiques `main.py`. Cualquier otro cambio a `src/`
  requiere autorización explícita fuera de este flujo SDD.
- No modifiques archivos dentro de `specs/` salvo petición explícita.
- Cada vez que redactes o modifiques un `spec.md` o `plan.md`, actualiza
  incrementalmente las notas y enlaces afectados en `grafo-conocimiento/`
  (nunca lo reescribas desde cero — ver `grafo-conocimiento/Indice.md`).

## Al terminar cualquier tarea
- Ejecuta `pytest -q` y confirma en tu respuesta que todo pasa.
