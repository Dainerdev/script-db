# Estandarización

Normalización de valores dentro de un [[Registro|registro]] para que sean
comparables entre sí: mayúsculas y sin tildes en nombres propios
(compareciente, magistrado, funcionario a cargo), espaciado uniforme en
todo texto libre, y fechas convertidas a un formato único aunque lleguen
como texto, como "Mes Año" o con años fuera de rango plausible.

Implementada en `src/standardization.py`
(`standardize_column_names`, `standardize_column_spacing`,
`standardize_column_dates`, `standardize_reparto_column`). Es distinta
de la [[Limpieza|limpieza]] general: la estandarización normaliza
formato, no decide qué hacer con duplicados o registros sospechosos.

## Relacionado
- [[Registro]]
- [[Limpieza]]
- [[Módulo Pandas]]
