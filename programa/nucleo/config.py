"""Lectura y guardado SEGUROS de los archivos de datos de NovaBot (JSON).

- Guardado atomico: se escribe en un archivo temporal, se fuerza a disco y se
  renombra; si el equipo se apaga a mitad, el archivo anterior queda intacto.
- Copia de seguridad (.bak) del ultimo archivo bueno; si el principal esta
  corrupto o falta, se lee la copia en vez de empezar de cero en silencio.
- Version de configuracion ("_v") y migraciones, para poder cambiar el
  formato sin perder los datos de quien actualiza.
"""
import json
import os
import shutil

VERSION = 1


def _cargar(ruta):
    with open(ruta, encoding="utf-8") as fh:
        return json.load(fh)


def leer(ruta, defecto=None):
    """Devuelve el contenido de `ruta`; si esta corrupto, el de `ruta`.bak;
    si tampoco, `defecto` (un dict vacio si no se indica)."""
    if defecto is None:
        defecto = {}
    for r in (ruta, ruta + ".bak"):
        try:
            return _cargar(r)
        except (OSError, ValueError):
            continue
    return defecto


def guardar(ruta, datos, indent=None) -> bool:
    """Guarda `datos` de forma atomica. Devuelve False si no se pudo."""
    tmp = f"{ruta}.{os.getpid()}.tmp"
    try:
        os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(datos, fh, indent=indent)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        try:                                   # el ultimo bueno pasa a .bak
            _cargar(ruta)
            shutil.copy2(ruta, ruta + ".bak")
        except (OSError, ValueError):
            pass
        os.replace(tmp, ruta)
        return True
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def migrar(datos: dict) -> dict:
    """Pone al dia un diccionario guardado con una version anterior.
    Hoy solo existe la version 1: se le anota la version si no la tiene."""
    if not isinstance(datos, dict):
        return {}
    v = datos.get("_v", 0)
    # aqui ira:  if v < 2: ...  datos["_v"] = 2
    if v < 1:
        datos["_v"] = 1
    return datos


def leer_config(ruta) -> dict:
    return migrar(leer(ruta))


def guardar_config(ruta, datos: dict, indent=None) -> bool:
    datos = dict(datos)
    datos["_v"] = VERSION
    return guardar(ruta, datos, indent)
