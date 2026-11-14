"""Reserva compartida de piratas normales entre cuentas (archivo comun).

Antes de pulsar Atacar, la cuenta reserva el pirata aqui; otra cuenta que
abra ese mismo pirata lo salta. La reserva caduca en unos minutos (lo que
tarda en morir). El leer-modificar-guardar va bajo un Cerrojo corto para que
dos hilos o procesos no se pisen; sin el turno, no se escribe nada.

Identificador: el juego no da coordenadas de sistema del pirata (el panel solo
trae nombre y FUERZA) y la vista puede diferir algo entre cuentas. Por eso la
FUERZA es el identificador principal: si las dos cuentas la leyeron, es el
mismo pirata si la fuerza coincide (tolerancia 1 %) y la posicion en pantalla
esta a menos de 250 px (laxa). La posicion estricta (45 px) solo se usa si
ninguna de las dos tiene fuerza; si solo una la tiene, 30 px.
"""
from __future__ import annotations

import os
import time

from nucleo import config
from nucleo.cerrojo import Cerrojo
from nucleo.rutas import carpeta_datos

RESERVA_SEG = 240          # lo que dura la reserva de un pirata atacado
RADIO = 45                 # px (1600x900): mismo pirata por posicion, sin fuerza en ninguna
RADIO_FUERZA = 250         # px: con la misma fuerza, el mismo pirata aunque la vista difiera
RADIO_UNA_FUERZA = 30      # px: solo una de las dos cuentas leyo la fuerza
TOLERANCIA_FUERZA = 0.01   # diferencia relativa de fuerza que aun cuenta como igual


def _ruta() -> str:
    return os.path.join(carpeta_datos(), "piratas_reservas.json")


def _vigentes(ahora=None) -> list:
    ahora = ahora or time.time()
    d = config.leer(_ruta(), defecto=[])
    if not isinstance(d, list):
        return []
    return [r for r in d if isinstance(r, dict) and r.get("hasta", 0) > ahora]


def _misma_fuerza(a, b) -> bool:
    return bool(a and b and abs(a - b) <= TOLERANCIA_FUERZA * max(a, b))


def es_el_mismo(r: dict, pos, fuerza) -> bool:
    """¿La reserva `r` es de este pirata (pos en 1600x900, fuerza o None)?"""
    dx, dy = abs(r["x"] - pos[0]), abs(r["y"] - pos[1])
    fr = r.get("fuerza")
    if fr and fuerza:
        return _misma_fuerza(fr, fuerza) and dx <= RADIO_FUERZA and dy <= RADIO_FUERZA
    radio = RADIO if not fr and not fuerza else RADIO_UNA_FUERZA
    return dx <= radio and dy <= radio


def reservado_por_otro(cuenta, pos, fuerza=None) -> bool:
    return any(str(r.get("cuenta")) != str(cuenta) and es_el_mismo(r, pos, fuerza)
               for r in _vigentes())


def reservar(cuenta, pos, fuerza=None, seg: float = RESERVA_SEG, parado=None, log=None) -> bool:
    """Reserva el pirata para `cuenta`. False si otra cuenta ya lo tenia o no
    se consiguio el turno (en ambos casos no se escribe y hay que saltarlo)."""
    with Cerrojo("piratas_reservas", cuenta, espera=8, parado=parado, log=log) as cj:
        if not cj.tengo:
            return False
        ahora = time.time()
        lista = _vigentes(ahora)
        if any(str(r.get("cuenta")) != str(cuenta) and es_el_mismo(r, pos, fuerza)
               for r in lista):
            return False
        lista = [r for r in lista
                 if not (str(r.get("cuenta")) == str(cuenta) and es_el_mismo(r, pos, fuerza))]
        lista.append({"x": int(pos[0]), "y": int(pos[1]), "fuerza": fuerza,
                      "cuenta": str(cuenta), "hasta": ahora + seg})
        return config.guardar(_ruta(), lista)


def liberar(cuenta, pos, fuerza=None, parado=None) -> bool:
    """Quita la reserva propia (no se llego a atacar). False si no se consiguio
    el turno: no se escribe y quien llama puede reintentarlo."""
    with Cerrojo("piratas_reservas", cuenta, espera=8, parado=parado) as cj:
        if not cj.tengo:
            return False
        lista = [r for r in _vigentes()
                 if not (str(r.get("cuenta")) == str(cuenta) and es_el_mismo(r, pos, fuerza))]
        return config.guardar(_ruta(), lista)


def leer_fuerza(img) -> int | None:
    """Fuerza del pirata seleccionado: la cifra de la fila justo debajo de
    «Fuerza» (la mas cercana en vertical y alineada)."""
    try:
        from cerebro.memoria_eventos import numero
        from vision import ocr
        h, w = img.shape[:2]
        items = ocr.leer(img, (0.1, 0.35, 0.6, 0.65))
        for d in items:
            if "fuerza" in ocr.normal(d["texto"]):
                x, y = d["centro"]
                mejor = None                  # (distancia vertical, cifra)
                for e in items:
                    n = numero(e["texto"])
                    dy = e["centro"][1] - y
                    if (n and n >= 1000 and 0 < dy < h * 0.1
                            and abs(e["centro"][0] - x) < w * 0.15
                            and (mejor is None or dy < mejor[0])):
                        mejor = (dy, n)
                return mejor[1] if mejor else None
    except Exception:                                          # noqa: BLE001
        pass
    return None


def con_flota_aliada(img) -> bool:
    """El panel muestra «Flota aliada» con flotas atacandolo (como en ballenas)."""
    try:
        from tareas.ballenas.atacar import _Atacar
        return bool(_Atacar.ocupada_por_otro(img))
    except Exception:                                          # noqa: BLE001
        return False
