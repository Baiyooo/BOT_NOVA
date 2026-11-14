"""Detectores sueltos de la pantalla: puntos rojos de aviso, barras de flota,
boton del radar, X de cerrar, lista de flotas hostiles...
"""
from __future__ import annotations

import cv2
import numpy as np

from vision.recursos import silueta
from vision.mascaras import mascara_blanco, mascara_rojo
from vision.plantillas import buscar_rotulo, localizar_todos


def puntos_rojos(img: np.ndarray, zona=(0.0, 0.0, 1.0, 1.0)):
    """Puntos rojos de aviso (circulitos de ~10 px a 1600 de ancho) dentro de
    la zona (fracciones x0, y0, x1, y1). Devuelve sus centros."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = int(zona[0] * w), int(zona[1] * h), int(zona[2] * w), int(zona[3] * h)
    hsv = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    tono = hsv[:, :, 0].astype(np.int32) * 2
    m = (((tono < 12) | (tono > 348)) & (hsv[:, :, 1] > 170) & (hsv[:, :, 2] > 115)).astype(np.uint8)
    n, _, est, cen = cv2.connectedComponentsWithStats(m)
    k = w / 1600.0
    salida = []
    for i in range(1, n):
        bw, bh, area = est[i, 2], est[i, 3], est[i, 4]
        if not (6 * k <= bw <= 20 * k and 6 * k <= bh <= 20 * k):
            continue
        if abs(bw - bh) > 4 * k or area < 0.55 * bw * bh:
            continue                     # no es redondo y macizo
        salida.append((int(cen[i][0]) + x0, int(cen[i][1]) + y0))
    return sorted(salida, key=lambda c: (c[1], c[0]))


def _fraccion_color(img, x0, y0, x1, y1, tono_min, tono_max) -> float:
    h, w = img.shape[:2]
    x0, x1 = max(0, int(x0)), min(w, int(x1))
    y0, y1 = max(0, int(y0)), min(h, int(y1))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    hsv = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    t = hsv[:, :, 0].astype(np.float32) * 2.0
    vivo = (hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 110)
    return float((vivo & (t > tono_min) & (t < tono_max)).mean())


def _diferencia(a: np.ndarray, b: np.ndarray) -> float:
    """Cuanto ha cambiado la pantalla entre dos capturas (0 = identicas)."""
    pa = cv2.resize(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), (160, 90)).astype(np.int16)
    pb = cv2.resize(cv2.cvtColor(b, cv2.COLOR_BGR2GRAY), (160, 90)).astype(np.int16)
    return float(np.abs(pa - pb).mean())


def barras_de_flota(img: np.ndarray) -> list[tuple[int, int, int]]:
    """Cada flota del mapa lleva encima una barra doble: cian sobre naranja.
    Devuelve (x centro, y, ancho) de cada una, sin las de la interfaz."""
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    t = hsv[:, :, 0].astype(np.float32) * 2.0
    vivo = (hsv[:, :, 1] > 120) & (hsv[:, :, 2] > 150)
    cian = (vivo & (t > 170) & (t < 205)).astype(np.uint8)
    nar = (vivo & (t > 10) & (t < 40)).astype(np.uint8)

    def tramos(m):
        n, _, st, _ = cv2.connectedComponentsWithStats(m, 8)
        out = []
        for i in range(1, n):
            x, y, bw, bh, a = st[i]
            if w * 0.015 <= bw <= w * 0.17 and bh <= max(7, h * 0.009) and a >= bw * 0.8:
                out.append((int(x), int(y), int(bw), int(bh)))
        return out

    res = []
    for (x, y, bw, _) in tramos(cian):
        for (x2, y2, bw2, _) in tramos(nar):
            if 0 < y2 - y <= max(10, h * 0.012) and abs(x - x2) < 8 and abs(bw - bw2) < 12:
                cx = x + bw // 2
                # fuera los bordes, donde estan los paneles de la interfaz
                if w * 0.10 < cx < w * 0.82 and h * 0.06 < y < h * 0.95:
                    res.append((cx, int(y), bw))
                break
    return res


def busca_sigilo(img: np.ndarray) -> tuple[float, tuple[int, int]]:
    return buscar_rotulo(img, "sigilo")


def caja_boton_radar(img: np.ndarray):
    """El boton de la pantalla del Radar (dice Buscar, y luego Ir a).
    Se busca el BORDE: un rectangulo hueco, ancho y poco relleno. Asi no se
    confunde con el cursor del raton, que es un triangulo solido.

    Se admiten los dos estilos que ha tenido el juego: el boton naranja
    (borde y texto ambar) y el gris claro actual (borde y texto blancos). Este
    ultimo fue el que dejo de detectarse y hacia que el radar no se usara."""
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    ambar = ((hsv[:, :, 0] > 12) & (hsv[:, :, 0] < 30)
             & (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 90))
    claro = (hsv[:, :, 2] > 110) & (hsv[:, :, 1] < 60)
    m = (ambar | claro).astype(np.uint8)
    m[:int(h * 0.70), :] = 0          # solo la franja de abajo
    m[:, :int(w * 0.55)] = 0          # y la mitad derecha
    m[:, int(w * 0.88):] = 0
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    mejor = None
    for i in range(1, n):
        x, y, bw, bh, area = (stats[i, 0], stats[i, 1], stats[i, 2],
                              stats[i, 3], stats[i, 4])
        if bw < w * 0.08 or bh < h * 0.03:
            continue
        if not (2.5 < bw / bh < 6.0):
            continue
        # el boton del radar va abajo a la derecha; asi no se cuela otro
        # recuadro claro de la interfaz cuando el radar no esta abierto
        if x + bw / 2 < w * 0.65 or y + bh / 2 < h * 0.82:
            continue
        if area / float(bw * bh) > 0.45:   # relleno: es el cursor, no un borde
            continue
        if mejor is None or bw * bh > mejor[0]:
            mejor = (bw * bh, int(x), int(y), int(bw), int(bh))
    return None if mejor is None else mejor[1:]


# ---------------------------------------------------------------------------
# La tarea
# ---------------------------------------------------------------------------
def buscar_cerrar_x(img: np.ndarray):
    """Busca la X de cerrar de las ventanas de eventos (arriba a la derecha).
    Devuelve el centro en la captura o None. Lineas finas: se engordan
    plantilla y pantalla para que un pixel de desfase no la pierda."""
    h, w = img.shape[:2]
    f = 1600.0 / w
    if f != 1:
        img = cv2.resize(img, (1600, int(round(h * f))))
    k = np.ones((5, 5), np.uint8)
    zona = cv2.dilate(mascara_blanco(img[0:170, 1300:1600]), k).astype(np.float32)
    tpl = cv2.dilate(silueta("cerrar_x"), k).astype(np.float32)
    mejor, centro = 0.0, None
    for e in np.arange(0.80, 1.21, 0.05):
        t = cv2.resize(tpl, None, fx=e, fy=e, interpolation=cv2.INTER_NEAREST)
        r = cv2.matchTemplate(zona, t, cv2.TM_CCOEFF_NORMED)
        _, mx, _, ml = cv2.minMaxLoc(r)
        if mx > mejor:
            mejor = mx
            centro = (int((ml[0] + t.shape[1] / 2 + 1300) / f), int((ml[1] + t.shape[0] / 2) / f))
    return centro if mejor >= 0.70 else None


# ---------------------------------------------------------------------------
# Defensa: si un jugador entra en combate con una flota propia, retirarla.
# "Llamar a todos" (abajo a la izquierda de la vista de batalla) es de pago:
# NO se usa. Se retira cada flota con su propio "Llamar".
def filas_hostiles(img):
    """Lineas de texto rojo de la lista "Flota hostil" (derecha de la vista de
    batalla). Devuelve [(y, es_pirata)] de arriba abajo."""
    h, w = img.shape[:2]
    x0, x1 = int(w * 0.83), int(w * 0.975)
    y0, y1 = int(h * 0.20), int(h * 0.86)
    m = mascara_rojo(img[y0:y1, x0:x1])
    filas = m.sum(axis=1) > max(3, 0.02 * (x1 - x0))
    k = h / 900.0
    pir = [c for _, c in localizar_todos(img, "pirata_rojo", 0.70, 10)
           if x0 <= c[0] <= x1]
    salida, y = [], 0
    while y < len(filas):
        if not filas[y]:
            y += 1
            continue
        ini = y
        while y < len(filas) and filas[y]:
            y += 1
        alto = y - ini
        banda = m[ini:y]
        cols = np.nonzero(banda.sum(axis=0))[0]
        ancho = (cols[-1] - cols[0] + 1) if len(cols) else 0
        denso = banda.sum() / float(max(1, ancho * alto))
        # texto: alto de letra, algo de ancho y trazo macizo (las barras de
        # vida son finas; las nebulosas rojas del fondo, ralas)
        if alto >= 14 * k and ancho >= 25 * k and denso >= 0.15:
            yc = y0 + (ini + y) // 2
            es = any(abs(c[1] - yc) < 16 * k for c in pir)
            salida.append((yc, es))
    return salida


def jugador_en_batalla(img) -> bool:
    """En la vista de batalla, algun enemigo que no es un pirata."""
    return any(not es for _, es in filas_hostiles(img))
