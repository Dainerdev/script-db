# Spec 001 — GUI de limpieza de base de datos Excel

## Contexto y objetivo
Los funcionarios de la Procuraduría/JEP necesitan limpiar, estandarizar y
separar la base de datos de reparto (Excel, ~185.000 filas) que hoy solo
se procesa ejecutando `python main.py` desde la terminal. Esta spec cubre
una GUI de escritorio para que lo hagan sin conocimientos de programación:
cargar el Excel, ejecutar la limpieza, ver progreso/errores en lenguaje
claro, y exportar el resultado. La lógica de limpieza (`src/`) ya existe
y está probada — en esta ronda solo recibe cambios aditivos puntuales
(ver `docs/constitution.md` principio 3 y `plan.md`), nunca cambios de
comportamiento.

## Usuarios / actores
Funcionarios de la Procuraduría/JEP sin conocimientos de programación, en
equipos Windows. Un solo usuario por ejecución, sin cuentas ni red.

## Historias de usuario
- H1: Como funcionario quiero seleccionar el Excel de entrada desde un
  diálogo de Windows para no usar la terminal ni escribir rutas.
- H2: Como funcionario quiero ver un resumen claro del diagnóstico
  (nulos, duplicados, problemas de texto) para saber qué tan sucia está
  mi base antes de limpiarla.
- H3: Como funcionario quiero ejecutar la limpieza con un botón y ver el
  avance por etapas para saber que el programa sigue funcionando.
- H4: Como funcionario quiero elegir dónde se guarda el archivo de
  resultados, igual que en cualquier programa de Windows.
- H5: Como funcionario quiero que se me avise con un mensaje claro (no un
  error técnico) si a mi archivo le falta alguna columna que el proceso
  espera, para corregirlo o decidir seguir de todas formas.
- H6: Como funcionario quiero un resumen final (cuántos registros quedaron
  en cada categoría) para confirmar que el proceso terminó bien.

## Requisitos funcionales (criterios de aceptación en EARS)

### Selección y validación del archivo de entrada (H1, H5)
- RF-1: CUANDO el funcionario haga clic en "Seleccionar archivo", EL
  SISTEMA abrirá un diálogo nativo de Windows filtrado a `.xlsx`/`.xls`.
- RF-2: CUANDO se seleccione un archivo, EL SISTEMA intentará leer la
  hoja "Reparto" (nombre exacto, sensible a mayúsculas/minúsculas). SI el
  archivo no puede leerse (dañado, no es un Excel válido, está abierto en
  otro programa), no existe una hoja llamada exactamente "Reparto", o esa
  hoja no tiene datos reconocibles (sin fila de encabezado), ENTONCES EL
  SISTEMA mostrará un mensaje de error claro con la causa específica y NO
  habilitará el botón de procesar.
- RF-3: SI el archivo se lee correctamente pero le faltan columnas que el
  proceso espera (RADICADO IUS, NOMBRES_APELLIDOS, IDENTIFICACIÓN, FECHA,
  REPARTO, CLASIFICACIÓN DEL RADICADO, FUNCIONARIO A CARGO, MAGISTRADO,
  No), ENTONCES EL SISTEMA mostrará una advertencia (no bloqueante)
  listando las columnas faltantes y qué partes del proceso se omitirán
  por esa razón, con opciones "Continuar de todas formas" / "Cancelar".

### Diagnóstico (H2)
- RF-4: CUANDO el archivo se acepte (con o sin advertencias), EL SISTEMA
  mostrará un resumen del diagnóstico inicial (total de filas, filas con
  espacios sobrantes, nulos en columnas clave, filas completamente
  duplicadas, cédulas con variantes de nombre, radicados IUS duplicados,
  nombres similares por *fuzzy matching*) en lenguaje llano, sin tablas
  columna por columna.

