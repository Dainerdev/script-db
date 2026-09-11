# Plan técnico — Spec 001 (GUI de limpieza de base de datos Excel)

## Cambios aditivos en `src/` (excepción documentada, constitución #3)
Todos preservan el comportamiento actual para cualquier archivo que ya
tenga todas las columnas (como el archivo real de producción) — cero
riesgo para `main.py`, que no cambia ni una línea:
- `src/reading.py:read_excel_file` — nuevo parámetro opcional
  `raise_errors: bool = False`. Si es `True`, relanza la excepción
  original en vez de solo imprimirla y retornar `None`. La GUI lo llama
  con `raise_errors=True` dentro de un `try/except` para traducir el
  tipo de excepción a un mensaje específico en español (RF-2).
- `src/standardization.py:split_multiple_comparecientes` — si `name_col`
  o `id_col` no están en `df.columns`, retorna `df.copy()` sin desdoblar
  (mismo patrón de guarda que ya usa `extract_multi_ius`).
- `src/diagnostic.py:split_by_status` — si falta "CLASIFICACIÓN DEL
  RADICADO", retorna todo el `df` como "activos" y los demás grupos
  vacíos. Si falta "FUNCIONARIO A CARGO" (con clasificación presente),
  `mask_retirados` se trata como `False` para todas las filas.
- `src/standardization.py:add_radicado_ius_revisada` — si `ius_col` no
  está en `df.columns`, retorna `df.copy()` sin agregar la columna nueva.
- `src/diagnostic.py:run_similarity_report` — agrega
  `return {"ius_duplicados": ..., "cedulas_variantes": ..., "nombres_fuzzy": ...}`
  al final (hoy no retorna nada; `main.py` ya ignora el valor de retorno).
- `src/exportation.py:export_multi_sheet_excel` — nuevo parámetro
  opcional `raise_errors: bool = False`. [Agregado al implementar T8]:
  la función atrapaba CUALQUIER excepción de escritura, la imprimía y
  retornaba `None` sin relanzar — con el comportamiento por defecto, la
  GUI habría mostrado "guardado exitoso" ante una ruta sin permisos de
  escritura (justo el caso límite ya aprobado en la spec). Mismo patrón
  que `read_excel_file`: por defecto no cambia nada, con
  `raise_errors=True` relanza para que la GUI sepa que falló.
- `src/exportation.py:export_multi_sheet_excel` — [Agregado en la ronda
  de mejoras post-validación, RF-14/RF-15/RF-16] dos parámetros opcionales
  más, ambos `None` por defecto (cero efecto si no se pasan):
  `on_sheet_done(sheet_name, indice, total)`, llamado justo después de
  terminar cada hoja (progreso real); `should_cancel()` (sin argumentos,
  retorna bool), revisado antes de cada hoja — si es `True`, aborta
  lanzando `ExportCancelled` (subclase de `Exception`, sigue el mismo
  camino de `raise_errors` pero el caller la distingue con su propio
  `except`).
- `gui/controller.py:process` — [Agregado en la misma ronda] nuevo
  parámetro opcional `should_cancel=lambda: False`, revisado después de
  cada una de sus 3 etapas (no se puede interrumpir una llamada de pandas
  ya en curso, solo saltar a la siguiente); si da `True`, emite
  `("cancelled",)` y retorna sin llegar a `("done", ...)`.

Cada guarda se implementa con sus propios tests (ver Estrategia de
tests) — hoy `src/` no tiene suite automática, así que estos son los
primeros tests del proyecto.

## Estructura de módulos
- `gui/app.py` — ventana principal Tkinter, layout y wiring de eventos.
  (RF-1, RF-6, RF-7, RF-8, RF-9, RF-13)
- `gui/controller.py` — `read_and_validate` + `process`, funciones
  síncronas (el threading es responsabilidad de `app.py`, T8); invocan
  únicamente funciones de `src/` documentadas en `AGENTS.md`.
  (RF-2, RF-3, RF-5, RF-6, RF-10, RF-12)
- `gui/validation.py` — valida hoja/columnas antes de procesar; genera la
  lista de columnas faltantes y qué se omite. Funciones puras, sin
  Tkinter. (RF-2, RF-3)
