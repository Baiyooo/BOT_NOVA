"""Imagenes de referencia del bot (plantillas), guardadas como PNG en la
carpeta `programa/recursos/` en vez de metidas en el codigo en base64.

    silueta(nombre)        -> mapa de bits 0/1 (uint8) de recursos/rotulos/<nombre>.png
    muestras_cifras()      -> [(caracter, archivo, proporcion)] de recursos/cifras
    silueta_cifra(archivo) -> mapa de bits 0/1 de una muestra de cifra
    imagen(*partes, gris)  -> imagen BGR (o gris) de recursos/<partes...>
    archivos(*carpeta)     -> nombres de los PNG de una carpeta, ordenados
"""
from __future__ import annotations

import json
import os

import cv2
import numpy as np

RAIZ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "recursos")

_SILUETAS: dict = {}


def ruta(*partes) -> str:
    return os.path.join(RAIZ, *partes)


def _leer(ruta_png: str, flags: int) -> np.ndarray:
    # np.fromfile + imdecode: funciona aunque la ruta tenga tildes o eñes
    im = cv2.imdecode(np.fromfile(ruta_png, np.uint8), flags)
    if im is None:
        raise FileNotFoundError(f"No puedo leer la plantilla {ruta_png}")
    return im


def imagen(*partes, gris: bool = False) -> np.ndarray:
    return _leer(ruta(*partes), cv2.IMREAD_GRAYSCALE if gris else cv2.IMREAD_COLOR)


def archivos(*carpeta) -> list[str]:
    try:
        return sorted(f for f in os.listdir(ruta(*carpeta)) if f.lower().endswith(".png"))
    except OSError:
        return []


def _bits(ruta_png: str) -> np.ndarray:
    return (_leer(ruta_png, cv2.IMREAD_GRAYSCALE) > 127).astype(np.uint8)


def silueta(nombre: str) -> np.ndarray:
    m = _SILUETAS.get(nombre)
    if m is None:
        m = _SILUETAS[nombre] = _bits(ruta("rotulos", nombre + ".png"))
    return m.copy()


def muestras_cifras() -> list[tuple[str, str, float]]:
    with open(ruta("cifras", "muestras.json"), encoding="utf-8") as fh:
        return [(c, a, float(p)) for c, a, p in json.load(fh)["muestras"]]


def silueta_cifra(archivo: str) -> np.ndarray:
    return _bits(ruta("cifras", archivo))
