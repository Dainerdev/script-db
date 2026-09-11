# Módulo Pandas (`src/`)

Núcleo de procesamiento del proyecto, ya desarrollado, probado y en
producción vía `main.py`. Construido sobre Pandas + openpyxl/xlsxwriter.
Cuatro submódulos:

- `reading.py` — lectura del [[Base de datos Excel|Excel fuente]].
- `standardization.py` — [[Estandarización]] y [[Limpieza|limpieza]].
- `diagnostic.py` — diagnóstico, similitud y [[Separación de
  registros|separación]].
- `exportation.py` — exportación multi-hoja replicando estilo original.

**Frontera importante:** dentro del alcance SDD de la [[GUI]], este
módulo es una dependencia resuelta que la GUI invoca; no reimplementa su
lógica. Tras la revisión de QA de la spec, se aprobó una **excepción
acotada y documentada** (constitución, principio 3): la GUI puede
agregar cambios ADITIVOS a `src/` (parámetros opcionales con el mismo
comportamiento por defecto, o guardas `if col in df.columns` donde hoy
falten), nunca cambios de comportamiento. Detalle completo en
`specs/001-gui-limpieza-excel/plan.md`, sección "Cambios aditivos en
`src/`" (pendiente de implementar en la tarea T3 de `tasks.md`).

**Cambios aditivos planeados (aún no implementados):** guardas de
columnas ausentes en `split_multiple_comparecientes`, `split_by_status` y
`add_radicado_ius_revisada`; `read_excel_file(..., raise_errors=False)`
para propagar la causa exacta de un fallo de lectura; y
`run_similarity_report` retornando sus conteos en vez de solo
imprimirlos.

## Relacionado
- [[Base de datos Excel]]
- [[Estandarización]]
- [[Limpieza]]
- [[Separación de registros]]
- [[GUI]]
