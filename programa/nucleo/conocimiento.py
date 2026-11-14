"""Conocimiento del bot: lo que ha aprendido jugando y que forma parte del
programa (viaja en la carpeta y en el paquete que se exporta), para que una
instalacion nueva no empiece de cero.

    programa/conocimiento/
        experiencia.json   escalas de los botones por resolucion, sitios donde
                           suele salir el pirata de sigilo, aciertos
        eventos.json       lo que pide cada evento (sus misiones), sin progreso
        novabot_det.onnx   el detector de objetos (ballena, gema, flota, pirata)

Aqui NO hay nada de nadie: ni nombres de cuentas, ni progreso, ni capturas.
Las capturas, registros, ajustes y el progreso de cada cuenta se quedan en
%LOCALAPPDATA%\\NovaBot, en el PC de cada uno.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading

from nucleo.rutas import PROGRAMA, carpeta_datos

CARPETA = os.path.join(PROGRAMA, "conocimiento")
EXPERIENCIA = "experiencia.json"
EVENTOS = "eventos.json"
MODELO = "novabot_det.onnx"
#  campos de un evento que son conocimiento (lo demas es de la partida de cada uno)
_CAMPOS_EVENTO = ("nombre", "misiones", "lector_v")
_CAMPOS_MISION = ("id", "texto", "meta")
_cerrojo = threading.Lock()


def ruta(nombre: str) -> str:
    return os.path.join(CARPETA, nombre)


def _leer(r, defecto):
    try:
        with open(r, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, type(defecto)) else defecto
    except (OSError, ValueError):
        return defecto


def _escribir(r, datos):
    os.makedirs(os.path.dirname(r), exist_ok=True)
    tmp = f"{r}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, indent=1, sort_keys=True, ensure_ascii=False)
    os.replace(tmp, r)


# ------------------------------------------------------------ experiencia --
def ruta_experiencia() -> str:
    """conocimiento/experiencia.json. La primera vez se trae la de la version
    anterior (programa/experiencia.json)."""
    nueva = ruta(EXPERIENCIA)
    vieja = os.path.join(PROGRAMA, EXPERIENCIA)
    if not os.path.exists(nueva) and os.path.exists(vieja):
        try:
            os.makedirs(CARPETA, exist_ok=True)
            shutil.move(vieja, nueva)
        except OSError:
            return nueva if os.path.exists(nueva) else vieja    # otro proceso ya la movio
    return nueva


def fusionar_experiencia(local: dict, llega: dict) -> dict:
    """Junta la experiencia de este PC con la que trae un paquete: lo de aqui
    manda (escalas), y de los contadores se queda el mayor."""
    out = {"version": 1, "escalas": {}, "pirata": {}, "cuentas": {}}
    for d in (llega, local):                       # local despues: gana en las escalas
        for k, v in (d.get("escalas") or {}).items():
            out["escalas"][k] = v
    for campo in ("pirata", "cuentas"):
        for d in (llega, local):
            for k, v in (d.get(campo) or {}).items():
                ant = out[campo].get(k)
                if ant is None:
                    out[campo][k] = v
                elif isinstance(v, list) and isinstance(ant, list):
                    out[campo][k] = [max(a, b) for a, b in zip(ant, v)]
                elif isinstance(v, (int, float)) and isinstance(ant, (int, float)):
                    out[campo][k] = max(ant, v)
    return out


# ---------------------------------------------------------------- eventos --
_RUIDO = re.compile(r"^\s*(activo|active)\b|\d+\s*:\s*\d{2}\s*:\s*\d{2}", re.I)


def _limpiar_evento(e: dict) -> dict:
    """Solo lo que pide el evento: fuera horas, cuentas atras y progreso."""
    out = {k: e[k] for k in _CAMPOS_EVENTO if k in e}
    if isinstance(out.get("misiones"), list):
        out["misiones"] = [{k: m[k] for k in _CAMPOS_MISION if k in m and m[k] is not None}
                           for m in out["misiones"] if isinstance(m, dict) and m.get("texto")
                           and not _RUIDO.search(str(m["texto"]))]
    return out


def eventos() -> dict:
    """Lo que pide cada evento, aprendido antes (en este PC o en otro)."""
    return _leer(ruta(EVENTOS), {}).get("eventos", {}) if os.path.exists(ruta(EVENTOS)) else {}


def apuntar_eventos(ev: dict) -> None:
    """Guarda en el conocimiento las misiones de los eventos ya leidos (solo
    los requisitos, nunca el progreso ni las horas)."""
    nuevos = {k: _limpiar_evento(e) for k, e in (ev or {}).items() if e.get("misiones")}
    if not nuevos:
        return
    with _cerrojo:
        actual = eventos()
        cambia = False
        for k, e in nuevos.items():
            if actual.get(k) != e:
                actual[k] = e
                cambia = True
        if cambia:
            try:
                _escribir(ruta(EVENTOS), {"version": 1, "eventos": actual})
            except OSError:
                pass


def fusionar_eventos(local: dict, llega: dict) -> dict:
    out = dict((llega or {}).get("eventos", {}))
    out.update((local or {}).get("eventos", {}))           # lo leido aqui manda
    return {"version": 1, "eventos": out}


# ----------------------------------------------------------------- modelo --
def rutas_modelo() -> list[str]:
    """Donde puede estar el detector: el entrenado en este PC (datos) y el
    que trae el programa. Primero el mas reciente."""
    rs = [os.path.join(carpeta_datos(), "modelos", MODELO), ruta(MODELO),
          os.path.join(PROGRAMA, "modelos", MODELO)]
    rs = [r for r in rs if os.path.exists(r)]
    return sorted(rs, key=os.path.getmtime, reverse=True)


def preparar_paquete(log=print) -> None:
    """Antes de exportar: deja en conocimiento/ lo ultimo aprendido (el modelo
    mas reciente de este PC y la experiencia)."""
    os.makedirs(CARPETA, exist_ok=True)
    ruta_experiencia()
    mod = rutas_modelo()
    if mod and os.path.abspath(mod[0]) != os.path.abspath(ruta(MODELO)):
        try:
            shutil.copy2(mod[0], ruta(MODELO))
            log("Conocimiento: incluyo el detector entrenado en este PC.")
        except OSError as e:
            log(f"Conocimiento: no he podido copiar el detector ({e}).")
    try:                                    # misiones que haya en los datos y aun no esten
        from nucleo import config as _cfg
        from cerebro.memoria_eventos import fusionar
        ev = _cfg.leer(os.path.join(carpeta_datos(), "eventos_juego.json"), defecto={}).get("eventos", {})
        apuntar_eventos(fusionar(ev))           # sin duplicados ni nombres mal leidos
    except Exception:                                         # noqa: BLE001
        pass
