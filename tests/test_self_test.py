"""T21: autoprueba del .exe sin ventana (`LimpiezaJEP.exe --autoprueba entrada salida`). Datos sintéticos."""
import pandas as pd

from gui.self_test import run_self_test


def _entrada(ruta):
    pd.DataFrame({
        "No": [1, 2, 3],
        "RADICADO IUS": ["E-2020-100001", "E-2020-100002", "E-2020-100003"],
        "IDENTIFICACIÓN": ["1000000001", "1000000002\n1000000003", "1000000004\n1000000005"],
        "NOMBRES_APELLIDOS": ["Ana Ruiz Diaz", "Luis Mora Paz\nEva Rios Gil", "Rosa Marin Tellez Y Hugo Cano Villa"],
        "CLASIFICACIÓN DEL RADICADO": ["ACTIVO", "ARCHIVADO", "SIM"],
        "SOLICITUD": ["Devolución", "devolucion", "REQUERIMIENTO"],
    }).to_excel(ruta, sheet_name="Reparto", index=False)


def test_autoprueba_procesa_y_guarda_el_par_y_deja_un_informe(tmp_path):
    entrada, salida = tmp_path / "entrada.xlsx", tmp_path / "resultado.xlsx"
    _entrada(entrada)

    codigo = run_self_test(str(entrada), str(salida))

    assert codigo == 0
    assert salida.exists() and (tmp_path / "resultado_revision.xlsx").exists()
    informe = (tmp_path / "resultado.xlsx.autoprueba.txt").read_text(encoding="utf-8")
    assert informe.startswith("OK")
    assert "Reparto_Activo: 2" in informe and "pendientes: 1 valores, 1 filas" in informe
    assert "rapidfuzz" in informe


def test_autoprueba_con_un_archivo_que_no_sirve_devuelve_1_y_lo_dice(tmp_path):
    salida = tmp_path / "resultado.xlsx"

    codigo = run_self_test(str(tmp_path / "no_existe.xlsx"), str(salida))

    assert codigo == 1
    assert not salida.exists()
    informe = (tmp_path / "resultado.xlsx.autoprueba.txt").read_text(encoding="utf-8")
    assert informe.startswith("ERROR") and "No se encontró el archivo" in informe
