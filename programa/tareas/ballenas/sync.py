"""Coordinacion de las dos cuentas de ballenas por archivos compartidos."""
from __future__ import annotations

import os
import time

from nucleo import config as _cfg
from nucleo.rutas import carpeta_diag


def _carpeta_sync():
    d = os.path.join(os.path.dirname(carpeta_diag()), "ballenas")
    os.makedirs(d, exist_ok=True)
    return d


def puerto(nombre) -> str:
    return str(nombre).split(":")[-1]


def pedido_pendiente(yo, lider, maximo=900) -> bool:
    """La cuenta que invoca esta pidiendo ayuda a esta (para el planificador)."""
    if puerto(yo) == str(lider):
        return False
    d = _cfg.leer(os.path.join(_carpeta_sync(), f"{lider}.json"), defecto={})
    mio = _cfg.leer(os.path.join(_carpeta_sync(), f"{puerto(yo)}.json"), defecto={})
    return (d.get("fase") in ("pedido", "atacar") and time.time() - d.get("t", 0) < maximo
            and mio.get("presente") != d.get("ciclo"))


class Sync:
    """Archivos de coordinacion: ballenas/<puerto>.json, uno por cuenta."""

    def __init__(self, yo: str, otro: str):
        self.yo, self.otro = puerto(yo), puerto(otro)
        self.d = _carpeta_sync()

    def _ruta(self, p):
        return os.path.join(self.d, f"{p}.json")

    def leer(self, p=None) -> dict:
        return _cfg.leer(self._ruta(p or self.yo), defecto={})

    def escribir(self, **kw):
        d = self.leer()
        d.update(kw, t=time.time())
        _cfg.guardar(self._ruta(self.yo), d)

    def del_otro(self) -> dict:
        return self.leer(self.otro)

    def esperar(self, cond, segundos, parado, paso=0.5) -> dict | None:
        fin = time.time() + segundos
        while time.time() < fin:
            if parado():
                return None
            d = self.del_otro()
            if cond(d):
                return d
            time.sleep(paso)
        return None
