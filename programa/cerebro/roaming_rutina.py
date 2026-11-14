"""Roaming Test dentro de la Rutina: abre el minijuego desde la lista de
eventos (Neural Roaming > boton «Roaming Test»), juega los tickets que diga
Ajustes y vuelve a la base.

La tarea suelta «Roaming Test» (tareas/roaming.py) necesita el tablero ya
abierto; aqui se llega solo. Los unicos toques fuera del minijuego son abrir
la lista de eventos, la tarjeta del evento, el boton «Roaming Test» y la X
para salir.
"""
from __future__ import annotations

import time

from cerebro.lector_eventos import LectorEventos
from tareas import roaming
from vision.plantillas import localizar

EVENTO = "Neural Roaming"


class RoamingRutina(LectorEventos):
    NOMBRE = "Roaming Test"
    UMBRAL_BOTON = 0.80

    def __init__(self, ctrl, log=None, stop=None, diag=True, tickets: int = 0):
        super().__init__(ctrl, log=log, stop=stop, diag=diag)
        self.tickets = max(0, int(tickets or 0))
        self.status.update({"partidas": 0})

    def _abrir_minijuego(self) -> bool:
        if not self.ir_a_base():
            self.log("  No encuentro la base.")
            return False
        if not self._abrir_lista():
            self.log("  No se ha abierto la lista de eventos.")
            return False
        r = self._abrir_evento(EVENTO)
        if r is None:
            self.log(f"  No encuentro el evento «{EVENTO}» (puede que haya acabado).")
            return False
        for _ in range(3):
            img = self.cap("roaming_evento")
            p, c, _ = localizar(img, "roaming_test")
            if p >= self.UMBRAL_BOTON:
                self.log("  Abro «Roaming Test».")
                self.ctrl.tap(c)
                time.sleep(3.0)
                return True
            time.sleep(1.5)
        self.log("  No veo el botón «Roaming Test» dentro del evento.")
        return False

    def run(self, ciclos: int = 1):
        self.status["estado"] = "abriendo Roaming Test"
        self.log(f"Roaming Test: juego {'todos los tickets' if not self.tickets else f'{self.tickets} ticket(s)'}.")
        try:
            if self._abrir_minijuego() and not self.parado():
                bot = roaming.Bot(self.ctrl, on_log=self._log, stop_event=self.stop)
                bot.run(games=self.tickets)
                self.status["partidas"] = bot.status.get("partida", 0)
                if bot.status.get("estado") in ("sin tablero",) and not self.status["partidas"]:
                    self.log("  Sin tickets o sin tablero: no hay partidas que jugar ahora.")
        finally:
            # cerrar el minijuego y el evento con su X, y volver a la base
            try:
                self._salir_a_lista()
                self._salir()
                self.volver_a_base()
            except Exception as e:                         # noqa: BLE001
                self.log(f"  Al salir del Roaming Test: {e}")
        self.status["estado"] = "terminado"
        self.log(f"Roaming Test: {self.status['partidas']} partida(s) jugada(s).")