- `gui/diagnostics_summary.py` — convierte lo que retornan
  `run_diagnostics`, `check_duplicates` y `run_similarity_report`
  (conteos de IUS/cédulas/fuzzy, ya con sus propias guardas) en el
  resumen en español de RF-4. Funciones puras. `rows_with_extra_spaces`
  se calcula aparte (agregado por fila, no por columna — ver docstring
  del módulo), con los mismos criterios de espaciado de `run_diagnostics`.
- `gui/error_log.py` — arma el mensaje genérico y escribe el detalle
  técnico en un log; retorna la ruta o `None` si la escritura también
  falla. Funciones puras. (RF-12)
- `gui/state.py` — dataclasses de estado en memoria (ver Modelo de datos).
- `run_gui.py` (raíz) — entry point (`App().mainloop()`); script que
  empaqueta PyInstaller.
- `tests/` — pytest: tests de los cambios aditivos en `src/` + tests de
  cada módulo no-visual de `gui/`.

## Modelo de datos (estado en memoria, sin persistencia — RF-10)
Nombres de campo en inglés (constitución, principio 6 — corregido tras
implementar T2, donde el borrador original de este plan tenía nombres en
español).
```python
@dataclass
class ValidationResult:
    sheet_ok: bool
    missing_columns: list[str]
    can_continue: bool           # False solo si sheet_ok es False

@dataclass
class DiagnosticSummary:
    total_rows: int
    rows_with_extra_spaces: int
    nulls_by_key_column: dict[str, int]
    duplicated_rows: int          # len(check_duplicates(df))
    ids_with_name_variants: int
    duplicated_ius: int
    fuzzy_similar_names: int

@dataclass
class ProcessResult:
    sheets: dict[str, pd.DataFrame]   # nombre_hoja -> df, listo para export
    counts: dict[str, int]            # nombre_hoja -> len(df), para RF-11
    source_path: str                  # style_reference_path del export
```
`ProcessResult` vive en memoria mientras la ventana esté abierta, para
reintentar el guardado (RF-10) sin reprocesar.

## Contrato de eventos hilo → UI (RF-6, RF-7) [Revisado al implementar T7]
`gui/controller.py` expone dos funciones síncronas, no una — RF-3 exige
una pausa real para que el funcionario decida "Continuar"/"Cancelar"
entre leer y procesar, algo que una sola función corriendo de un tirón
no puede modelar limpiamente:
- `read_and_validate(path, on_event)` — RF-2/RF-3/RF-4. Emite
  `("stage", "Leyendo archivo...")`, y termina con
  `("read_error", mensaje_especifico)` (RF-2, bloqueante — mensaje ya
  traducido según el tipo de excepción) o
  `("diagnostic", ValidationResult, DiagnosticSummary, df)`.
- `process(df, source_path, on_event)` — RF-5/RF-6/RF-7/RF-10/RF-12.
  Emite `("stage", texto)` + `("progress", fracción)` por cada una de
  sus 3 etapas (limpieza, similitud, separación), y termina con
  `("done", ProcessResult)` o, ante un error no previsto,
  `("error", mensaje_generico, log_path_o_None)` vía
  `gui/error_log.py`.

`app.py` (T8) envuelve cada llamada en su propio `threading.Thread`,
pasa `on_event=queue.put` y sondea la cola cada 100ms con
`root.after(100, poll_queue)`. La etapa "Exportando resultados..."
(RF-8/RF-9/RF-11) NO vive en `controller.py`: pasa después del diálogo
"Guardar como", ya en T8, usando `ProcessResult.sheets` directamente sin
volver a procesar.

## Decisiones técnicas (con alternativa descartada)

**#1 — Conteo de IUS duplicados para el diagnóstico (RF-4). [Revisado
tras QA de la spec]**
Decisión: `run_similarity_report` ahora retorna un diccionario con los 3
conteos (ver "Cambios aditivos en `src/`"); `gui/diagnostics_summary.py`
simplemente lo consume.
Descartado: la versión anterior de este plan proponía duplicar esas 3
líneas de `groupby().nunique()` dentro de `gui/` para no tocar `src/` en
absoluto. Se descartó al revisar la spec como QA: la misma tensión
aparecía también en RF-2 (mensajes de error genéricos) y RF-3 (columnas
sin guarda que revientan en vez de omitirse), así que se resolvió una
sola vez, en la constitución, con una excepción acotada y documentada —
en vez de ir parchando cada síntoma por separado en `gui/`.

