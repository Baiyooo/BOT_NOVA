"""Pruebas puras de la grafica compartida: turno, limitador y caida a procesador.

    python pruebas\\pruebas_gpu_compartida.py
"""
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="novabot_prueba_")

import numpy as np  # noqa: E402

from vision import gpu_compartida as gc  # noqa: E402
from vision import percepcion  # noqa: E402

fallos = 0


def ok(cond, texto):
    global fallos
    print(("OK   " if cond else "FALLO ") + texto)
    fallos += not cond


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def nueva(reloj, **kw):
    return gc.GpuCompartida(candado=gc.CandadoLocal(), almacen=gc.AlmacenMemoria(), reloj=reloj, **kw)


# --- limitador: como mucho 4 por segundo en total
r = Reloj()
g = nueva(r, max_por_seg=4)
ok(g.ejecutar(lambda x: x + 1, 1) == 2, "primera imagen: va a la grafica")
ok(g.ejecutar(lambda x: x + 1, 1) is None, "segunda al instante: limite, va al procesador")
r.t += 0.3
ok(g.ejecutar(lambda x: x + 1, 1) == 2, "pasado el intervalo vuelve a poder")
usadas = 0
for _ in range(40):                      # 40 intentos en 1 s simulado
    r.t += 0.025
    usadas += g.ejecutar(lambda x: 1, 0) is not None
ok(usadas <= 4, f"en 1 s no pasa de 4 imagenes (fueron {usadas})")

# --- cola compartida: un solo uso a la vez entre hilos
g = nueva(time.time, max_por_seg=1000, espera=0.0)
dentro, maximo, rechazadas = [0], [0], [0]
lk = threading.Lock()


def lento(x):
    with lk:
        dentro[0] += 1
        maximo[0] = max(maximo[0], dentro[0])
    time.sleep(0.02)
    with lk:
        dentro[0] -= 1
    return 1


def hilo():
    for _ in range(10):
        if g.ejecutar(lento, 0) is None:
            with lk:
                rechazadas[0] += 1


ts = [threading.Thread(target=hilo) for _ in range(6)]
[t.start() for t in ts]
[t.join() for t in ts]
ok(maximo[0] == 1, "nunca dos usos de la grafica a la vez")
ok(rechazadas[0] > 0, f"quien no tiene turno usa el procesador sin esperar ({rechazadas[0]} desvios)")

# --- caida: errores seguidos pausan la grafica
r = Reloj()
g = nueva(r, max_por_seg=1000, fallos_para_pausar=3, pausa=60)


def roto(x):
    raise RuntimeError("grafica ocupada")


res = []
for _ in range(3):
    r.t += 1
    res.append(g.ejecutar(roto, 0))
ok(all(v is None for v in res), "un error no rompe: devuelve None (procesador)")
ok(g.en_pausa(), "tras 3 errores seguidos se pausa la grafica")
ok(g.ejecutar(lambda x: 5, 0) is None, "en pausa no se usa")
r.t += 61
ok(g.ejecutar(lambda x: 5, 0) == 5, "pasada la pausa se vuelve a probar")

# --- lentitud: tarda mas de lo permitido -> cuenta como ocupada
g = nueva(Reloj(), max_por_seg=1000, fallos_para_pausar=1, pausa=60)
ok(g.ejecutar(lambda x: time.sleep(0.05) or 1, 0, max_seg=0.01) == 1 and g.en_pausa(),
   "una grafica muy lenta entrega el resultado y se pausa")

# --- Detector con proveedor falso: grafica si hay turno, procesador si no, y resultado igual
det = object.__new__(percepcion.Detector)
det._gpu_probada = True
det.ms_cpu, det.ms_gpu = 60, 4
det.dispositivo = "CPU"
llamadas = {"cpu": 0, "gpu": 0}


def cpu(x):
    llamadas["cpu"] += 1
    return "salida"


def gpu_ok(x):
    llamadas["gpu"] += 1
    return "salida"


det._correr_cpu = cpu
det._gpu = ("Falsa", gpu_ok)
gc._unica = nueva(time.time, max_por_seg=1000)
x = np.zeros((1, 3, 4, 4), np.float32)
gc.poner_usar_gpu(True)
ok(det._correr(x) == "salida" and det.dispositivo == "GPU", "detector: con proveedor falso usa la grafica")
gc.poner_usar_gpu(False)
ok(det._correr(x) == "salida" and det.dispositivo == "CPU", "detector: interruptor apagado -> procesador, en caliente")
gc.poner_usar_gpu(True)
det._gpu = ("Falsa", roto)
ok(det._correr(x) == "salida" and det.dispositivo == "CPU", "detector: la grafica falla -> procesador, sin romper")
ok(llamadas["gpu"] == 1, "la grafica solo se uso cuando tocaba")

# --- preferencia persistente
gc.poner_usar_gpu(False)
gc._pref.update(t=0.0, mtime=None, usar=True)
ok(gc.usar_gpu() is False, "el interruptor se guarda en disco y se relee")
gc.poner_usar_gpu(True)

print("\nTODO BIEN" if not fallos else f"\n{fallos} FALLO(S)")
sys.exit(1 if fallos else 0)
