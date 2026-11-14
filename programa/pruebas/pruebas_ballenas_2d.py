"""Pruebas de la vista 2D de ballenas y gemas (sin BlueStacks ni ADB):

    python pruebas\\pruebas_ballenas_2d.py

 - deteccion de la ballena y de las gemas en 2D a varios zooms, sobre imagenes
   hechas pegando los iconos reales (recursos/ballenas) en un fondo oscuro;
 - los pirata/estaciones (otras siluetas) no cuentan como ballena;
 - la vista elegida (2D por defecto, 3D) llega a la tarea;
 - con pareja cada cuenta manda hasta TODOS sus drones (no la mitad).
"""
import os
import sys
import threading

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tareas.ballenas import deteccion as det  # noqa: E402
from tareas.ballenas.tarea import Ballenas  # noqa: E402
from vision import conocimiento_vista  # noqa: E402

fallos = 0


def ok(nombre, cond, extra=""):
    global fallos
    print(("OK   " if cond else "FALLO ") + nombre + (f" {extra}" if extra else ""))
    fallos += 0 if cond else 1


def fondo():
    rng = np.random.default_rng(1)
    return (rng.integers(0, 14, (900, 1600, 3))).astype(np.uint8)


def pegar(img, icono, centro, escala=1.0):
    t = icono if escala == 1.0 else cv2.resize(icono, None, fx=escala, fy=escala)
    h, w = t.shape[:2]
    x, y = centro[0] - w // 2, centro[1] - h // 2
    img[y:y + h, x:x + w] = t
    return img


# ---- ballena en 2D, a varios zooms
ball = conocimiento_vista.icono("ballena_2d")
for esc in (1.0, 1.4, 2.0):
    img = pegar(fondo(), ball, (900, 500), esc)
    v = det.ballenas_2d(img)
    ok(f"ballena 2D a escala {esc}: {v}", len(v) == 1 and abs(v[0][0] - 900) < 12 and abs(v[0][1] - 500) < 12)
ok("sin ballena: no inventa ninguna", det.ballenas_2d(fondo()) == [])
bordes = pegar(fondo(), ball, (60, 450))                      # sobre el panel de la izquierda
ok("una ballena en el borde (botones) no cuenta", det.ballenas_2d(bordes) == [])

# ---- gemas blancas en 2D (zoom medio) y sin falsos positivos
gema = conocimiento_vista.icono("gema_blanca_2d")
img = fondo()
for c in ((800, 300), (1100, 520), (500, 640)):
    pegar(img, gema, c)
g = det.gemas_2d(img)
ok(f"gemas 2D: 3 pegadas -> {g}", len(g) == 3 and all(
    any(abs(a[0] - c[0]) < 14 and abs(a[1] - c[1]) < 14 for a in g) for c in ((800, 300), (1100, 520), (500, 640))))
ok("sin gemas: no inventa ninguna", det.gemas_2d(fondo()) == [])
img = pegar(fondo(), ball, (900, 500))
ok("una ballena no se cuenta como gema", det.gemas_2d(img) == [])


# ---- la vista llega a la tarea
class Falso:
    name = "127.0.0.1:5001"


def nueva(**kw):
    return Ballenas(Falso(), log=lambda *a: None, stop=threading.Event(), lider="5001", apoyo="5002",
                    preparar_grupo=False, **kw)


ok("vista por defecto: 2D", nueva().vista == "2d")
ok("vista 3D elegida", nueva(vista="3d").vista == "3d")
ok("vista rara: vuelve a 2D", nueva(vista="xyz").vista == "2d")

# ---- con pareja, cada cuenta manda hasta TODOS sus drones libres
for lider in (True, False):
    t = nueva(robots=6)
    t.sync.escribir = lambda **k: None
    t.sync.esperar = lambda *a, **k: {"fase": "gemas", "n_gemas": 7, "muertas": 1}
    t._ver_gemas_2d = lambda: 7
    pedidos = []
    t.recoger_gemas = lambda cupo, radio=False, p=pedidos: p.append(cupo) or cupo
    n, hechas = t._gemas_en_2d(lider, False)
    ok(f"pareja ({'invoca' if lider else 'apoya'}): 7 gemas, 6 drones -> cupo {pedidos}", pedidos == [6] and hechas == 6)
t = nueva(robots=6, sola=True)
t.BUSCAR_FUERA = False
t._ver_gemas_2d = lambda: 4
pedidos = []
t.recoger_gemas = lambda cupo, radio=False: pedidos.append(cupo) or cupo
t._gemas_en_2d(True, True)
ok(f"sola: 4 gemas -> cupo {pedidos}", pedidos == [4])

# ---- barrido del mapa cuando quedan drones: zoom medio con el sol centrado y, despues,
#      el sistema entero (gemas fuera del anillo, con la busqueda de manchas aisladas)
t = nueva(robots=7, sola=True)
pasos = []
t._asegurar_2d = lambda: pasos.append("medio")
t._zoom_mapa = lambda acercar: pasos.append("alejar") or True
t._contar_gemas = lambda: pasos.append(("contar", t._pequenas)) or 2
t.recoger_gemas = lambda cupo, radio=False: pasos.append(("recoger", cupo)) or min(cupo, 2)
hechas = t._barrido_2d(5)
ok(f"barrido: medio y sistema entero -> {pasos}",
   hechas == 4 and pasos == ["medio", ("contar", False), ("recoger", 5), "alejar", "alejar",
                             ("contar", True), ("recoger", 3)])
pasos.clear()
ok("barrido: sin drones libres no mira nada", t._barrido_2d(0) == 0 and pasos == [])
t.BUSCAR_FUERA = False
ok("barrido: desactivable", t._barrido_2d(3) == 0 and pasos == [])

# ---- gemas sueltas (Recolección): la vista elegida primero; en 3D, si no sale nada, cae al 2D
def sueltas(vista, tres_d):
    t = nueva(robots=7, sola=True, vista=vista)
    llamadas = []
    t._sueltas_en_3d = lambda *a: llamadas.append("3d") or tres_d
    t._ver_gemas_2d = lambda: llamadas.append("2d") or 0
    t._restaurar_vista = t._ir_al_sistema = lambda *a, **k: None
    t._modo = lambda q: True
    t.sync.leer = lambda: {}
    t.sync.del_otro = lambda: {}
    return t.recoger_sueltas(), llamadas


h3, ll3 = sueltas("3d", 3)
ok(f"gemas sueltas en 3D con ballena reciente: {h3}, solo 3D {ll3}", h3 == 3 and ll3 == ["3d"])
h3b, ll3b = sueltas("3d", 0)
ok(f"gemas sueltas en 3D sin nada: prueba 3D y despues 2D {ll3b}", ll3b == ["3d", "2d"])
h2, ll2 = sueltas("2d", 5)
ok(f"gemas sueltas en 2D: no mira el 3D primero {ll2}", ll2 == ["2d"])

# ---- la vista es un ajuste de CADA cuenta (Ajustes > Ballenas): 2D por defecto
from cerebro import config_ballenas as cb  # noqa: E402

ok("ajuste por cuenta: sin vista guardada -> 2D", cb.normalizar({"rol": "sola"})["vista"] == "2d")
ok("ajuste por cuenta: 3D guardado se respeta", cb.normalizar({"rol": "sola", "vista": "3d"})["vista"] == "3d")
ok("ajuste por cuenta: valor raro -> 2D", cb.normalizar({"vista": "otra"})["vista"] == "2d")

print(f"\nFALLOS: {fallos}")
sys.exit(1 if fallos else 0)