**#2 — Threading + queue vs. bloquear la UI.**
`threading.Thread` + `queue.Queue` para cumplir el NFR de interfaz
usable durante el procesamiento. Descartado: llamar el pipeline directo
en el hilo principal con `root.update()` intercalado — más simple, pero
no es realmente asíncrono y es frágil por reentrancia del mainloop.

**#3 — Threading vs. multiprocessing.**
Se descarta `multiprocessing`: pandas libera el GIL en la mayoría de sus
operaciones vectorizadas en C, un hilo basta, y evita serializar
DataFrames de 185k filas entre procesos.

**#4 — Empaquetado con PyInstaller.**
`pyinstaller --onefile --windowed --name LimpiezaJEP --icon=assets/icon.ico run_gui.py`.
Descartado: `cx_Freeze` y distribuir intérprete embebido a mano.

**#11 — Ícono: foto de perfil oficial de la cuenta de X @PGN_COL, no un
recorte propio (T13, revisado).**
El identificador visual 2026 publicado en
`procuraduria.gov.co/procuraduria/conozca-entidad/Pages/Identificador.aspx`
solo tiene versiones horizontales con el nombre completo — ilegible
reducido a 16×16/32×32 px. Primer intento: recortar y recolorear a mano
el "ojo" del logo horizontal (descartado por el usuario en favor de una
versión ya diseñada). Versión final: `assets/icon.ico` generado con
Pillow desde `https://pbs.twimg.com/profile_images/2090488322657234944/FL-xHrm4_400x400.png`
(400×400, foto de perfil de la cuenta oficial `@PGN_COL` en X — ya
tiene el ojo + "PGN COLOMBIA" compuesto y cuadrado, sin necesitar
recorte), en tamaños 16/32/48/64/128/256. Pillow es dependencia de
desarrollo únicamente (genera el `.ico` una vez; no se importa en tiempo
de ejecución) — no se agrega a `requirements.txt`.
Descartado: pedir el asset a la Oficina de Prensa — innecesario una vez
apareció la foto de perfil oficial de X, que ya es cuadrada y de uso
público en su cuenta verificada.

**#5 — Formato de fecha en nombres sugeridos (RF-8) y de log (RF-12).**
`AAAAMMDD_HHMMSS` (ej. `Base_resultado_20260909_143205.xlsx`,
`error_20260909_143205.txt`) — ordenable alfabéticamente y sin
caracteres inválidos para nombres de archivo en Windows.
Descartado: `DD/MM/AAAA` (igual a las fechas del dominio) — inválido
como nombre de archivo en Windows por la barra `/`.

**#6 — Lectura del archivo: una sola vez, en la selección.**
El `DataFrame` se lee una única vez al seleccionar el archivo (RF-2) y
se conserva en memoria durante todo el flujo, incluido el reintento de
guardado (RF-10); "Procesar" nunca vuelve a leer del disco. Esto cierra
por diseño el caso de que el archivo se mueva/edite/elimine entre la
selección y el procesamiento.

**#7 — Doble clic en "Procesar" no es una condición de carrera real.**
Tkinter procesa eventos en un solo hilo dentro de su `mainloop()`; el
handler del clic (incluido deshabilitar los controles, RF-7) corre de
forma atómica antes del siguiente evento. No hace falta lógica adicional
de bloqueo.

**#8 — Progreso de exportación ponderado por filas, no por hoja (RF-16).**
`gui/app.py` calcula el progreso como
`filas_ya_exportadas / total_de_filas` usando `ProcessResult.counts`
(ya disponible, sin cálculo extra), actualizado en el callback
`on_sheet_done`. Descartado: progreso por CANTIDAD de hojas
(`hojas_hechas / 5`) — con Reparto_Activo teniendo ~50× las filas de
cualquier otra hoja, ese conteo saltaría a 20% tras la primera hoja y
luego apenas avanzaría, dando una sensación de avance engañosa.
También descartado: progreso estimado por tiempo transcurrido — más
frágil (depende de la máquina) y menos honesto que progreso real basado
en trabajo efectivamente terminado.

**#9 — Cancelación por puntos de control, no por hilo forzado.**
`should_cancel()` se revisa entre etapas de `process()` y antes de cada
hoja en `export_multi_sheet_excel` — nunca a mitad de una llamada de
pandas/xlsxwriter ya en curso. Descartado: matar el `threading.Thread`
a la fuerza (`Thread.terminate()` no existe en Python; hacks con
`ctypes` para inyectar una excepción en el hilo son frágiles y pueden
corromper el archivo de salida a medio escribir) — el patrón cooperativo
(revisar un flag) es el estándar recomendado en Python y evita ese riesgo.

