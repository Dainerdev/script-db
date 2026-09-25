# Separación de registros

Última etapa del pipeline: tras la [[Limpieza|limpieza]], cada
[[Registro|registro]] se clasifica en una de las hojas de salida del
Excel de resultados:

- **Reparto_Activo** — el resto, base activa limpia.
- **Archivados** — "ARCHIVADO" en la clasificación **o** en el
  funcionario a cargo (ej. "ARCHIVADO - DEVOLUCIÓN - NO MISIONAL"), y no
  es de retirados.
- **Funcionarios_Retirados** — funcionario a cargo contiene "RETIRADOS",
  esté o no archivado en la clasificación.

Regla vigente desde el arreglo de Dainer en `master` (`032d6c9`,
2026-09-15), integrada en `Jose_Blanco` el 2026-09-25. Antes, Retirados
exigía también "ARCHIVADO" en la clasificación: sobre el corte del 5 de
agosto dejaba 8.266 filas de "PROCESOS ARCHIVADOS POR FUNCIONARIOS
RETIRADOS" (clasificación OVAC/DOKUS antecedente) en Activos, y 242 con
"ARCHIVADO - DEVOLUCIÓN - NO MISIONAL" solo en el funcionario también.
- **SIM** — clasificación contiene "SIM" (copia desde la base activa, no
  se mueve).
- **Multiples_IUS** — un mismo nombre con más de un Radicado IUS distinto
  (caso especial para revisión).

Implementada en `src/diagnostic.py` (`split_by_status`,
`extract_multi_ius`) y escrita a Excel con
`src/exportation.py:export_multi_sheet_excel`.

## Relacionado
- [[Registro]]
- [[Limpieza]]
- [[Módulo Pandas]]