### Procesamiento (H3)
- RF-5: CUANDO el funcionario confirme "Procesar", EL SISTEMA ejecutará,
  en este orden, invocando únicamente funciones existentes de `src/`
  (ver `AGENTS.md`, incluidas sus guardas para columnas ausentes):
  limpieza/estandarización → análisis de similitud/duplicados →
  separación de registros → adición de "Radicado IUS Revisada".
- RF-6: MIENTRAS el procesamiento esté en curso, EL SISTEMA mostrará una
  barra de progreso indicando la etapa actual, entre el conjunto cerrado:
  "Leyendo archivo...", "Limpiando y estandarizando...", "Analizando
  duplicados...", "Separando registros...", "Exportando resultados...".
- RF-7: MIENTRAS haya un procesamiento en curso, EL SISTEMA deshabilitará
  los controles de selección/procesamiento para evitar dos procesos
  simultáneos.

### Guardado y resumen final (H4, H6)
- RF-8: CUANDO el procesamiento de datos termine sin errores, EL SISTEMA
  abrirá un diálogo nativo "Guardar como" (nombre sugerido: nombre del
  archivo original + "_resultado" + fecha) para que el funcionario elija
  carpeta y nombre de salida, y exportará con `export_multi_sheet_excel`
  usando el archivo original como referencia de estilo.
- RF-9: SI la ruta elegida en "Guardar como" coincide con la ruta del
  archivo de entrada, ENTONCES EL SISTEMA mostrará una advertencia
  explícita ("vas a reemplazar tu archivo original") antes de confirmar
  el guardado.
- RF-10: SI el funcionario cancela el diálogo "Guardar como", ENTONCES EL
  SISTEMA conservará los datos ya procesados en memoria y permitirá
  reintentar el guardado sin repetir el procesamiento desde cero.
- RF-11: CUANDO la exportación termine, EL SISTEMA mostrará un resumen
  final con la cantidad de registros por hoja generada (Reparto_Activo,
  Archivados, Funcionarios_Retirados, SIM, Multiples_IUS) y la ruta
  completa del archivo guardado.

### Cancelación y ventana (Cambio — validado con la Dra. Mauren en un
equipo real, sin Python, funcionando; RF-14/RF-15/RF-16 agregados tras
esa prueba)
- RF-14: MIENTRAS haya un procesamiento o una exportación en curso, EL
  SISTEMA mostrará un botón "Cancelar". CUANDO se presione, EL SISTEMA
  detendrá el flujo en el siguiente punto de control seguro (entre
  etapas de limpieza/similitud/separación, o entre hojas durante la
  exportación — no a mitad de una operación de pandas/Excel ya en
  curso) y lo comunicará como cancelado, sin mostrarlo como error.
- RF-15: SI se cancela durante la exportación, ENTONCES EL SISTEMA no
  dejará un archivo de resultado a medio escribir en la ruta elegida.
- RF-16: MIENTRAS la exportación esté en curso, EL SISTEMA actualizará
  la barra de progreso y el texto de etapa por cada hoja completada
  (no solo un mensaje fijo de "Exportando..."), ponderado por la
  cantidad de registros de cada hoja para que el avance refleje el
  trabajo real (la hoja Reparto_Activo puede tener 50× más filas que
  las demás). MIENTRAS se escribe una hoja individual (sin puntos de
  avance propios), la barra avanzará gradualmente hacia el siguiente
  punto conocido en vez de quedarse fija — validado como necesario tras
  la prueba real de la Dra. Mauren (la hoja más grande se veía congelada
  varios segundos).

### Errores y reuso (transversal)
- RF-12: SI ocurre un error no previsto en cualquier etapa, ENTONCES EL
  SISTEMA mostrará un mensaje genérico y comprensible (sin traceback en
  pantalla) e intentará guardar el detalle técnico en un archivo de log,
  indicando su ruta en el mensaje. SI la escritura del log también
  falla, ENTONCES EL SISTEMA lo indicará en el mismo mensaje (sin ruta) y
  sugerirá contactar a soporte con la hora exacta del error.
