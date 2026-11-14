"""Encontrar en pantalla ballenas, sus anillos rojos y las gemas."""
from __future__ import annotations

import cv2
import numpy as np

from vision import conocimiento_vista, ocr
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


#  Vista 2D del sistema (radar): la ballena es un rombo naranja con un triangulo
#  dentro, de unos 28 px, siempre del mismo tamano (los iconos no escalan con el
#  zoom). Se busca en el canal naranja para no depender del fondo; los piratas
#  (otra silueta, naranja tambien) no llegan a 0.5 de parecido.
_BALLENA_2D = None


def centro_sol_2d(img):
    """Centro del sol en la vista 2D: el disco blanco brillante del medio, con la
    cruz de lineas del mapa. No se mueve con el zoom ni al deslizar el mapa mas
    que junto con todo lo demas, asi que sirve de referencia para ubicar ballenas
    y gemas. Devuelve (x, y, radio) en pixeles de la imagen, o None."""
    h, w = img.shape[:2]
    k = w / 1600.0
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # el disco es gris claro (V ~130-160) con la estacion dorada dentro: se cuenta
    # tambien lo dorado del interior para que el disco quede lleno
    gris = (hsv[:, :, 1] < 50) & (hsv[:, :, 2] > 110)
    oro = (hsv[:, :, 0] >= 15) & (hsv[:, :, 0] <= 30) & (hsv[:, :, 1] > 100) & (hsv[:, :, 2] > 150)
    m = (gris | oro).astype(np.uint8) * 255
    m[: int(h * 0.12), :] = 0
    m[int(h * 0.85):, :] = 0
    m[:, : int(w * 0.04)] = 0
    m[:, int(w * 0.80):] = 0
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))   # fuera lineas y texto
    n, _, st, cen = cv2.connectedComponentsWithStats(m)
    mejor = None
    for i in range(1, n):
        x, y, bw, bh, area = st[i]
        if not (20 * k <= bw <= 260 * k and 0.8 <= bw / float(bh) <= 1.25):
            continue
        if area / float(bw * bh) < 0.55:                  # un disco, no un marco
            continue
        if mejor is None or area > mejor[0]:
            mejor = (area, (float(cen[i][0]), float(cen[i][1])), (bw + bh) / 4.0)
    if mejor is not None and mejor[2] >= conocimiento_vista.SOL_RADIO_MIN * k:   # sol del sistema entero
        return mejor[1][0], mejor[1][1], mejor[2]
    return None


