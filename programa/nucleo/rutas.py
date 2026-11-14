"""Carpetas del programa y de los datos del usuario."""
from __future__ import annotations

import os

#  la carpeta "programa" (la que tiene main.py)
PROGRAMA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#  imagenes de referencia del bot (plantillas, iconos)
RECURSOS = os.path.join(PROGRAMA, "recursos")


def carpeta_datos() -> str:
    """Datos del usuario (ajustes, estadisticas, capturas, errores), FUERA de
    la carpeta del bot: %LOCALAPPDATA%\\NovaBot."""
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".novabot")
    return os.path.join(base, "NovaBot")


def carpeta_diag() -> str:
    """Capturas de diagnostico, FUERA de la carpeta del bot."""
    return os.path.join(carpeta_datos(), "diag")


#  carpetas de diagnostico ya vaciadas en esta ejecucion (ver tareas/base.py)
_DIAG_LIMPIO: set = set()


def podar(carpeta: str, maximo: int, extensiones=(".png", ".jpg")) -> None:
    """Deja en la carpeta solo las `maximo` imagenes mas recientes."""
    try:
        fotos = [os.path.join(carpeta, f) for f in os.listdir(carpeta)
                 if f.lower().endswith(extensiones)]
        if len(fotos) <= maximo:
            return
        fotos.sort(key=os.path.getmtime)
        for f in fotos[:len(fotos) - maximo]:
            try:
                os.remove(f)
            except OSError:
                pass
    except OSError:
        pass
