import sys

from gui.app import main
from gui.self_test import run_self_test

if __name__ == "__main__":
    # Spec 002, T21: "--autoprueba entrada salida" prueba el .exe sin ventana.
    if len(sys.argv) == 4 and sys.argv[1] == "--autoprueba":
        sys.exit(run_self_test(sys.argv[2], sys.argv[3]))
    main()
