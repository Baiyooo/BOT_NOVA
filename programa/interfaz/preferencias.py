"""Preferencias de la ventana (%LOCALAPPDATA%\\NovaBot\\ventana.json)."""
from __future__ import annotations

from nucleo import config


def _ruta_prefs():
    import os
    from nucleo.rutas import carpeta_datos
    return os.path.join(carpeta_datos(), "ventana.json")


def leer_prefs() -> dict:
    return config.leer_config(_ruta_prefs())


def guardar_prefs(d: dict):
    config.guardar_config(_ruta_prefs(), d)