**#10 — Ventana con tamaño inicial fijo + `wraplength`, no `tk.Text`.**
`root.geometry("820x480")` + `minsize` + `wraplength=720` en las
etiquetas largas. Descartado: reemplazar los `ttk.Label` por `tk.Text`
con scrollbar — más robusto ante contenido arbitrariamente largo, pero
innecesario aquí (el resumen más largo son 5 líneas cortas) y añade
complejidad (un widget editable hay que poner en solo-lectura, manejar
scroll) que no se justifica todavía; se reconsiderará si en producción
aparecen resúmenes más largos de lo esperado.

**#12 — Barra de progreso "reptante" (crawl) mientras se escribe una
hoja, en vez de quedarse fija (RF-16, refinado dos veces tras pruebas
reales).**
`export_multi_sheet_excel` ahora también llama `on_sheet_start` justo
ANTES de escribir cada hoja (no solo `on_sheet_done` al terminar), ya
que una sola llamada de `xlsxwriter` no tiene puntos de avance
intermedios propios. `gui/app.py` usa ese aviso para animar la barra
por su cuenta con pasos LINEALES fijos: cada 120ms avanza un paso de
tamaño constante — `(objetivo × 0.92 − inicio) / 55` — hasta un tope
del 92% de la distancia al punto real (nunca lo alcanza sola), y cuando
llega el evento real de "hoja terminada" la barra salta al valor exacto
y la animación se detiene. Con la hoja más grande (Reparto_Activo, con
50× más filas que las demás) tardando varios segundos, esto la mantiene
visiblemente en movimiento en vez de congelada.
Descartado (primer intento): decaimiento proporcional a la distancia
restante (acercarse un % de lo que falta en cada tick) — matemáticamente
nunca se detiene, pero el paso se vuelve imperceptible cerca del tope
(la Dra. Mauren lo reportó como "se sigue viendo pegada"); un paso
lineal fijo con techo explícito se nota parejo de principio a fin.
También descartado: estimar tiempo por fila para un ETA real (frágil,
depende de la máquina/disco) y un `mode="indeterminate"` de
`ttk.Progressbar` (pierde la información real de "cuánto falta").

## Contrato de errores (RF-12)
`gui/error_log.py:handle_unexpected_error(exc)` intenta escribir
`logs/error_<AAAAMMDD_HHMMSS>.txt` (carpeta `logs/` junto al `.exe`,
creada si no existe) con el traceback completo, y retorna un mensaje
genérico + la ruta del log. Si la escritura falla (ej. sin permisos),
retorna el mensaje genérico + `None`, y `app.py` ajusta el texto del
`messagebox` para no mostrar una ruta inexistente.

## Estrategia de tests
- `test_src_additive_guards.py`: cada cambio aditivo de `src/` (ver
  arriba) con columna presente (comportamiento idéntico al actual) y
  columna ausente (guarda activa), incluido el nuevo retorno de
  `run_similarity_report`.
- `test_validation.py`: hoja faltante/vacía (bloqueante), columnas
  faltantes (advertencia con lista correcta, incluida "No"), archivo
  completo (sin avisos).
- `test_diagnostics_summary.py`: `DiagnosticSummary` a partir de
  DataFrames de prueba pequeños, con y sin columnas faltantes.
- `test_controller.py`: orden de eventos emitidos (stage → ... → done)
  con un DataFrame pequeño y las funciones reales de `src/` (sin mocks);
  caso de excepción forzada → evento `error` con log escrito; caso de
  fallo al escribir el log → evento `error` sin ruta.
- `test_error_log.py`: creación del archivo, contenido con traceback,
  creación de `logs/` si no existe, y el caso de fallo de escritura.
- Sin tests automáticos de widgets/layout de `app.py` (constitución
  punto 4) — se valida con la demo manual del criterio de finalización.

## Empaquetado
- `run_gui.py` como entry point de PyInstaller.
- `pyinstaller --onefile --windowed --name LimpiezaJEP --icon=assets/icon.ico run_gui.py`
- Verificación manual en un equipo/entorno sin Python instalado.
  **Hecho: validado por la Dra. Mauren en un equipo real sin Python —
  funciona.**
