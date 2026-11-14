"""Experiencia: lo que el bot aprende al jugar (escalas de los botones por
resolucion, donde suele aparecer el pirata de sigilo, aciertos).
Se guarda en programa\\conocimiento\\experiencia.json para que viaje con la carpeta
y en el paquete que se exporta.
"""
from __future__ import annotations

from vision.plantillas import _ESCALAS


# ---------------------------------------------------------------------------
# Experiencia: lo que el bot aprende al jugar. Se guarda en
# programa\conocimiento\experiencia.json, DENTRO del bot, para que viaje
# cuando se pasa a otra persona. Solo numeros sin datos de nadie: escalas de
# los botones por resolucion, en que punto de la pantalla suele aparecer el
# pirata de sigilo y cuantas veces acierta cada cosa. Nunca capturas, nombres
# de cuentas ni progreso.
# ---------------------------------------------------------------------------
class Experiencia:
    def __init__(self):
        import threading
        from nucleo import conocimiento
        self.ruta = conocimiento.ruta_experiencia()          # programa/conocimiento/
        self.cerrojo = threading.Lock()
        self.datos = {"version": 1, "escalas": {}, "pirata": {}, "cuentas": {}}
        self.nuevo_pirata, self.nuevo_cuentas = {}, {}
        try:
            import json
            with open(self.ruta, encoding="utf-8") as fh:
                d = json.load(fh)
            if isinstance(d, dict):
                for k in self.datos:
                    if isinstance(d.get(k), type(self.datos[k])):
                        self.datos[k] = d[k]
        except (OSError, ValueError):
            pass
        # las escalas aprendidas se cargan en la cache de localizar
        for k, v in self.datos["escalas"].items():
            try:
                nombre, w, h = k.rsplit("|", 2)
                _ESCALAS[(nombre, int(w), int(h))] = float(v)
            except ValueError:
                pass

    def guardar(self):
        """Varias instancias (procesos) guardan a la vez: se relee el archivo
        y se le SUMA lo aprendido desde la ultima vez, para no pisarse."""
        import json
        import os
        with self.cerrojo:
            try:
                with open(self.ruta, encoding="utf-8") as fh:
                    disco = json.load(fh)
                if not isinstance(disco, dict):
                    disco = {}
            except (OSError, ValueError):
                disco = {}
            for k in ("escalas", "pirata", "cuentas"):
                if not isinstance(disco.get(k), dict):
                    disco[k] = {}
            disco["version"] = 1
            for (nombre, w, h), v in list(_ESCALAS.items()):
                disco["escalas"][f"{nombre}|{w}|{h}"] = round(v, 4)
            for k, v in self.nuevo_pirata.items():
                disco["pirata"][k] = disco["pirata"].get(k, 0) + v
            for k, (a, b) in self.nuevo_cuentas.items():
                c = disco["cuentas"].get(k, [0, 0])
                disco["cuentas"][k] = [c[0] + a, c[1] + b]
            self.nuevo_pirata, self.nuevo_cuentas = {}, {}
            self.datos = disco
            try:
                tmp = f"{self.ruta}.{os.getpid()}.tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(disco, fh, indent=1, sort_keys=True)
                os.replace(tmp, self.ruta)
            except OSError:
                pass

    def contar(self, clave: str, ok: bool):
        with self.cerrojo:
            c = self.datos["cuentas"].setdefault(clave, [0, 0])
            c[0 if ok else 1] += 1
            n = self.nuevo_cuentas.setdefault(clave, [0, 0])
            n[0 if ok else 1] += 1

    def pirata_encontrado(self, modo: str, dx: float, dy: float):
        """dx, dy: donde estaba el pirata respecto al punto de referencia, en
        fraccion de pantalla, redondeado a una rejilla de 2 %."""
        clave = f"{modo}|{round(dx / 0.02) * 0.02:.2f}|{round(dy / 0.02) * 0.02:.2f}"
        with self.cerrojo:
            p = self.datos["pirata"]
            p[clave] = p.get(clave, 0) + 1
            self.nuevo_pirata[clave] = self.nuevo_pirata.get(clave, 0) + 1

    def sitios_pirata(self, modo: str, n: int = 4):
        """Los n sitios donde mas veces ha aparecido, de mas a menos."""
        with self.cerrojo:
            items = [(v, k) for k, v in self.datos["pirata"].items()
                     if k.startswith(modo + "|")]
        items.sort(reverse=True)
        res = []
        for _, k in items[:n]:
            _, dx, dy = k.split("|")
            res.append((float(dx), float(dy)))
        return res


_EXP = None


def experiencia() -> Experiencia:
    global _EXP
    if _EXP is None:
        _EXP = Experiencia()
    return _EXP
