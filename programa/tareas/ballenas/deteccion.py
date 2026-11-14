"""Encontrar en pantalla ballenas, sus anillos rojos y las gemas."""
from __future__ import annotations

import cv2
import numpy as np

from vision import ocr
from vision.recursos import imagen


SLOT2 = (499, 250)                 # 2.º objeto de "Objeto comun" (1600x900)
BOTON_LADO = (1572, 626)           # boton redondo que despliega 2D / Ayuda / Recursos


# forma de la ballena de eter en la vista del sistema (1600x900), recortada de
# captura real: cuerpo gris-morado con manchas rosas. La aparicion es
# aleatoria y el anillo rojo no siempre se ve: se busca por la forma
# (y su reflejo, por si mira al otro lado).
_BALLENA = None


def _plantilla_ballena():
    global _BALLENA
    if _BALLENA is None:
        _BALLENA = imagen("ballenas", "ballena.png")
    return _BALLENA


def ballenas_por_forma(imgs, umbral=0.70) -> list[tuple[int, int]]:
    """Centros de las ballenas por su forma en la vista del sistema."""
    if not imgs:
        return []
    t0 = _plantilla_ballena()
    out = []
    for img in imgs[:3]:
        h, w = img.shape[:2]
        t = t0 if (w, h) == (1600, 900) else cv2.resize(t0, None, fx=w / 1600, fy=h / 900)
        for tt in (t, cv2.flip(t, 1)):
            r = cv2.matchTemplate(img, tt, cv2.TM_CCOEFF_NORMED)
            for _ in range(5):
                _, mx, _, (px, py) = cv2.minMaxLoc(r)
                if mx < umbral:
                    break
                c = (px + tt.shape[1] // 2, py + tt.shape[0] // 2)
                r[max(0, py - 25):py + 25, max(0, px - 35):px + 35] = -1
                # fuera de los botones de los bordes, y con manchas rosas
                if not (w * 0.12 < c[0] < w * 0.92 and h * 0.12 < c[1] < h * 0.85):
                    continue
                caja = img[py:py + tt.shape[0], px:px + tt.shape[1]].astype(int)
                rosa = ((caja[..., 2] > 140) & (caja[..., 1] < 110) & (caja[..., 0] > 60)).sum()
                if rosa < 4:
                    continue
                if all(abs(c[0] - o[0]) > 30 or abs(c[1] - o[1]) > 20 for o in out):
                    out.append(c)
    return out


_BALLENA_ZOOM = None


def ballena_en_zoom(img, umbral=0.38):
    """Centro de la ballena en la vista con zoom (cuando el toque ha cogido
    otra cosa que estaba encima, la ballena suele verse al lado)."""
    global _BALLENA_ZOOM
    if _BALLENA_ZOOM is None:
        _BALLENA_ZOOM = imagen("ballenas", "ballena_zoom.png")
    h, w = img.shape[:2]
    mejor = None
    for s in (0.7, 0.85, 1.0, 1.15, 1.3):
        t = cv2.resize(_BALLENA_ZOOM, None, fx=s * w / 1600, fy=s * h / 900)
        if t.shape[0] >= h or t.shape[1] >= w:
            continue
        r = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
        _, mx, _, (px, py) = cv2.minMaxLoc(r)
        if mejor is None or mx > mejor[0]:
            mejor = (mx, (px + t.shape[1] // 2, py + t.shape[0] // 2))
    return mejor[1] if mejor and mejor[0] >= umbral else None


# icono de la gema en el modo 2D del sistema (aro gris con concha blanca y
# rombos debajo), de un video de una partida, a escala 1600x900
_GEMA2D = None


def gemas_2d(img, umbral=0.80) -> list[tuple[int, int]]:
    global _GEMA2D
    if _GEMA2D is None:
        _GEMA2D = imagen("ballenas", "gema_2d.png")
    h, w = img.shape[:2]
    out = []
    for s in (0.75, 0.85, 1.0, 1.15):
        t = cv2.resize(_GEMA2D, None, fx=s * h / 900, fy=s * h / 900)
        r = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
        for _ in range(12):
            _, mx, _, (px, py) = cv2.minMaxLoc(r)
            if mx < umbral:
                break
            r[max(0, py - 25):py + 25, max(0, px - 25):px + 25] = -1
            c = (px + t.shape[1] // 2, py + int(t.shape[0] * 0.4))
            if not (w * 0.1 < c[0] < w * 0.9 and h * 0.12 < c[1] < h * 0.85):
                continue
            if all(abs(c[0] - o[0]) > 25 or abs(c[1] - o[1]) > 25 for o in out):
                out.append(c)
    return out


def anillos_rojos(imgs) -> list[tuple[int, int]]:
    """Centros de los circulos rojos de las ballenas en la vista del sistema
    (parpadean: se juntan varias capturas). Escala 1600x900."""
    if not imgs:
        return []
    h, w = imgs[0].shape[:2]
    k = w / 1600.0
    acum = np.zeros((h, w), np.uint8)
    for img in imgs:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        roja = (((hsv[:, :, 0] < 6) | (hsv[:, :, 0] > 174)) & (hsv[:, :, 1] > 170)
                & (hsv[:, :, 2] > 170)).astype(np.uint8) * 255
        acum = cv2.bitwise_or(acum, roja)
    # fuera la estrella del centro y los paneles
    acum[: int(h * 0.12), :] = 0
    acum[int(h * 0.85):, :] = 0
    acum[:, : int(w * 0.17)] = 0
    acum[:, int(w * 0.80):] = 0
    acum = cv2.morphologyEx(acum, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _, st, cen = cv2.connectedComponentsWithStats(acum)
    out = []
    for i in range(1, n):
        x, y, bw, bh, area = st[i]
        relleno = area / float(max(1, bw * bh))
        # anillo: ancho de 60-220 px, mas ancho que alto, hueco por dentro
        if 55 * k <= bw <= 230 * k and 25 * k <= bh <= 140 * k and bw >= bh and relleno < 0.45:
            out.append((int(x + bw / 2), int(y + bh / 2)))
    return sorted(out)


def rojo_cerca(imgs, pos, rx=85, ry=65) -> int:
    """Pixeles rojos intensos alrededor de pos (circulo de la ballena o el
    triangulo "!" del combate), juntando varias capturas."""
    if not imgs:
        return 0
    h, w = imgs[0].shape[:2]
    k = w / 1600.0
    x0, x1 = max(0, int(pos[0] - rx * k)), min(w, int(pos[0] + rx * k))
    y0, y1 = max(0, int(pos[1] - ry * k)), min(h, int(pos[1] + ry * k))
    acum = None
    for img in imgs:
        hsv = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
        m = ((hsv[:, :, 0] < 6) | (hsv[:, :, 0] > 174)) & (hsv[:, :, 1] > 170) & (hsv[:, :, 2] > 150)
        acum = m if acum is None else (acum | m)
    return int(acum.sum()) if acum is not None else 0


def gemas_candidatas(img, textos=None, sistema=False) -> list[tuple[int, int]]:
    """Iconos blancos de las gemas en la vista Recursos (con el filtro solo de
    gemas): manchas blancas de 10-34 px. Se confirman tocandolas."""
    h, w = img.shape[:2]
    k = w / 1600.0
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    blanca = ((hsv[:, :, 1] < 45) & (hsv[:, :, 2] > 205)).astype(np.uint8) * 255
    blanca[: int(h * 0.13), :] = 0           # titulo y barra
    blanca[int(h * 0.80):, :] = 0
    blanca[:, int(w * (0.80 if sistema else 0.76)):] = 0     # filtro / botones de la derecha
    if sistema:
        blanca[:, : int(w * 0.10)] = 0       # recursos de la izquierda
    blanca = cv2.dilate(blanca, np.ones((3, 3), np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(blanca)
    out = []
    for i in range(1, n):
        x, y, bw, bh, area = st[i]
        if 7 * k <= bw <= 34 * k and 9 * k <= bh <= 40 * k and area >= 30 * k * k:
            out.append((int(x + bw / 2), int(y + bh / 2)))
    # fuera los textos (contadores de las flotas, nombres)
    if textos is None:
        textos = ocr.leer(img)
    def en_texto(p):
        return any(t["caja"][0] - 6 <= p[0] <= t["caja"][0] + t["caja"][2] + 6
                   and t["caja"][1] - 6 <= p[1] <= t["caja"][1] + t["caja"][3] + 6
                   for t in textos)
    return [p for p in out if not en_texto(p)]
