"""Lectura de numeros del juego comparando cada cifra con muestras reales."""
from __future__ import annotations

import cv2
import numpy as np

from vision.recursos import muestras_cifras, silueta_cifra


_DIG = None


def _digitos():
    global _DIG
    if _DIG is None:
        _DIG = [(k, silueta_cifra(archivo).astype(np.float32), a)
                for k, archivo, a in muestras_cifras()]
    return _DIG


def leer_cifras(img, caja, v_min=140, s_max=255):
    """Lee los numeros escritos en la caja (x0, y0, x1, y1) de la captura.
    Devuelve la lista de numeros de izquierda a derecha (p. ej. "10/100" ->
    [10, 100]; "Disponible: 123" -> [123]; los puntos de millar se ignoran)."""
    x0, y0, x1, y1 = [int(v) for v in caja]
    h, w = img.shape[:2]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    if x1 - x0 < 5 or y1 - y0 < 5:
        return []
    hsv = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    m = ((hsv[:, :, 2] > v_min) & (hsv[:, :, 1] <= s_max)).astype(np.uint8)
    n, _, st, _ = cv2.connectedComponentsWithStats(m)
    comps = sorted((int(st[i, 0]), int(st[i, 1]), int(st[i, 2]), int(st[i, 3]))
                   for i in range(1, n) if st[i, 4] >= 3)
    piezas = []
    for c in comps:                      # juntar trozos de un mismo signo
        if piezas and c[0] < piezas[-1][0] + piezas[-1][2] - 1:
            a = piezas[-1]
            xa, ya = min(a[0], c[0]), min(a[1], c[1])
            piezas[-1] = (xa, ya, max(a[0] + a[2], c[0] + c[2]) - xa, max(a[1] + a[3], c[1] + c[3]) - ya)
        else:
            piezas.append(c)
    if not piezas:
        return []
    alto = max(p[3] for p in piezas)
    dig = _digitos()
    numeros, actual, ultimo_x = [], "", None
    for x, y, pw, ph in piezas:
        if ph < 0.45 * alto:
            continue                      # punto de millar o resto pequeno
        hueco = ultimo_x is not None and x - ultimo_x > 0.9 * alto
        car = None
        if pw >= 0.22 * ph:
            g = cv2.resize(m[y:y + ph, x:x + pw].astype(np.float32), (12, 18), interpolation=cv2.INTER_AREA)
            g = (g > 0.5).astype(np.float32)
            asp = pw / float(ph)
            mejor, mejor_k = 0.0, None
            for k, t, a in dig:
                sc = 1.0 - float(np.abs(g - t).mean()) - 0.6 * abs(asp - a)
                if sc > mejor:
                    mejor, mejor_k = sc, k
            if mejor >= 0.62 and ph >= 0.7 * alto and mejor_k != "/":
                car = mejor_k
        if car is None or hueco:
            if actual:
                numeros.append(int(actual))
            actual = car or ""
        else:
            actual += car
        ultimo_x = x + pw
    if actual:
        numeros.append(int(actual))
    return numeros
