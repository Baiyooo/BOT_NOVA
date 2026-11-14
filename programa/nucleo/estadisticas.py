"""Estadisticas historicas de NovaBot, por cuenta y por dia.

Se guardan en %LOCALAPPDATA%\\NovaBot\\estadisticas.json (guardado atomico, ver
config.py), con esta forma:
    {"_v": 1, "dias": {"2026-10-30": {"127.0.0.1:5555": {"sigilo": 21, ...}}}}
Claves que se cuentan: sigilo (piratas de sigilo atacados), normales (piratas
normales atacados), encontrados, recompensas (recogidas), ok (pasos correctos),
errores, segundos (tiempo activo), ballenas (muertas) y gemas (recogidas).
Varias cuentas son procesos distintos que escriben a la vez: cada anotacion
relee el archivo, suma y guarda, con un cerrojo de archivo.
"""
import os
import time

from nucleo import config

CLAVES = ("sigilo", "normales", "encontrados", "recompensas", "ok", "errores", "segundos",
          "ballenas", "gemas")
MAX_DIAS = 400


def ruta() -> str:
    from nucleo.rutas import carpeta_datos
    return os.path.join(carpeta_datos(), "estadisticas.json")


def dia_actual() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


def _cerrojo(r):
    fd = None
    fin = time.time() + 3.0
    while time.time() < fin:
        try:
            fd = os.open(r + ".lock", os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            return fd
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(r + ".lock") > 10:
                    os.remove(r + ".lock")
            except OSError:
                pass
            time.sleep(0.05)
        except OSError:
            return None
    return None


def sumar(cuenta: str, clave: str, n=1, dia=None, archivo=None) -> bool:
    """Suma n a una clave de una cuenta en el dia indicado (hoy por defecto).
    Nunca lanza excepciones."""
    if not n:
        return True
    try:
        r = archivo or ruta()
        os.makedirs(os.path.dirname(r), exist_ok=True)
        fd = _cerrojo(r)
        try:
            d = config.leer_config(r)
            dias = d.setdefault("dias", {})
            fila = dias.setdefault(dia or dia_actual(), {}).setdefault(str(cuenta), {})
            fila[clave] = round(fila.get(clave, 0) + n, 1) if clave == "segundos" else int(fila.get(clave, 0) + n)
            if len(dias) > MAX_DIAS:
                for k in sorted(dias)[:len(dias) - MAX_DIAS]:
                    dias.pop(k, None)
            return config.guardar_config(r, d)
        finally:
            if fd is not None:
                os.close(fd)
                try:
                    os.remove(r + ".lock")
                except OSError:
                    pass
    except Exception:                                        # noqa: BLE001
        return False


def leer(archivo=None) -> dict:
    return config.leer_config(archivo or ruta()).get("dias", {})


def resumen(dias_atras=7, archivo=None, hasta=None) -> dict:
    """Totales por cuenta y por dia de los ultimos `dias_atras` dias.
    Devuelve {"cuentas": {cuenta: {clave: total}}, "por_dia": {dia: {clave: total}},
    "total": {clave: total}}."""
    dias = leer(archivo)
    fin = hasta or time.time()
    validos = {time.strftime("%Y-%m-%d", time.localtime(fin - i * 86400)) for i in range(dias_atras)}
    cuentas, por_dia, total = {}, {}, {}
    for dia, cs in dias.items():
        if dia not in validos:
            continue
        for cuenta, fila in cs.items():
            for k, v in fila.items():
                for dest in (cuentas.setdefault(cuenta, {}), por_dia.setdefault(dia, {}), total):
                    dest[k] = dest.get(k, 0) + v
    return {"cuentas": cuentas, "por_dia": por_dia, "total": total}


def formato_tiempo(seg) -> str:
    seg = int(seg or 0)
    return f"{seg // 3600} h {seg % 3600 // 60:02d} min"
