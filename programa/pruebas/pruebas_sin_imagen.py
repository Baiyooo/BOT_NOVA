"""Instancia sin imagen: la Rutina comprueba unas pocas veces (no para
siempre) si BlueStacks vuelve y, si no, para esa cuenta sin recorrer todas
las tareas ni dejar un error por cada una.

    python pruebas\\pruebas_sin_imagen.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="novabot_prueba_")

from nucleo import adb  # noqa: E402
from cerebro import rutina  # noqa: E402
from cerebro.planificador import Accion  # noqa: E402

fallos = 0


def ok(texto, cond):
    global fallos
    print(("OK   " if cond else "FALLO ") + texto)
    fallos += 0 if cond else 1


class Ctrl:
    name = "127.0.0.1:5000"

    def __init__(self, vuelve_en=None):
        self.n, self.vuelve_en = 0, vuelve_en

    def capture(self):
        self.n += 1
        if self.vuelve_en is not None and self.n >= self.vuelve_en:
            return object()
        raise adb.SinConexion("sin imagen")


def rutina_falsa(ctrl):
    r = rutina.Rutina.__new__(rutina.Rutina)
    r.ctrl, r.status, r._fallos, r._pausa, r._rec_paso = ctrl, {}, {}, {}, 0
    r.log = lambda *a: None
    r.stop = None
    r.NOMBRES = {}
    r.CADA_CONEXION = 0
    r._ejecutar = lambda a, est: ctrl.capture()
    return r


rutina.time.sleep = lambda s: None
r = rutina_falsa(Ctrl())
r._accion_segura(Accion(10, "gratis", "x"), {})
ok("no vuelve: para la cuenta", getattr(r, "_sin_imagen", False))
ok("lo mira unas pocas veces, no para siempre", r.ctrl.n <= r.INTENTOS_CONEXION + 1)
ok("no cuenta como fallo de la tarea", r._fallos.get("gratis", 0) == 0 and "gratis" not in r._pausa)

r = rutina_falsa(Ctrl(vuelve_en=3))
r._accion_segura(Accion(10, "gratis", "x"), {})
ok("vuelve: sigue con la Rutina", not getattr(r, "_sin_imagen", False))
print(f"\nFALLOS: {fallos}")
sys.exit(1 if fallos else 0)
