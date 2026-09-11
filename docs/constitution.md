# Constitución — GUI de limpieza de base de datos (script-db)

Principios innegociables. Toda spec, plan y tarea de esta ronda SDD
(exclusiva de la GUI) debe cumplirlos.

1. **Simplicidad primero**: Tkinter (stdlib) para la interfaz, sin
   frameworks web ni bases de datos nuevas. Única dependencia nueva
   permitida: PyInstaller (empaquetado a `.exe`), y `pytest` para tests.
2. **La spec manda**: ningún comportamiento de la GUI se implementa si no
   está descrito en la spec activa. Si falta una decisión, se detiene el
   trabajo y se pregunta antes de codificar.
3. **`src/` es una dependencia resuelta, con una excepción acotada**: la
   GUI invoca las funciones de `src/` (documentadas en `AGENTS.md`); no
   reimplementa su lógica. Se permiten cambios ADITIVOS puntuales en
   `src/` —parámetros opcionales cuyo valor por defecto preserva el
   comportamiento actual, o guardas `if col in df.columns` donde hoy
   falten— únicamente cuando sean indispensables para que la GUI cumpla
   su spec sin alterar el comportamiento de `main.py` (documentados en
   `plan.md`, sección "Cambios aditivos en `src/`"). Cualquier otro
   cambio (nueva lógica de negocio, cambio de comportamiento por
   defecto) requiere su propia spec, fuera de este alcance.
4. **Tests como puerta**: toda lógica no trivial de la GUI (validación de
   rutas, manejo de estados/errores, orquestación de `src/`) lleva test
   con pytest antes de darse por terminada. El layout visual se valida
   con demo manual, no con test forzado.
5. **Usuario sin conocimientos técnicos**: todo mensaje visible en
   pantalla (errores, confirmaciones, progreso) en español claro y
   accionable; nunca se expone un traceback crudo.
6. **Idioma**: identificadores de código en inglés; mensajes al usuario,
   docstrings y comentarios en español (misma convención que `src/`).
7. **Documentación viva**: cada spec/plan aprobado actualiza de forma
   incremental `grafo-conocimiento/` (nunca se reescribe desde cero).
