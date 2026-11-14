"""Prueba de humo de las ballenas: ejecuta el ciclo del que invoca y el del que
apoya con un BlueStacks falso (pantalla negra) y comprueba que no revientan
(por ejemplo el antiguo «'bool' object is not callable»). No toca el juego.

    python pruebas\\pruebas_ballenas_humo.py
"""
import os
import sys
import tempfile
import threading
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="novabot_prueba_")

import numpy as np  # noqa: E402

from tareas.ballenas.tarea import Ballenas  # noqa: E402


class Falso:
    name = "127.0.0.1:5001"

    def capture(self):
        return np.zeros((900, 1600, 3), np.uint8)

    def tap(self, p):
        pass

    def drag(self, a, b):
        pass

    def back(self):
        pass


fallos = 0
for papel in ("invoca", "apoya"):
    parar = threading.Event()
    threading.Timer(8, parar.set).start()
    yo, otro = "5001", "5002"
    t = Ballenas(Falso(), log=lambda *a: None, stop=parar,
                 lider=yo if papel == "invoca" else otro, apoyo=otro if papel == "invoca" else yo,
                 preparar_grupo=False)
    try:
        (t.ciclo_lider if papel == "invoca" else t.ciclo_apoyo)()
        print(f"OK   {papel}: termina sin error ({t.status.get('estado')})")
    except Exception:                                    # noqa: BLE001
        fallos += 1
        print(f"FALLO {papel}:")
        traceback.print_exc()
print(f"\nFALLOS: {fallos}")
sys.exit(1 if fallos else 0)
