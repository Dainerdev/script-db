# Separación de registros

Última etapa del pipeline: tras la [[Limpieza|limpieza]], cada
[[Registro|registro]] se clasifica en una de las hojas de salida del
Excel de resultados:

- **Reparto_Activo** — el resto, base activa limpia.
- **Archivados** — clasificación contiene "ARCHIVADO".
- **Funcionarios_Retirados** — archivados cuyo funcionario a cargo
  contiene "RETIRADOS".
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
