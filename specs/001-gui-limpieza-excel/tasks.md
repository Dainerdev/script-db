# Tareas — Spec 001 (GUI de limpieza de base de datos Excel)

Cada tarea se implementa con tests primero (constitución punto 4);
ninguna se marca hecha con `pytest -q` en rojo.

- [x] T1. Esqueleto: paquete `gui/` (`__init__.py`), carpeta `tests/`,
      pytest configurado, `run_gui.py` placeholder. (RF: —)
      Hecho cuando: `pytest -q` corre (0 tests) sin errores.

- [x] T2. `gui/state.py`: dataclasses `ValidationResult`,
      `DiagnosticSummary`, `ProcessResult` (campos según `plan.md`).
      (Soporte de RF-3, RF-4, RF-10, RF-11)
      Hecho cuando: test de instanciación con los campos del plan en verde.

- [x] T3. Cambios aditivos en `src/` (excepción documentada, constitución
      #3): `read_excel_file(..., raise_errors=False)`,
      `split_multiple_comparecientes` y `add_radicado_ius_revisada` con
      guarda de columnas ausentes, `split_by_status` con degradación si
      falta CLASIFICACIÓN DEL RADICADO / FUNCIONARIO A CARGO, y
      `run_similarity_report` retornando el diccionario de conteos.
      (Soporte de RF-2, RF-3, RF-4, RF-5, RF-12)
      Hecho cuando: por cada función, test con la columna presente
      (comportamiento idéntico al actual) y test con la columna ausente
      (guarda activa) en verde; primeros tests del proyecto sobre `src/`.

- [x] T4. `gui/validation.py`: validar hoja "Reparto" leída (incluida
      hoja vacía) y las 9 columnas de RF-3. (RF-2, RF-3)
      Hecho cuando: tests de sheet faltante/vacía (bloqueante), columnas
      faltantes (lista correcta), archivo completo (sin avisos) en verde.

- [x] T5. `gui/diagnostics_summary.py`: construir `DiagnosticSummary` a
      partir de `run_diagnostics`, `check_duplicates`,
      `check_duplicate_names_by_id`, `check_fuzzy_duplicate_names` y el
      diccionario que retorna `run_similarity_report` (T3). (RF-4)
      Hecho cuando: test con DataFrame de prueba pequeño produce los 7
      campos correctos, en verde.

- [x] T6. `gui/error_log.py`: `handle_unexpected_error(exc)` intenta
      escribir `logs/error_<fecha_hora>.txt` con traceback completo y
      retorna mensaje genérico + ruta (o + `None` si falla la
      escritura). (RF-12)
      Hecho cuando: tests de creación de archivo, contenido con
      traceback, creación de `logs/` si no existe, y fallo de escritura
      (retorna `None` en vez de ruta), en verde.

- [x] T7. `gui/controller.py`: `run(path, on_event)` orquesta
      lectura (una sola vez, Decisión #6) → validación → limpieza/
      estandarización → similitud → separación → "Radicado IUS
      Revisada", emitiendo eventos `stage`/`progress`/`diagnostic`/
      `done`/`error` por cola; invoca solo funciones de `src/` (T3) +
      `gui/validation.py` + `gui/diagnostics_summary.py` +
      `gui/error_log.py`. (RF-2, RF-3, RF-5, RF-6, RF-10, RF-12)
      Hecho cuando: test de orden de eventos con DataFrame pequeño real
      (stage → ... → done), test de excepción forzada → evento `error`
      con log escrito, y test de columnas faltantes → procesa igual sin
      excepción (gracias a T3), en verde.

- [x] T8. `gui/app.py`: ventana Tkinter completa — selección de archivo
      (RF-1, RF-2), advertencia de columnas faltantes con
      Continuar/Cancelar (RF-3), resumen de diagnóstico (RF-4), botón
      procesar con barra de progreso por etapas (RF-5, RF-6, RF-7),
      diálogo "Guardar como" con advertencia de sobrescritura (RF-8,
      RF-9) + resumen final (RF-11), reintento de guardado sin
      reprocesar (RF-10), nuevo archivo con advertencia si hay resultado
      sin guardar (RF-13), confirmación al cerrar con proceso en curso o
      resultado sin guardar.
      Hecho cuando: smoke test de construcción de `App` sin lanzar
      `mainloop()` (`root.withdraw()`) en verde, + demo manual del flujo
      completo con un archivo de prueba real.

- [x] T9. `run_gui.py`: entry point (`App().mainloop()`). (Soporte)
      Hecho cuando: `python run_gui.py` abre la ventana sin errores
      (verificación manual).

- [x] T10. Empaquetado: `pyinstaller --onefile --windowed --name
      LimpiezaJEP run_gui.py`. (Soporte, criterios de finalización)
      Hecho cuando: el `.exe` corre por doble clic en un equipo/entorno
      sin Python y completa el flujo con un archivo de prueba real.
      **Validado en un equipo real sin Python (Dra. Mauren): funciona.**

- [x] T12. Mejoras post-validación (feedback de la Dra. Mauren sobre
      el `.exe` corriendo de verdad): botón "Cancelar" durante
      procesar/exportar (RF-14, RF-15), progreso de exportación
      ponderado por filas en vez de fijo (RF-16), tamaño de ventana que
      ya no recorta el resumen final. (RF-14, RF-15, RF-16)
      Hecho cuando: tests de cancelación (controller y export) y de
      progreso por hoja en verde; ventana con tamaño inicial que
      muestra el resumen completo.
      **Segunda vuelta (misma tarea):** la hoja más grande seguía
      viéndose congelada varios segundos (sin puntos de avance propios
      dentro de una sola escritura) — se agregó animación "reptante"
      hacia el siguiente punto real (Decisión técnica #12). Reconstruido
      y verificado.

- [x] T13. Ícono de la aplicación: `assets/icon.ico` generado desde la
      foto de perfil oficial de la cuenta de X `@PGN_COL` (cuadrada,
      ojo + "PGN COLOMBIA" ya compuesto — ver Decisión técnica #11).
      Hecho cuando: `assets/icon.ico` existe y el `.exe` empaquetado lo
      muestra en la barra de tareas/título. **`--icon=assets/icon.ico`
      agregado al comando de PyInstaller; reconstruido con `--clean` y
      verificado extrayendo el ícono real del `.exe` (no solo confiar
      en que el build "completó bien" — un rebuild sin `--clean`
      dejó el ícono viejo la primera vez).

- [x] T11. Validación final: checklist RF-1 a RF-16 con su test o
      verificación manual asociada; actualización final de
      `grafo-conocimiento/`. (Todos)
      Hecho cuando: cada RF queda cubierto y el veredicto es "spec
      cumplida". **Veredicto: spec cumplida.** Al recorrer las RF se
      encontraron varios huecos reales de cobertura automática (RF-8,
      RF-9, RF-10, RF-13, RF-15, RF-16 no tenían test directo — solo el
      mecanismo subyacente) y se cerraron agregando 15 tests nuevos a
      `tests/test_app.py`, sin necesidad de disparar ningún diálogo
      real (mismo patrón de `test_app_integration.py`). Suite final:
      64 tests, `pytest -q` en verde.
