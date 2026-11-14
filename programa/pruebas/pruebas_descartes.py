"""Pruebas puras (sin BlueStacks) de la lista de descartes y del cerrojo.

    python pruebas\\pruebas_descartes.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="novabot_prueba_")

import numpy as np  # noqa: E402

from nucleo.cerrojo import Cerrojo  # noqa: E402
from tareas import descartes  # noqa: E402

fallos = 0


def ok(cond, texto):
    global fallos
    print(("OK   " if cond else "FALLO ") + texto)
    fallos += not cond


# ---- descartes
img = np.zeros((900, 1600, 3), np.uint8)
img[:, :800] = 120                                   # vista con algo de contenido
d = descartes.Descartes()
d.anotar((500, 400), img, "malo")
d.anotar((900, 300), img, "mando")
ok(d.bloqueado((510, 405), img), "malo: cerca del punto, bloqueado")
ok(not d.bloqueado((540, 400), img), "malo: radio pequeno (40 px fuera)")
ok(d.bloqueado((960, 300), img), "mando: radio grande (60 px dentro)")
ok(not d.bloqueado((1100, 300), img), "mando: lejos, libre")
otra = np.zeros((900, 1600, 3), np.uint8)
otra[:, 800:] = 200                                  # camara movida: vista distinta
ok(not d.bloqueado((500, 400), otra), "vista cambiada: se ignora")
ok(d.bloqueado((500, 400), img), "vuelve la vista: vale otra vez")
pequena = np.zeros((450, 800, 3), np.uint8)
pequena[:, :400] = 120
ok(d.bloqueado((250, 200), pequena), "escala con el ancho")
d._l = [(time.time() - 1,) + e[1:] for e in d._l]
ok(not d.bloqueado((500, 400), img), "caducado: libre")
ok(descartes.de_cuenta("a") is descartes.de_cuenta("a")
   and descartes.de_cuenta("a") is not descartes.de_cuenta("b"), "una lista por cuenta")

# ---- cerrojo
a = Cerrojo("prueba", "A", espera=0.3)
b = Cerrojo("prueba", "B", espera=0.3)
ok(a.adquirir(), "A toma el turno")
ok(not b.adquirir(), "B espera y no lo consigue")
b.soltar()                                           # cierra el intento fallido
a2 = Cerrojo("prueba", "A", espera=0.3)
ok(a2.adquirir(), "reentrante para la misma cuenta")
a2.soltar()
ok(os.path.exists(a.ruta), "sigue tomado tras soltar el interior")
a.soltar()
ok(not os.path.exists(a.ruta), "soltado: el archivo desaparece")
ok(b.adquirir(), "B entra tras soltar")
b.soltar()
# dueno muerto: archivo viejo sin renovar
c = Cerrojo("prueba", "C", espera=0.3, caducidad=0.2)
Path(c.ruta).write_text("muerto")
time.sleep(0.4)
ok(c.adquirir(), "caducado: se roba el turno")
c.soltar()
# parado respeta
Path(c.ruta).write_text("otro")
e = Cerrojo("prueba", "E", espera=30, parado=lambda: True)
t0 = time.time()
ok(not e.adquirir() and time.time() - t0 < 5, "respeta parado()")
os.remove(c.ruta)

# latido: con caducidad corta, el turno no caduca mientras se tiene
h1 = Cerrojo("latido", "H", espera=0.3, caducidad=0.6, latido=0.1)
h2 = Cerrojo("latido", "I", espera=0.3, caducidad=0.6)
ok(h1.adquirir(), "H toma el turno (con latido)")
time.sleep(1.5)
ok(not h2.adquirir(), "tras 1.5 s (> caducidad) sigue siendo de H gracias al latido")
h1.soltar()
ok(not os.path.exists(h1.ruta), "al soltar, para el latido y borra el lock")

# caducidad: si no se puede renombrar/borrar, no bucle activo y se agota la espera
q = Cerrojo("rep", "Q", espera=1.0, caducidad=0.1)
Path(q.ruta).write_text("viejo|1|x")
time.sleep(0.3)
llamadas = []


def falla(*a, **k):
    llamadas.append(1)
    raise PermissionError("bloqueado")


with mock.patch("nucleo.cerrojo.os.replace", falla):
    t0 = time.time()
    ok(not q.adquirir(), "no se puede retirar el caducado: no entra")
    ok(len(llamadas) <= 4 and time.time() - t0 >= 0.9, f"sin bucle activo ({len(llamadas)} intentos)")
q.soltar()
ok(q.adquirir(), "con el sistema de ficheros bien, retira el caducado y entra")
q.soltar()

# reentrancia sin segunda espera cuando el primer intento fallo
Path(c.ruta).write_text("otro|1|x")
r1 = Cerrojo("prueba", "R", espera=0.5)
r2 = Cerrojo("prueba", "R", espera=30)
t0 = time.time()
r1.adquirir()
r2.adquirir()
ok(time.time() - t0 < 3 and not r2.tengo, "el interior no repite la espera si el exterior no lo consiguio")
r2.soltar()
r1.soltar()
os.remove(c.ruta)

print(f"FALLOS: {fallos}")
sys.exit(1 if fallos else 0)
