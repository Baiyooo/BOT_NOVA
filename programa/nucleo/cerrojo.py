"""Cerrojo entre procesos: que solo UNA cuenta a la vez elija y mande drones.

Es un archivo en %LOCALAPPDATA%\\NovaBot creado de forma atomica (O_EXCL): quien
lo crea tiene el turno. Caduca (por la hora de modificacion) para que un
proceso muerto no bloquee a los demas; mientras se tiene el turno, un hilo
latido lo renueva solo cada pocos segundos, asi que no hace falta acordarse
de renovar en las rutas largas. Es reentrante por cuenta: si la misma cuenta
lo pide dos veces (una funcion que llama a otra) solo se toma una vez, y si
la primera vez no lo consiguio, la segunda no vuelve a esperar.
"""
from __future__ import annotations

import os
import threading
import time
import uuid

from nucleo.rutas import carpeta_datos

CADUCIDAD_SEG = 90          # sin renovar durante tanto, se da por muerto
ESPERA_SEG = 45             # lo maximo que se espera el turno
LATIDO_SEG = 20             # cada cuanto renueva el hilo latido

#  (ruta, dueno) -> [veces pedido, tengo, evento de parada del latido, token]
_estado: dict = {}
_mutex = threading.Lock()


def _ruta(nombre: str) -> str:
    return os.path.join(carpeta_datos(), f"cerrojo_{nombre}.lock")


def _contenido(ruta: str) -> str | None:
    try:
        with open(ruta, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return None


class Cerrojo:
    """Uso: `with Cerrojo("drones", cuenta, parado=self.parado) as c: ...`
    `c.tengo` dice si se consiguio el turno (si se agota la espera se sigue
    igualmente, sin turno: mejor eso que quedarse parado para siempre)."""

    def __init__(self, nombre: str, dueno, espera: float = ESPERA_SEG, parado=None,
                 caducidad: float = CADUCIDAD_SEG, log=None, latido: float = LATIDO_SEG):
        self.ruta = _ruta(nombre)
        self.dueno = str(dueno)
        self.espera, self.caducidad, self.latido = espera, caducidad, latido
        self.parado = parado or (lambda: False)
        self.log = log
        self.tengo = False
        self._token = f"{self.dueno}|{os.getpid()}|{uuid.uuid4().hex[:8]}"
        self._clave = (self.ruta, self.dueno)
        self._pedido = False

    # -- fichero ---------------------------------------------------------
    def _crear(self) -> bool:
        try:
            os.makedirs(os.path.dirname(self.ruta), exist_ok=True)
            fd = os.open(self.ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except OSError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(self._token)
        return True

    def _caducado(self) -> bool:
        try:
            return time.time() - os.path.getmtime(self.ruta) > self.caducidad
        except OSError:
            return False                    # ya no existe: se reintenta crear

    def _quitar_caducado(self) -> bool:
        """Retira un lock caducado sin carreras: se vuelve a comprobar que
        sigue caducado y con el mismo contenido, se renombra (atomico) a un
        nombre unico y se borra ese. Devuelve False si no se pudo."""
        visto = _contenido(self.ruta)
        if visto is None or not self._caducado() or _contenido(self.ruta) != visto:
            return True                     # ya cambio: que se reintente el bucle
        viejo = f"{self.ruta}.{os.getpid()}.{uuid.uuid4().hex[:8]}.viejo"
        try:
            os.replace(self.ruta, viejo)
        except OSError:
            return False
        try:
            os.remove(viejo)
        except OSError:
            pass                            # queda un .viejo suelto, no molesta
        return True

    # -- tomar / soltar --------------------------------------------------
    def adquirir(self) -> bool:
        with _mutex:
            est = _estado.get(self._clave)
            if est is not None:             # ya pedido por esta cuenta: sin segunda espera
                est[0] += 1
                self._pedido, self.tengo = True, est[1]
                return self.tengo
        fin = time.time() + self.espera
        avisado, conseguido = False, False
        while True:
            if self._crear():
                conseguido = True
                break
            if self._caducado() and self._quitar_caducado():
                continue                    # si no se pudo quitar, espera 0.5 s abajo
            if self.parado() or time.time() >= fin:
                break
            if not avisado and self.log:
                self.log("  Otra cuenta esta mandando drones: espero mi turno.")
                avisado = True
            time.sleep(0.5 if self._caducado() else 1.0)
        parar = None
        if conseguido:
            parar = threading.Event()
            threading.Thread(target=self._latir, args=(parar,), daemon=True,
                             name="latido-cerrojo").start()
        with _mutex:
            _estado[self._clave] = [1, conseguido, parar, self._token]
        self._pedido, self.tengo = True, conseguido
        return conseguido

    def _latir(self, parar: threading.Event):
        while not parar.wait(self.latido):
            try:
                os.utime(self.ruta, None)
            except OSError:
                pass

    def renovar(self):
        if self.tengo:
            try:
                os.utime(self.ruta, None)
            except OSError:
                pass

    def soltar(self):
        if not self._pedido:
            return
        self._pedido = False
        tenia = self.tengo
        self.tengo = False
        with _mutex:
            est = _estado.get(self._clave)
            if est is None:
                return
            est[0] -= 1
            if est[0] > 0:
                return
            _estado.pop(self._clave, None)
        if est[2] is not None:
            est[2].set()
        if tenia and _contenido(self.ruta) == est[3]:
            try:
                os.remove(self.ruta)
            except OSError:
                pass

    def __enter__(self):
        self.adquirir()
        return self

    def __exit__(self, *exc):
        self.soltar()
        return False
