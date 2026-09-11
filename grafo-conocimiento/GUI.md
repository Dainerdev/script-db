# GUI

Interfaz de escritorio en construcción (Tkinter, empaquetada a `.exe`
con PyInstaller) para que el [[Funcionario (usuario final)|funcionario]]
ejecute el pipeline de [[Módulo Pandas|`src/`]] sin usar la terminal:
seleccionar el [[Base de datos Excel|Excel de entrada]], ejecutar la
[[Limpieza|limpieza]]/[[Estandarización|estandarización]]/[[Separación de
registros|separación]], ver progreso y errores, y exportar el resultado.

**Estado:** spec aprobada (`specs/001-gui-limpieza-excel/spec.md`), plan
pendiente. Flujo: seleccionar Excel → advertencia si faltan columnas
(no bloquea, el funcionario decide) → resumen de diagnóstico en lenguaje
llano → procesar con barra de progreso por etapas → elegir dónde guardar
→ resumen final por hoja. No reimplementa lógica de `src/`, solo la
invoca — ver frontera documentada en [[Módulo Pandas]] y en `AGENTS.md`.

**Fuera de alcance de esta ronda:** configurar desde la GUI qué hoja o
columnas usa el proceso — se mantienen los defaults actuales de `src/`;
la genericidad ("cualquier columna u hoja") queda pendiente para una spec
futura. (Distinto de los cambios ADITIVOS sí permitidos — ver
[[Módulo Pandas]].)

## Relacionado
- [[Funcionario (usuario final)]]
- [[Módulo Pandas]]
- [[Base de datos Excel]]

**Plan técnico** (`specs/001-gui-limpieza-excel/plan.md`): módulos
`gui/app.py` (ventana), `gui/controller.py` (orquesta `src/` en un
`threading.Thread` + `queue.Queue`), `gui/validation.py`,
`gui/diagnostics_summary.py`, `gui/error_log.py`, entry point
`run_gui.py`. Empaquetado con PyInstaller (`--onefile --windowed`).

**Implementación** (`tasks.md` T1–T13): T1–T10, T12, T13 listas, 50
tests en verde. `gui/controller.py` (T7) terminó siendo dos funciones
síncronas —`read_and_validate` y `process`— en vez de una sola, porque
RF-3 exige una pausa real para que el funcionario decida
"Continuar"/"Cancelar" entre leer y procesar. `app.py` (T8) ata todo:
selección, advertencia de columnas, diagnóstico, progreso por etapas,
guardado automático al terminar (RF-8) con protección de sobrescritura
(RF-9), reintento sin reprocesar (RF-10) y confirmación al cerrar con
trabajo sin guardar. `run_gui.py` (T9) es el entry point real.

**Validado en producción real** (T10): la Dra. Mauren probó
`dist/LimpiezaJEP.exe` en un equipo de la Procuraduría sin Python
instalado — funciona (185k+ filas reales). De ese uso real salió una
segunda ronda de mejoras (T12, RF-14/15/16): botón "Cancelar" durante
Procesar/exportar, progreso de exportación ponderado por filas (no fijo
en "Exportando..."), y ventana con tamaño que ya no recorta el resumen
final. T13 agregó el ícono de la app: no hay versión cuadrada oficial
publicada del logo 2026, así que se usó la foto de perfil oficial de
la cuenta de X `@PGN_COL` (ojo + "PGN COLOMBIA", ya cuadrada) — ver
Decisión técnica #11 en `plan.md`.

**T11 — Validación final: spec cumplida.** RF-1 a RF-16 recorridas una
por una. Al hacerlo aparecieron huecos reales de cobertura automática
(sobre todo en las RF que dependen de diálogos: RF-8/9/10/13/15/16) que
no tenían test directo, solo el mecanismo subyacente — se cerraron con
15 tests nuevos, sin disparar ningún diálogo real. Suite final: 64
tests, verde. Único punto sin automatizar (por diseño, no por hueco):
RF-1, el diálogo nativo de selección en sí — verificado por uso real,
no por test, igual que en cualquier GUI de escritorio.

---
*Spec revisada como QA (ambigüedades, contradicciones, casos límite,
conflictos con la constitución) — ver hallazgos y resolución en la
sesión. Siguiente paso: T8 (`gui/app.py`, la ventana Tkinter).*
