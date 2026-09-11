# Funcionario (usuario final)

Persona de la Procuraduría/JEP que hoy necesitaría ejecutar `python
main.py` desde la terminal para limpiar la [[Base de datos Excel|base de
datos]], pero **no tiene conocimientos de programación**. Es el actor
principal de la spec de [[GUI]]: necesita poder cargar el Excel, disparar
el proceso, ver progreso/errores en lenguaje claro (nunca un traceback
crudo) y obtener el archivo de resultados, sin tocar código ni terminal.

Historias de usuario (`specs/001-gui-limpieza-excel/spec.md`): elegir el
archivo de entrada sin terminal, entender el diagnóstico sin tablas
técnicas, decidir si continuar cuando faltan columnas esperadas, ver
avance mientras procesa, elegir dónde guardar el resultado, y confirmar
al final cuántos registros quedaron en cada categoría.

## Relacionado
- [[GUI]]
- [[Base de datos Excel]]
