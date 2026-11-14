"""Registro central de errores de NovaBot.

Cada error se apunta en  %LOCALAPPDATA%\\NovaBot\\errores.jsonl  (una linea JSON
por error) con: fecha y hora, cuenta, plataforma, tarea, pantalla detectada,
accion que se intentaba, descripcion y, si se pudo, una captura en
%LOCALAPPDATA%\\NovaBot\\errores\\ . Es seguro desde varios procesos a la vez
(cada error es una sola escritura al final del archivo) y no lanza nunca
excepciones: un fallo al diagnosticar no debe tumbar la tarea.
"""
import json
import os
import time

PLATAFORMA = "Android (BlueStacks)"
MAX_BYTES = 2_000_000          # al pasar de aqui se archiva el registro viejo
MAX_CAPTURAS = 120


def carpeta() -> str:
    from nucleo.rutas import carpeta_datos
    return carpeta_datos()


def ruta_registro() -> str:
    return os.path.join(carpeta(), "errores.jsonl")


def _rotar(ruta):
    try:
        if os.path.getsize(ruta) > MAX_BYTES:
            os.replace(ruta, ruta + ".1")
    except OSError:
        pass


def _limpiar_capturas(dir_cap):
    try:
        fich = sorted(os.listdir(dir_cap))
        for f in fich[:-MAX_CAPTURAS]:
            os.remove(os.path.join(dir_cap, f))
    except OSError:
        pass


def registrar(descripcion, cuenta="", tarea="", pantalla="", accion="", img=None,
              nivel="error", plataforma=PLATAFORMA, ruta=None):
    """Apunta un error. Devuelve el diccionario guardado (o None si falla)."""
    try:
        ahora = time.time()
        fila = {"t": ahora, "hora": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ahora)),
                "nivel": nivel, "cuenta": str(cuenta), "plataforma": plataforma,
                "tarea": str(tarea), "pantalla": str(pantalla), "accion": str(accion),
                "error": str(descripcion)[:1500], "captura": ""}
        base = os.path.dirname(ruta) if ruta else carpeta()
        if img is not None:
            try:
                import cv2
                dir_cap = os.path.join(base, "errores")
                os.makedirs(dir_cap, exist_ok=True)
                nombre = (time.strftime("%Y%m%d_%H%M%S", time.localtime(ahora))
                          + "_" + str(cuenta).replace(":", "_") + ".png")
                if cv2.imwrite(os.path.join(dir_cap, nombre), img):
                    fila["captura"] = os.path.join("errores", nombre)
                _limpiar_capturas(dir_cap)
            except Exception:                                # noqa: BLE001
                pass
        ruta = ruta or ruta_registro()
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        _rotar(ruta)
        with open(ruta, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
        return fila
    except Exception:                                        # noqa: BLE001
        return None


def ultimos(n=20, ruta=None):
    """Los n ultimos errores (mas reciente al final)."""
    try:
        with open(ruta or ruta_registro(), encoding="utf-8") as fh:
            lineas = fh.readlines()[-n:]
        out = []
        for ln in lineas:
            try:
                out.append(json.loads(ln))
            except ValueError:
                continue
        return out
    except OSError:
        return []
