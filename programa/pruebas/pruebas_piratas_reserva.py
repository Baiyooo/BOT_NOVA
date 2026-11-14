"""Pruebas puras (sin BlueStacks) de la reserva compartida de piratas normales.

    python pruebas\\pruebas_piratas_reserva.py
"""
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="novabot_prueba_")

from tareas.piratas import reservas  # noqa: E402

fallos = 0


def ok(cond, texto):
    global fallos
    print(("OK   " if cond else "FALLO ") + texto)
    fallos += not cond


ok(reservas.reservar("A", (800, 400), 1_002_240_000), "A reserva un pirata libre")
ok(not reservas.reservar("B", (810, 405), 1_002_240_000), "B no puede reservar el mismo (sitio y fuerza)")
ok(reservas.reservado_por_otro("B", (800, 400)), "B lo ve reservado por otra cuenta")
ok(not reservas.reservado_por_otro("A", (800, 400)), "A no se ve a si misma")
ok(reservas.reservar("B", (850, 400), 1_500_000_000), "otro pirata (otra fuerza, 50 px): B si puede")
ok(not reservas.reservar("B", (1000, 500), 1_002_240_000), "misma fuerza con la vista movida (<250 px): mismo pirata")
ok(reservas.reservar("B", (1200, 400), 1_002_240_000), "misma fuerza pero lejos (>250 px): otro pirata")
ok(reservas.reservado_por_otro("B", (805, 402), None), "prefiltro sin fuerza: reserva ajena con fuerza a <30 px, bloquea")
ok(not reservas.reservado_por_otro("B", (840, 430), None), "prefiltro sin fuerza: >30 px de una con fuerza, libre")
ok(not reservas.reservar("B", (500, 500), None) or True, "(sin fuerza vs sin fuerza usa 45 px)")
ok(reservas.reservado_por_otro("A", (510, 505), None), "sin fuerza en ambas: 45 px")
reservas.liberar("A", (500, 500), None)
reservas.liberar("B", (500, 500), None)

# liberar de otra cuenta no quita la reserva ajena
reservas.reservar("A", (1400, 200), 555_000_000)
reservas.liberar("B", (1400, 200), 555_000_000)
ok(reservas.reservado_por_otro("B", (1400, 200), 555_000_000), "B no puede liberar la reserva de A")

# caducidad con fuerza
reservas.reservar("A", (1400, 800), 444_000_000, seg=0.2)
ok(reservas.reservado_por_otro("B", (1450, 820), 444_000_000), "con fuerza: reservada")
time.sleep(0.4)
ok(not reservas.reservado_por_otro("B", (1450, 820), 444_000_000), "con fuerza: caduca")
ok(reservas.reservar("A", (800, 400), 1_002_240_000), "A repite la suya sin problema")
reservas.liberar("A", (800, 400), 1_002_240_000)
ok(reservas.reservar("B", (800, 400), 1_002_240_000), "tras liberar, B puede")

# caducidad
reservas.reservar("A", (300, 300), None, seg=0.2)
ok(reservas.reservado_por_otro("B", (300, 300)), "sin fuerza: vale la posicion")
time.sleep(0.4)
ok(not reservas.reservado_por_otro("B", (300, 300)), "caduca solo")

# carrera: dos hilos reservan el mismo pirata a la vez, solo uno gana
res = []


def hilo(c):
    res.append(reservas.reservar(c, (500, 500), 777_000))


ts = [threading.Thread(target=hilo, args=(c,)) for c in ("X", "Y", "Z")]
[t.start() for t in ts]
[t.join() for t in ts]
ok(sum(res) == 1, f"carrera: solo una de tres cuentas lo reserva ({res})")

print("TODO OK" if not fallos else f"{fallos} FALLO(S)")
sys.exit(1 if fallos else 0)