def _naranja(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    m = (hsv[:, :, 0] >= 5) & (hsv[:, :, 0] <= 22) & (hsv[:, :, 1] > 150) & (hsv[:, :, 2] > 150)
    return m.astype(np.float32)


def ballenas_2d(imgs, umbral=0.62) -> list[tuple[int, int]]:
    """Centros de las ballenas en la vista 2D del sistema (acepta una imagen o
    varias; une lo visto). Escala 1600x900."""
    global _BALLENA_2D
    if imgs is None:
        return []
    if not isinstance(imgs, (list, tuple)):
        imgs = [imgs]
    if not imgs:
        return []
    if _BALLENA_2D is None:
        _BALLENA_2D = _naranja(conocimiento_vista.icono("ballena_2d"))   # el icono vive en codigo
    t0 = _BALLENA_2D
    out = []
    for img in imgs[:4]:
        h, w = img.shape[:2]
        k = w / 1600.0
        mapa = _naranja(img)
        mejores = []                                   # (parecido, centro) de todas las escalas
        # los iconos del 2D crecen con el zoom del mapa: de 1x (todo el sistema)
        # a ~2.6x (muy acercado)
        for s in conocimiento_vista.ESCALAS_BALLENA_2D:
            f = s * k
            t = cv2.resize(t0, None, fx=f, fy=f, interpolation=cv2.INTER_NEAREST)
            if t.shape[0] >= h or t.shape[1] >= w:
                continue
            r = cv2.matchTemplate(mapa, t, cv2.TM_CCOEFF_NORMED)
            for _ in range(4):
                _, mx, _, (px, py) = cv2.minMaxLoc(r)
                if mx < umbral:
                    break
                a = int(14 * s)
                r[max(0, py - a):py + a, max(0, px - a):px + a] = -1
                mejores.append((mx, (px + t.shape[1] // 2, py + t.shape[0] // 2), s))
        for mx, c, s in sorted(mejores, reverse=True):
            # fuera los botones y paneles de los bordes
            if not (w * 0.10 < c[0] < w * 0.92 and h * 0.10 < c[1] < h * 0.85):
                continue
            a = 22 * s
            if all(abs(c[0] - o[0]) > a or abs(c[1] - o[1]) > a for o in out):
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


def lilas_primero(img, puntos, radio=14) -> list[tuple[int, int]]:
    """Reordena (nunca anade ni quita) los puntos: primero los de icono con
    tono lila (H 120-170, S 20-120, V>=160), despues los blancos. Orden
    estable: dentro de cada grupo se mantiene el orden que traian."""
    if not puntos:
        return puntos
    h, w = img.shape[:2]
    r = max(4, int(radio * w / 1600.0))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    def lila(p):
        x0, y0 = max(0, p[0] - r), max(0, p[1] - r)
        c = hsv[y0:p[1] + r + 1, x0:p[0] + r + 1]
        if c.size == 0:
            return 0
        m = ((c[:, :, 0] >= 120) & (c[:, :, 0] <= 170) & (c[:, :, 1] >= 20)
             & (c[:, :, 1] <= 120) & (c[:, :, 2] >= 160))
        return 0 if m.sum() < 6 else 1

    return sorted(puntos, key=lambda p: -lila(p))


def gemas_2d(img, umbral=0.80, pequenas=False) -> list[tuple[int, int]]:
    """Gemas libres en 2D. pequenas=True: el mapa esta alejado del todo (iconos de
    ~10 px) y ademas se buscan las manchas blancas aisladas (gemas fuera del
    sistema, que la plantilla no ve a ese tamano)."""
    libres = [c for c in _gemas_2d(img, umbral, pequenas) if not _azul_cerca(img, c)]
    return lilas_primero(img, libres)


def _azul_cerca(img, p, radio: int = 22) -> bool:
    """Las gemas con aro azul las esta recogiendo un compañero: no se tocan (y así no se pierden
    pasos abriendo su menú). Cuenta píxeles de azul vivo alrededor del icono."""
    h, w = img.shape[:2]
    r = max(6, int(radio * w / 1600.0))
    c = img[max(0, p[1] - r):p[1] + r + 1, max(0, p[0] - r):p[0] + r + 1]
    if c.size == 0:
        return False
    hsv = cv2.cvtColor(c, cv2.COLOR_BGR2HSV)
    azul = (hsv[:, :, 0] >= 95) & (hsv[:, :, 0] <= 118) & (hsv[:, :, 1] >= 130) & (hsv[:, :, 2] >= 140)
    return int(azul.sum()) >= max(12, int(25 * (w / 1600.0) ** 2))


_GEMA2D_BLANCA = None


def _gemas_2d(img, umbral=0.80, pequenas=False) -> list[tuple[int, int]]:
    """Gemas en la vista 2D del sistema, a cualquier zoom: las blancas por
    plantilla (la nueva, de zoom medio, y la vieja de zoom acercado a escala
    pequena para el sistema entero); con pequenas=True, tambien manchas blancas
    aisladas (gemas fuera del sistema, con el mapa alejado del todo)."""
    global _GEMA2D, _GEMA2D_BLANCA
    if _GEMA2D is None:
        _GEMA2D = imagen("ballenas", "gema_2d.png")
    if _GEMA2D_BLANCA is None:
        _GEMA2D_BLANCA = conocimiento_vista.icono("gema_blanca_2d")    # el icono vive en codigo
    h, w = img.shape[:2]
    out = []

    def anadir(c, a):
        if not (w * 0.1 < c[0] < w * 0.9 and h * 0.12 < c[1] < h * 0.85):
            return
        if all(abs(c[0] - o[0]) > a or abs(c[1] - o[1]) > a for o in out):
            out.append(c)

    #  (plantilla, tamanos, parecido minimo, y del centro dentro de la plantilla)
    pruebas = ((_GEMA2D_BLANCA, conocimiento_vista.ESCALAS_GEMA_BLANCA, conocimiento_vista.UMBRAL_GEMA_BLANCA, 0.5),
               (_GEMA2D, (0.45, 0.5, 0.55, 0.6), 0.62, 0.4),
               (_GEMA2D, (0.75, 0.85, 1.0, 1.15, 1.3), umbral, 0.4))
    for plantilla, escalas, minimo, cy in pruebas:
        for s in escalas:
            t = cv2.resize(plantilla, None, fx=s * h / 900, fy=s * h / 900)
            if t.shape[0] >= h or t.shape[1] >= w:
                continue
            r = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
            a = max(20, int(0.55 * t.shape[1]))
            for _ in range(12):
                _, mx, _, (px, py) = cv2.minMaxLoc(r)
                if mx < minimo:
                    break
                r[max(0, py - a):py + a, max(0, px - a):px + a] = -1
                anadir((px + t.shape[1] // 2, py + int(t.shape[0] * cy)), a)
    # (los iconos lila de color liso son depositos de recursos —Cristales, Mineral—,
    # no gemas: no se cuentan)
    if pequenas:
        # sistema entero a la vista: el icono mide ~10 px y la plantilla no sirve.
        # Respaldo por forma (aisladas); se confirman tocandolas (menu «Gema ...»)
        for c in _gemas_pequenas(img):
            anadir(c, 14)
    return out


def _gemas_pequenas(img) -> list[tuple[int, int]]:
    """Gemas libres con el mapa alejado del todo: manchas blancas de 6-16 px,
    aisladas, en la zona del mapa (sin los paneles ni las barras). Escala 1600x900."""
    h, w = img.shape[:2]
    k = w / 1600.0
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    blanca = ((hsv[:, :, 1] < 60) & (hsv[:, :, 2] > 190)).astype(np.uint8) * 255
    blanca[: int(h * 0.26), :] = 0                      # barra de arriba, avisos y rotulos
    blanca[int(h * 0.82):, :] = 0                       # barra de abajo
    blanca[:, : int(w * 0.31)] = 0                      # datos y recursos de la izquierda
    blanca[:, int(w * 0.74):] = 0                       # botones de la derecha
    blanca = cv2.dilate(blanca, np.ones((3, 3), np.uint8))
    n, _, st, cen = cv2.connectedComponentsWithStats(blanca)
    # todo lo claro del mapa (estaciones, flotas, piratas...): una gema suelta
    # fuera del sistema no tiene nada cerca
    claro = (hsv[:, :, 2] > 150).astype(np.uint8) * 255
    claro[: int(h * 0.26), :] = 0
    claro = cv2.dilate(claro, np.ones((3, 3), np.uint8))
    m, _, st2, cen2 = cv2.connectedComponentsWithStats(claro)
    out = []
    for i in range(1, n):
        x, y, bw, bh, area = st[i]
        if not (6 * k <= bw <= 18 * k and 6 * k <= bh <= 18 * k and area >= 25 * k * k
                and 0.6 <= bw / float(bh) <= 1.6):
            continue
        c = (x + bw / 2, y + bh / 2)
        solo = True
        for j in range(1, m):
            if st2[j][4] < 12 * k * k:
                continue                          # polvo y estrellas
            cx, cy = cen2[j]
            if abs(cx - c[0]) <= bw and abs(cy - c[1]) <= bh:
                continue                          # ella misma
            if (cx - c[0]) ** 2 + (cy - c[1]) ** 2 < (70 * k) ** 2:
                solo = False
                break
        if solo:
            out.append((int(c[0]), int(c[1])))
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
    return lilas_primero(img, [p for p in out if not en_texto(p)])
