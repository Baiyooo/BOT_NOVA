"""Uso COMPARTIDO y limitado de la grafica para el detector.

Las cuentas pueden ser hilos (menu de texto) o procesos (ventana), asi que el
turno se coordina entre procesos con un mutex con nombre de Windows (lo suelta
solo el sistema si un proceso muere) y, sin Windows, con un cerrojo de hilos.
Reglas:
  - un solo uso de la grafica a la vez en todo el PC (el que no consigue turno
    en un instante, usa el procesador: nunca espera);
  - como mucho MAX_POR_SEG imagenes por segundo entre todas las cuentas (la
    hora de la ultima se guarda en un archivo compartido);
  - si falla o tarda demasiado varias veces seguidas (la grafica ocupada, el
    usuario jugando), se pausa su uso un rato y se vuelve al procesador;
  - interruptor persistente «usar_gpu» (por defecto activado; solo es efectivo
    si midiendo compensa) que se aplica en caliente en todos los procesos.
"""
from __future__ import annotations

import os
import threading
import time

from nucleo import config
from nucleo.rutas import carpeta_datos

MAX_POR_SEG = 3.5            # imagenes por segundo, sumando todas las cuentas
ESPERA_TURNO = 0.05          # lo que se espera el turno antes de usar el procesador
FALLOS_PARA_PAUSAR = 3       # fallos o lentitudes seguidas hasta pausar
PAUSA_SEG = 60.0             # cuanto se deja la grafica tras esos fallos
REVISAR_PREF_SEG = 2.0       # cada cuanto se relee la preferencia del disco


# ---- preferencia persistente --------------------------------------------
def _ruta_pref() -> str:
    return os.path.join(carpeta_datos(), "gpu.json")


_pref = {"t": 0.0, "mtime": None, "usar": True}
_pref_cerrojo = threading.Lock()


def usar_gpu() -> bool:
    """Interruptor del usuario (True por defecto). Se relee del disco cada pocos
    segundos para que un cambio hecho en otro proceso se aplique en caliente."""
    ahora = time.monotonic()
    with _pref_cerrojo:
        if ahora - _pref["t"] >= REVISAR_PREF_SEG:
            _pref["t"] = ahora
            try:
                mt = os.path.getmtime(_ruta_pref())
            except OSError:
                mt = None
            if mt != _pref["mtime"] or mt is None:
                _pref["mtime"] = mt
                _pref["usar"] = bool(config.leer_config(_ruta_pref()).get("usar_gpu", True))
        return _pref["usar"]


def poner_usar_gpu(valor: bool) -> bool:
    """Guarda el interruptor y lo aplica ya en este proceso."""
    valor = bool(valor)
    datos = config.leer_config(_ruta_pref())
    datos["usar_gpu"] = valor
    ok = config.guardar_config(_ruta_pref(), datos)
    with _pref_cerrojo:
        _pref["usar"] = valor
        _pref["t"] = time.monotonic()
        try:
            _pref["mtime"] = os.path.getmtime(_ruta_pref())
        except OSError:
            _pref["mtime"] = None
    return ok


# ---- turno entre procesos --------------------------------------------------
class CandadoLocal:
    """Cerrojo de hilos (sin Windows, o para pruebas)."""

    def __init__(self):
        self._c = threading.Lock()

    def adquirir(self, espera: float) -> bool:
        return self._c.acquire(timeout=max(espera, 0.0))

    def soltar(self):
        self._c.release()


class CandadoWindows:
    """Mutex con nombre: vale entre procesos e hilos; lo libera el sistema si
    el dueno muere. Se pide y se suelta desde el mismo hilo."""

    def __init__(self, nombre="NovaBot_gpu_turno"):
        import ctypes
        self._k = ctypes.windll.kernel32
        self._k.CreateMutexW.restype = ctypes.c_void_p
        self._k.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        self._k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self._k.ReleaseMutex.argtypes = [ctypes.c_void_p]
        self._h = self._k.CreateMutexW(None, 0, nombre)
        if not self._h:
            raise OSError("no se pudo crear el mutex")

    def adquirir(self, espera: float) -> bool:
        r = self._k.WaitForSingleObject(self._h, int(max(espera, 0.0) * 1000))
        return r in (0, 0x80)               # WAIT_OBJECT_0 o WAIT_ABANDONED

    def soltar(self):
        self._k.ReleaseMutex(self._h)


