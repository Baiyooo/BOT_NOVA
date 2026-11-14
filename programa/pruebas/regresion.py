"""Prueba de regresion de la vision del bot.

Pasa todos los detectores (rotulos, cifras, pantallas, tablero del Roaming
Test, ballenas, flotas, Cosmomante...) por las capturas reales de
pruebas/capturas y compara el resultado con el guardado en
pruebas/regresion_esperado.json. Si algo cambia, dice que y en que captura.

    python pruebas\\regresion.py            comprobar (tarda unos minutos)
    python pruebas\\regresion.py --guardar  aceptar los resultados actuales como buenos
                                           (solo tras un cambio hecho a proposito)

No toca el juego ni ADB, y no escribe en los datos del usuario.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
PROGRAMA = os.path.dirname(AQUI)
sys.path.insert(0, PROGRAMA)
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="novabot_regresion_")   # nada a los datos reales

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from tareas import flotas, roaming  # noqa: E402
from tareas.ballenas import deteccion as ballenas  # noqa: E402
from tareas.cosmomante import mapa as cosmo  # noqa: E402
from vision import cifras, detectores, pantallas, plantillas  # noqa: E402

CAPTURAS = os.path.join(AQUI, "capturas")
ESPERADO = os.path.join(AQUI, "regresion_esperado.json")
#  capturas que ademas se prueban reducidas, para cubrir otras resoluciones
REDUCIDAS = {"00": (1280, 720), "12": (1280, 720), "16": (1366, 768)}


def limpio(x):
    """Pasa el resultado a algo que se pueda guardar en JSON y comparar."""
    if isinstance(x, (np.floating, float)):
        return round(float(x), 5)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.ndarray):
        return limpio(x.tolist())
    if isinstance(x, (list, tuple)):
        return [limpio(v) for v in x]
    if isinstance(x, dict):
        return {str(k): limpio(v) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
    if isinstance(x, (str, int, bool)) or x is None:
        return x
    return repr(type(x))


def comprobaciones(img):
    h, w = img.shape[:2]
    r = {}
    for n in sorted(plantillas.ROTULOS):
        r["loc:" + n] = lambda n=n: plantillas.localizar(img, n)
    for n, u in (("recoger_todo", 0.6), ("recoger_ev", 0.6), ("pirata_rojo", 0.6)):
        r["todos:" + n] = lambda n=n, u=u: plantillas.localizar_todos(img, n, u)

    def tablero():
        g = roaming.detect_grid(img)
        return None if g is None else [g.rows, g.cols, g.dx, g.dy, g.x0, g.y0, roaming.read_board(img, g)]

    r.update({
        "cifras": lambda: cifras.leer_cifras(img, (0, 0, w // 3, h // 6)),
        "rojos": lambda: detectores.puntos_rojos(img),
        "barras": lambda: detectores.barras_de_flota(img),
        "sigilo": lambda: detectores.busca_sigilo(img),
        "radar": lambda: detectores.caja_boton_radar(img),
        "cerrar": lambda: detectores.buscar_cerrar_x(img),
        "hostiles": lambda: detectores.filas_hostiles(img),
        "batalla": lambda: detectores.jugador_en_batalla(img),
        "pantalla": lambda: pantallas.donde_estoy(img),
        "aviso": lambda: pantallas.dialogo_aviso(img),
        "tablero": tablero,
        "ballenas": lambda: ballenas.ballenas_por_forma([img]),
        "ballena_zoom": lambda: ballenas.ballena_en_zoom(img),
        "gemas_2d": lambda: ballenas.gemas_2d(img),
        "anillos": lambda: ballenas.anillos_rojos([img]),
        "llamar": lambda: flotas.boton_llamar(img, h // 2),
        "cosmo_filas": lambda: cosmo.filas_panel(img),
        "cosmo_icono": lambda: cosmo.clasificar(img[400:450, 600:676]),
    })
    return r


def ejecutar():
    plantillas._ESCALAS.clear()            # sin lo aprendido: siempre el mismo punto de partida
    archivos = sorted(f for f in os.listdir(CAPTURAS) if f.lower().endswith(".png"))
    casos = []
    for f in archivos:
        img = cv2.imdecode(np.fromfile(os.path.join(CAPTURAS, f), np.uint8), cv2.IMREAD_COLOR)
        casos.append((f, img))
        tam = REDUCIDAS.get(f[:2])
        if tam:
            casos.append((f"{f} @{tam[0]}x{tam[1]}", cv2.resize(img, tam, interpolation=cv2.INTER_AREA)))
    res = {}
    t0 = time.time()
    for i, (nombre, img) in enumerate(casos, 1):
        r = {}
        for k, fn in comprobaciones(img).items():
            try:
                r[k] = limpio(fn())
            except Exception as e:  # noqa: BLE001
                r[k] = f"EXCEPCION {type(e).__name__}: {str(e)[:80]}"
        res[nombre] = r
        print(f"\r  {i}/{len(casos)} capturas  ({time.time() - t0:.0f} s)", end="", flush=True)
    print()
    return res


def main():
    guardar = "--guardar" in sys.argv
    if not guardar and not os.path.exists(ESPERADO):
        print("No hay resultados esperados. Ejecuta primero con --guardar.")
        return 2
    print("Prueba de regresion de la vision de NovaBot")
    actual = ejecutar()
    if guardar:
        with open(ESPERADO, "w", encoding="utf-8") as fh:
            json.dump(actual, fh, indent=0, sort_keys=True, ensure_ascii=False)
            fh.write("\n")
        print(f"Guardados {sum(len(v) for v in actual.values())} resultados como los esperados.")
        return 0
    with open(ESPERADO, encoding="utf-8") as fh:
        esperado = json.load(fh)
    difs = []
    for cap in sorted(set(esperado) | set(actual)):
        if cap not in actual or cap not in esperado:
            difs.append(f"{cap}: captura {'nueva' if cap in actual else 'que falta'}")
            continue
        for k in sorted(set(esperado[cap]) | set(actual[cap])):
            a, b = esperado[cap].get(k, "(no estaba)"), actual[cap].get(k, "(ya no esta)")
            if a != b:
                difs.append(f"{cap} · {k}\n      antes: {str(a)[:110]}\n      ahora: {str(b)[:110]}")
    total = sum(len(v) for v in esperado.values())
    if not difs:
        print(f"TODO IGUAL: {total} comprobaciones en {len(esperado)} capturas.")
        return 0
    print(f"{len(difs)} DIFERENCIAS de {total} comprobaciones:")
    for d in difs[:40]:
        print("  " + d)
    if len(difs) > 40:
        print(f"  ... y {len(difs) - 40} mas")
    print("Si el cambio es a proposito y esta bien, acepta los nuevos con --guardar.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
