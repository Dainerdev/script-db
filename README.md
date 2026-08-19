# Automatización de limpieza y diagnóstico de datos

Proyecto desarrollado en Python para la lectura, diagnóstico, limpieza y estandarización de una base de datos almacenada en archivos Excel, con el objetivo de preparar la información para su posterior migración a Microsoft Access.

## Descripción

El proyecto permite procesar archivos Excel que contienen información con inconsistencias en sus registros, como:

- Nombres con y sin tildes.
- Espacios innecesarios.
- Diferentes formatos de fechas.
- Fechas almacenadas como texto.
- Valores vacíos o nulos.
- Diferencias en la estructura de los datos.
- Posibles registros duplicados.
- Inconsistencias en los valores de las columnas.

El procesamiento se realiza de manera automatizada utilizando Python y librerías especializadas para manipulación de datos.

## Tecnologías utilizadas

- Python 3
- Pandas
- OpenPyXL
- Excel

## Estructura del proyecto

```text
/
├── data/
│   ├── original/
│   └── processed/
│
├── diagnostico/
│
├── src/
│   ├── diagnostic.py
│   ├── exportation.py
│   ├── reading.py
│   └── standarization.py
│
├── main.py
└── requirements.txt
