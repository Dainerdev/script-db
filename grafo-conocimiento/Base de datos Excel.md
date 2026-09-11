# Base de datos Excel

Archivo `.xlsx` de reparto de la Procuraduría/JEP (hoja "Reparto",
~185.000 [[Registro|registros]]) que llega con inconsistencias: nombres
con/sin tildes, espacios sobrantes, fechas en formatos mixtos o como
texto, celdas con múltiples comparecientes.

Es la entrada del pipeline (`src/reading.py:read_excel_file`, engine
`calamine` por velocidad) y también la fuente del estilo visual
(fuente, alineación, anchos de columna) que se replica en el archivo de
salida — ver [[Módulo Pandas]].

## Relacionado
- [[Registro]]
- [[Módulo Pandas]]
- [[GUI]] — el funcionario selecciona este archivo desde la interfaz.
