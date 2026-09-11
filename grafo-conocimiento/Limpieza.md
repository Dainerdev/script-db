# Limpieza

Proceso más amplio que la [[Estandarización|estandarización]]: incluye
desdoblar registros con múltiples comparecientes empaquetados en una
celda (`split_multiple_comparecientes`), detectar duplicados y
similitudes (radicados IUS repetidos, una misma cédula con variantes de
nombre, nombres parecidos por *fuzzy matching*), y generar la columna
"Radicado IUS Revisada" con el código más avanzado por compareciente.

Orquestada por `clean_and_standardize` y `run_similarity_report` en
`src/standardization.py` / `src/diagnostic.py`. El resultado alimenta la
[[Separación de registros|separación]] final.

## Relacionado
- [[Registro]]
- [[Estandarización]]
- [[Separación de registros]]
- [[Módulo Pandas]]
