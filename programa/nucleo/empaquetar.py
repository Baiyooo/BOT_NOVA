"""Crea el paquete de actualizacion NovaBot-<version>.zip de la carpeta programa.

    python -m nucleo.empaquetar [carpeta_salida]     (desde programa; lo usa EMPAQUETAR.bat)

El zip lleva programa/manifiesto.json (con el SHA-256 de cada archivo) y el
codigo, los recursos, los textos y el conocimiento (programa/conocimiento:
lo aprendido jugando y el detector), para que el bot no empiece de cero en
otro equipo. Nunca lleva datos de nadie (ajustes, progreso, capturas,
registros), que viven en %LOCALAPPDATA%\\NovaBot, ni la carpeta pruebas.
Antes de crearlo comprueba que todo el codigo compila.
"""
from __future__ import annotations

import json
import os
import sys
import zipfile

from nucleo.actualizar import crear_manifiesto

PROGRAMA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUERA = ("pruebas/",)          # no viajan en el paquete


def version() -> str:
    ns = {}
    with open(os.path.join(PROGRAMA, "version.py"), encoding="utf-8") as fh:
        exec(fh.read(), ns)                                  # noqa: S102
    return str(ns.get("VERSION", "?"))


def crear(salida: str | None = None, log=print) -> str:
    """Crea el zip y devuelve su ruta."""
    v = version()
    from nucleo import conocimiento
    conocimiento.preparar_paquete(log)          # lo ultimo aprendido, dentro del paquete
    man = crear_manifiesto(PROGRAMA, v)
    man["archivos"] = {rel: sha for rel, sha in man["archivos"].items() if not rel.startswith(FUERA)}
    errores = []
    for rel in man["archivos"]:
        if rel.endswith(".py"):
            with open(os.path.join(PROGRAMA, *rel.split("/")), encoding="utf-8") as fh:
                try:
                    compile(fh.read(), rel, "exec")
                except SyntaxError as e:
                    errores.append(f"{rel}: {e}")
    if errores:
        raise SystemExit("No empaqueto: hay errores de sintaxis:\n  " + "\n  ".join(errores))
    salida = salida or os.path.join(os.path.dirname(PROGRAMA), "paquetes")
    os.makedirs(salida, exist_ok=True)
    ruta = os.path.join(salida, f"NovaBot-{v}.zip")
    tmp = ruta + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("programa/manifiesto.json", json.dumps(man, indent=1, ensure_ascii=False))
        for rel in sorted(list(man["archivos"]) + list(man.get("conocimiento", {}))):
            z.write(os.path.join(PROGRAMA, *rel.split("/")), "programa/" + rel)
        for nombre in man.get("raiz", {}):            # BOT.bat, EMPAQUETAR.bat, LEEME.txt
            z.write(os.path.join(os.path.dirname(PROGRAMA), nombre), "programa/_raiz/" + nombre)
    os.replace(tmp, ruta)
    log(f"Paquete {os.path.basename(ruta)}: {len(man['archivos'])} archivos, "
        f"{os.path.getsize(ruta) / 1e6:.1f} MB")
    log(f"Guardado en {ruta}")
    return ruta


if __name__ == "__main__":
    crear(sys.argv[1] if len(sys.argv) > 1 else None)