- RF-13: CUANDO termine un procesamiento (con éxito o cancelado), EL
  SISTEMA permitirá seleccionar un nuevo archivo y repetir el flujo sin
  cerrar y reabrir el programa. SI hay un resultado procesado pendiente
  de guardar, ENTONCES EL SISTEMA lo advertirá antes de descartarlo.

## Requisitos no funcionales
- La interfaz debe permanecer usable (no "No responde" de Windows)
  mientras procesa un archivo de ~185.000 filas x 27 columnas.
- Sin límite superior de filas impuesto por software; con archivos mucho
  mayores al de referencia, el límite práctico depende de la RAM del
  equipo — un fallo por memoria insuficiente se trata como error no
  previsto (RF-12).
- Solo Windows; se distribuye como `.exe` standalone (PyInstaller), sin
  requerir Python instalado en el equipo del funcionario.
- Todo mensaje visible en español claro, sin jerga técnica ni tracebacks.
- Sin red, sin credenciales, sin base de datos.
- La ventana debe mostrar completo el resumen final (ruta + conteo por
  hoja) sin recortarlo — tamaño inicial generoso, con ajuste de texto
  (`wraplength`) en vez de una ventana de tamaño fijo (Cambio: la
  primera versión sí lo recortaba, ver captura de la prueba real).

## Casos límite
- Excel dañado, abierto en otro programa, sin hoja "Reparto" (nombre
  exacto), o con la hoja presente pero sin datos reconocibles (sin fila
  de encabezado) → RF-2, bloqueante.
- Excel con encabezados válidos pero 0 filas de datos → se acepta, el
  diagnóstico lo refleja (0 filas) y el procesamiento continúa sin error.
- Excel válido con columnas faltantes → RF-3, advertencia no bloqueante.
- El archivo de entrada se lee una única vez, en el momento de la
  selección (RF-2); cambios posteriores en disco (movido, editado,
  eliminado) no afectan un procesamiento ya iniciado, porque no se
  vuelve a leer del archivo original hasta que el funcionario elija uno
  nuevo (RF-13).
- Funcionario cancela el diálogo de selección de archivo → vuelve a la
  pantalla inicial sin cambios.
- Funcionario cierra la ventana mientras hay un procesamiento en curso o
  un resultado procesado sin guardar → confirmación previa antes de
  cerrar.
- Ruta de guardado sin permisos de escritura → error claro + reintento
  (RF-10/RF-12), sin perder los datos ya procesados.
- Ruta de guardado igual a la del archivo de entrada → RF-9.

## Fuera de alcance
Hacer configurable desde la GUI qué hoja o qué nombres de columna usa el
proceso (sheet_name, RADICADO IUS, NOMBRES_APELLIDOS, etc.) — el
supervisor indicó dejar el comportamiento actual de `src/` como default;
volverlo genérico para "cualquier columna u hoja" queda como requisito
futuro para una spec posterior. También fuera de alcance: edición de
datos dentro de la GUI, previsualización/tabla interactiva de filas,
historial o cola de múltiples archivos, otros idiomas, instalador con
autoactualización.

## Criterios de finalización
- Todos los RF con lógica no visual (validación de columnas, orquestación
  de etapas, manejo de errores) cubiertos por test automático y
  `pytest -q` en verde — incluidos los cambios aditivos en `src/`.
- Demo manual del flujo completo con un archivo de prueba real: seleccionar
  → diagnóstico → procesar → progreso → guardar → resumen final, sin errores.
- Empaquetado exitoso a `.exe`, verificado en un equipo/entorno sin Python.

## Dudas abiertas
- [NECESITA ACLARACIÓN] Alcance exacto de la futura configurabilidad de
  hoja/columnas (qué tan flexible) — se resuelve con el supervisor antes
  de una spec futura, no bloquea esta.