class AlmacenArchivo:
    """Hora de la ultima imagen enviada a la grafica, compartida entre procesos."""

    def __init__(self, ruta=None):
        self.ruta = ruta or os.path.join(carpeta_datos(), "gpu_ultimo.txt")

    def leer(self) -> float:
        try:
            with open(self.ruta, encoding="utf-8") as fh:
                return float(fh.read().strip() or 0)
        except (OSError, ValueError):
            return 0.0

    def poner(self, t: float):
        try:
            os.makedirs(os.path.dirname(self.ruta), exist_ok=True)
            with open(self.ruta, "w", encoding="utf-8") as fh:
                fh.write(repr(t))
        except OSError:
            pass


class AlmacenMemoria:
    def __init__(self):
        self.t = 0.0

    def leer(self) -> float:
        return self.t

    def poner(self, t: float):
        self.t = t


def _candado_por_defecto():
    if os.name == "nt":
        try:
            return CandadoWindows()
        except Exception:                                     # noqa: BLE001
            pass
    return CandadoLocal()


class GpuCompartida:
    """Puerta unica a la grafica: `ejecutar(f, x)` la usa si hay turno, no se
    pasa del limite y no esta en pausa; si no, devuelve None y quien llama usa
    el procesador. Nunca lanza excepciones."""

    def __init__(self, candado=None, almacen=None, reloj=time.time,
                 max_por_seg=MAX_POR_SEG, espera=ESPERA_TURNO,
                 fallos_para_pausar=FALLOS_PARA_PAUSAR, pausa=PAUSA_SEG):
        self.candado = candado or _candado_por_defecto()
        self.almacen = almacen or AlmacenArchivo()
        self.reloj = reloj
        self.intervalo = 1.0 / max_por_seg
        self.espera = espera
        self.fallos_para_pausar = fallos_para_pausar
        self.pausa = pausa
        self.fallos = 0
        self.hasta = 0.0                    # no se usa la grafica antes de esta hora
        self.motivo = ""

    def en_pausa(self) -> bool:
        return self.reloj() < self.hasta

    def _fallo(self, motivo: str):
        self.fallos += 1
        self.motivo = motivo
        if self.fallos >= self.fallos_para_pausar:
            self.hasta = self.reloj() + self.pausa
            self.fallos = 0
            self.motivo = f"{motivo}: pausada {int(self.pausa)} s"

    def ejecutar(self, f, x, max_seg: float | None = None):
        """Devuelve el resultado de f(x) en la grafica, o None si hay que usar
        el procesador. `max_seg`: si f tarda mas, cuenta como grafica ocupada."""
        if self.en_pausa():
            return None
        try:
            if not self.candado.adquirir(self.espera):
                self.motivo = "grafica en uso por otra cuenta"
                return None
        except Exception:                                     # noqa: BLE001
            return None
        try:
            ahora = self.reloj()
            if ahora - self.almacen.leer() < self.intervalo:
                self.motivo = "limite de imagenes por segundo"
                return None
            self.almacen.poner(ahora)
            t0 = time.perf_counter()
            try:
                y = f(x)
            except Exception as e:                            # noqa: BLE001
                self._fallo(f"error en la grafica ({type(e).__name__})")
                return None
            if max_seg is not None and time.perf_counter() - t0 > max_seg:
                self._fallo("grafica ocupada (va lenta)")
            else:
                self.fallos = 0
                self.motivo = ""
            return y
        finally:
            try:
                self.candado.soltar()
            except Exception:                                 # noqa: BLE001
                pass


_unica = None
_unica_cerrojo = threading.Lock()


def compartida() -> GpuCompartida:
    """La puerta de este proceso (el turno y el limite son de todo el PC)."""
    global _unica
    with _unica_cerrojo:
        if _unica is None:
            _unica = GpuCompartida()
        return _unica
