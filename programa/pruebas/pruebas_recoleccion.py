"""Pruebas de la tarea «Recolección» (sin BlueStacks ni ADB):

    python pruebas\\pruebas_recoleccion.py

 - solo hace las tareas de recoger que se han marcado (como la Rutina, a elegir);
 - filtra lo que propone el planificador;
 - las gemas se recogen cada 5 min si hay un dron libre, o cuando se piden a mano;
 - el desplegable de tareas la ofrece y la ventana guarda sus casillas sin perder el horario.
"""
import os
import sys
import tempfile
import time

os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cerebro import planificador as plan  # noqa: E402
from cerebro import rutina  # noqa: E402
from interfaz import catalogo  # noqa: E402

fallos = 0


def ok(nombre, cond, extra=""):
    global fallos
    print(("OK   " if cond else "FALLO ") + nombre + (f" {extra}" if extra else ""))
    fallos += 0 if cond else 1


class Falso:
    name = "127.0.0.1:5001"


# ---- solo lo marcado
r = rutina.SoloRecoleccion(Falso(), que={"gratis": True, "escombros": True, "gemas": True,
                                         "sigilo": True, "ballenas": True, "cosmomante": True})
ok(f"solo recoge lo marcado: {sorted(r._elegidas)}", r._elegidas == {"gratis", "escombros", "gemas"})
ok("no hace piratas, ballenas ni minijuegos", not any(r.que[k] for k in ("sigilo", "normales", "ballenas",
                                                                       "cosmomante", "roaming", "bingo")))
ok("las gemas van aparte (no por el planificador)", r.que["gemas"] is False and r.recoger_gemas is True)
ok("sin «Recompensas de eventos» no lee los eventos", r._leido_sesion is True)
r2 = rutina.SoloRecoleccion(Falso(), que={"eventos": True})
ok("con «Recompensas de eventos» si los lee", r2._leido_sesion is False and r2._elegidas == {"eventos"})
ok("nombre de la tarea", rutina.SoloRecoleccion.NOMBRE == "Recolección")

# ---- filtra lo que propone el planificador
propuestas = [plan.Accion(100, "leer_eventos", "x", {}), plan.Accion(90, "gratis", "x", {}),
              plan.Accion(60, "sigilo", "x", {}), plan.Accion(55, "escombros", "x", {}),
              plan.Accion(103, "ballenas", "x", {}), plan.Accion(102, "gemas", "x", {})]
original = rutina.Rutina._decidir
rutina.Rutina._decidir = lambda self, est: list(propuestas)
try:
    claves = [a.clave for a in r._decidir({})]
    claves2 = [a.clave for a in r2._decidir({})]
finally:
    rutina.Rutina._decidir = original
ok(f"filtra el planificador: {claves}", claves == ["gratis", "escombros", "gemas"])
ok(f"con eventos tambien permite leerlos: {claves2}", claves2 == ["leer_eventos"])

# ---- gemas cada 5 min con algun dron libre, o por orden manual
ok("gemas: la primera vez (con drones libres) toca", r._gemas_pedidas({"gemas_t": 0}) is True)
ok("gemas: hace poco que se recogieron, no toca", r._gemas_pedidas({"gemas_t": time.time()}) is False)
sin_gemas = rutina.SoloRecoleccion(Falso(), que={"escombros": True})
ok("gemas: desmarcadas, nunca", sin_gemas._gemas_pedidas({"gemas_t": 0}) is False)

# ---- el desplegable de tareas la ofrece
ok("desplegable: grupo «Recolección»", any(g == "Recolección" for g, _ in catalogo.TAREA_GRUPOS))
ok("desplegable: tarea -> clave", catalogo.TAREA_FILA.get("Recolección (a elegir)") == "recoleccion")
ok("sin limite de tiempo", catalogo.UNIDAD.get("recoleccion") is None and "recoleccion" in catalogo.AYUDA_TAREA)

print(f"\nFALLOS: {fallos}")
sys.exit(1 if fallos else 0)
