"""Tarea mixta: piratas normales sin parar y, cada 30 min, los de sigilo."""
from __future__ import annotations

import time

from tareas.piratas.normales import PiratasNormales
from tareas.piratas.sigilo import PiratasSigilo


class PiratasMixto:
    """Piratas normales sin parar y, cada 30 min, los de sigilo con las
    busquedas de radar que haya (si no hay, lo deja enseguida y sigue con
    los normales)."""

    NOMBRE = "Piratas: sigilo + normales"
    CADA_SIGILO = 30 * 60

    def __init__(self, ctrl, log=None, stop=None, atacar=True, usar_salto=False):
        self.ctrl, self._log, self.stop = ctrl, log, stop
        self.atacar, self.usar_salto = atacar, usar_salto
        self.status = {"estado": "en espera", "ciclo": 0, "ciclos": 0, "encontrados": 0,
                       "atacados": 0, "normales": 0, "sigilo": 0}

    def log(self, m):
        if self._log:
            self._log(getattr(self.ctrl, "name", ""), m)

    def parado(self):
        return self.stop is not None and self.stop.is_set()

    def _sigilo(self):
        self.status["estado"] = "piratas de sigilo"
        t = PiratasSigilo(self.ctrl, log=self._log, stop=self.stop,
                          atacar=self.atacar, usar_salto=self.usar_salto)
        t.ESPERAR_BUSQUEDAS = False                 # sin busquedas: a los normales
        t.run(0)
        try:
            img = t.cap("fin_sigilo")               # no dejar el radar abierto
            if t.radar_abierto(img):
                t.atras(img)
        except Exception:                           # noqa: BLE001
            pass
        self.status["sigilo"] += t.status.get("atacados", 0)
        self.status["atacados"] = self.status["sigilo"]
        self.status["ciclo"] = self.status["normales"]

    def _normales(self, hasta):
        self.status["estado"] = "piratas normales"
        t = PiratasNormales(self.ctrl, log=self._log, stop=self.stop)
        base = t.parado
        t.parado = lambda: base() or time.time() >= hasta   # vuelve a la hora del sigilo
        t.status = self.status                      # el estado se ve en la ventana
        t.run(0, base=self.status["normales"])
        self.status["normales"] = self.status["ciclo"]

    def run(self, ciclos: int = 0):
        self.log("Piratas de sigilo cada 30 min y normales entre medias. "
                 "Para pararlo, pulsa Parar.")
        ultimo = 0.0
        while not self.parado():
            if time.time() - ultimo >= self.CADA_SIGILO:
                self._sigilo()
                ultimo = time.time()
            if self.parado():
                break
            self._normales(ultimo + self.CADA_SIGILO)
            if self.status.get("mision_hecha"):
                # mision de fuerza pirata hecha: solo sigilo, esperar al siguiente
                self.status["estado"] = "esperando (mision de piratas hecha)"
                while not self.parado() and time.time() < ultimo + self.CADA_SIGILO:
                    time.sleep(2)
        self.status["ciclo"] = self.status["normales"]
        self.status["atacados"] = self.status["sigilo"]
        self.status["estado"] = "parado"
