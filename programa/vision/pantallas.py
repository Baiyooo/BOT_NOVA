"""Mapa de pantallas de Nova Empire.

Un solo sitio que sabe reconocer en que pantalla esta el juego y como salir
de ella, para que las tareas no tengan que improvisar. Todo es vision por
ordenador local (colores y plantillas): no se envia nada fuera del PC.

    donde_estoy(img)     -> nombre de la pantalla ("aviso", "base", ...)
    dialogo_aviso(img)   -> botones de un aviso del juego (No / OK) o None
    salir(ctrl, img)     -> da un paso seguro para salir de lo desconocido
"""
from __future__ import annotations

import cv2
import numpy as np


def _a1600(img):
    """Todo se mide sobre 1600 de ancho; devuelve (imagen, factor)."""
    h, w = img.shape[:2]
    f = 1600.0 / w
    if abs(f - 1) < 1e-3:
        return img, 1.0
    return cv2.resize(img, (1600, int(round(h * f)))), f


def _ambar(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    tono = hsv[:, :, 0].astype(np.float32) * 2.0
    return (((tono > 20) & (tono < 55))
            & (hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 55)).astype(np.uint8)


# ---------------------------------------------------------------------------
# Avisos del juego: panel con cabecera gris azulada y dos botones con borde
# ambar debajo (No / OK, Cancelar / Confirmar). Ej.: "Tu FPS actual parece
# ser bajo..." o "Seguro que quieres salir?". El bot pulsa siempre el de la
# izquierda (No / Cancelar), que nunca cambia nada.
# ---------------------------------------------------------------------------
def _botones_ambar(img):
    """Rectangulos huecos de borde ambar del tamano de un boton de aviso."""
    h, w = img.shape[:2]
    m = _ambar(img)
    m = cv2.dilate(m, np.ones((3, 3), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cnts:
        x, y, bw, bh = cv2.boundingRect(c)
        if not (0.09 * w <= bw <= 0.24 * w and 0.045 * h <= bh <= 0.13 * h):
            continue
        if not (2.0 <= bw / bh <= 5.5) or not (0.35 * h <= y <= 0.90 * h):
            continue
        dentro = m[y + 6:y + bh - 6, x + 6:x + bw - 6]
        if dentro.size == 0:
            continue
        # hueco: el borde es ambar y el interior casi no (solo el texto)
        borde = (m[y:y + 4, x:x + bw].mean() + m[y + bh - 4:y + bh, x:x + bw].mean()) / 2
        if borde < 0.45 or dentro.mean() > 0.35:
            continue
        out.append((x, y, bw, bh))
    return out


def _cabecera(img, x0, x1, y_bajo):
    """Busca encima de los botones la franja gris azulada del titulo."""
    h = img.shape[0]
    y_top = max(0, int(y_bajo - 0.45 * h))
    zona = img[y_top:int(y_bajo), x0:x1].astype(np.int16)
    if zona.size == 0:
        return False
    b, g, r = zona[:, :, 0], zona[:, :, 1], zona[:, :, 2]
    luz = (b + g + r) / 3
    gris_az = (b >= r) & (luz > 55) & (luz < 140) & (np.abs(b - r) < 45)
    filas = gris_az.mean(axis=1)
    # varias filas seguidas casi enteras de ese color = cabecera del panel
    seguidas = mejor = 0
    for v in filas:
        seguidas = seguidas + 1 if v > 0.80 else 0
        mejor = max(mejor, seguidas)
    return mejor >= int(0.025 * h)


def dialogo_aviso(img):
    """{"no": (x, y), "ok": (x, y)} en coordenadas de la captura, o None."""
    im, f = _a1600(img)
    h, w = im.shape[:2]
    bots = _botones_ambar(im)
    if len(bots) < 2 or len(bots) > 4:
        return None
    # un aviso oscurece todo lo de detras: fuera de los dos botones casi no
    # queda ambar (en "Elige tu flota" las tarjetas tienen borde ambar)
    m = _ambar(im)
    for x, y, bw, bh in bots:
        m[max(0, y - 4):y + bh + 4, max(0, x - 4):x + bw + 4] = 0
    if m.mean() > 0.008:
        return None
    for i in range(len(bots)):
        for j in range(len(bots)):
            a, b = bots[i], bots[j]
            if a[0] >= b[0]:
                continue
            mismo_y = abs((a[1] + a[3] / 2) - (b[1] + b[3] / 2)) < 0.02 * h
            mismo_tam = abs(a[2] - b[2]) < 0.18 * a[2] and abs(a[3] - b[3]) < 0.25 * a[3]
            hueco = b[0] - (a[0] + a[2])
            if not (mismo_y and mismo_tam and 0.04 * w < hueco < 0.20 * w):
                continue
            centro = (a[0] + b[0] + b[2]) / 2
            if abs(centro - w / 2) > 0.12 * w:          # los avisos van centrados
                continue
            if not _cabecera(im, a[0], b[0] + b[2], min(a[1], b[1])):
                continue
            no = (int((a[0] + a[2] / 2) / f), int((a[1] + a[3] / 2) / f))
            ok = (int((b[0] + b[2] / 2) / f), int((b[1] + b[3] / 2) / f))
            return {"no": no, "ok": ok}
    return None


def aviso_un_boton(img):
    """Aviso del juego con un solo boton (p. ej. "Error de conexion(0)" con
    OK): un boton ambar centrado, cabecera de aviso encima y el resto
    oscurecido. Devuelve el centro del boton o None."""
    im, f = _a1600(img)
    h, w = im.shape[:2]
    bots = _botones_ambar(im)
    if len(bots) != 1:
        return None
    x, y, bw, bh = bots[0]
    if abs((x + bw / 2) - w / 2) > 0.06 * w or not (0.45 * h < y < 0.85 * h):
        return None
    m = _ambar(im)
    m[max(0, y - 4):y + bh + 4, max(0, x - 4):x + bw + 4] = 0
    if m.mean() > 0.008:
        return None
    if not _cabecera(im, int(w * 0.3), int(w * 0.7), y):
        return None
    return (int((x + bw / 2) / f), int((y + bh / 2) / f))


# ---------------------------------------------------------------------------
# Reconocer la pantalla
# ---------------------------------------------------------------------------
def donde_estoy(img) -> str:
    """Nombre de la pantalla, de lo mas concreto a lo mas general:
    aviso, elige_flota, menu_objetivo, ventana (con X), base, sistema,
    secundaria (con Atras) o desconocida."""
    from vision import detectores
    from vision import plantillas
    if dialogo_aviso(img):
        return "aviso"
    h = img.shape[0]

    def ve(nombre, umbral=0.62):
        try:
            p, c = plantillas.buscar_rotulo(img, nombre)
        except Exception:                             # noqa: BLE001
            return None
        return c if p >= umbral else None

    if ve("elige"):
        return "elige_flota"
    if ve("atacar", 0.60) or ve("marcador", 0.62):
        return "menu_objetivo"
    if detectores.buscar_cerrar_x(img):
        return "ventana"
    c = ve("sistema")
    if c and c[1] > 0.75 * h:                         # boton "Sistema": estoy en la base
        return "base"
    c = ve("estacion")
    if c and c[1] > 0.75 * h:                         # "Estacion espacial": vista del sistema
        return "sistema"
    if ve("atras"):
        return "secundaria"
    return "desconocida"


def salir(ctrl, img, log=None) -> str:
    """Un paso seguro hacia la base o el sistema. Devuelve que ha hecho.
    Nunca pulsa Atras en la base (el juego preguntaria si quieres salir)."""
    def di(m):
        if log:
            log(m)

    av = dialogo_aviso(img)
    if av:
        ctrl.tap(av["no"])
        di("Aviso del juego: pulso No.")
        return "aviso"
    sitio = donde_estoy(img)
    if sitio in ("base", "sistema"):
        return sitio
    if sitio == "ventana":
        from vision import detectores
        ctrl.tap(detectores.buscar_cerrar_x(img))
        di("Cierro la ventana con la X.")
        return "x"
    ctrl.back()
    di(f"Pantalla '{sitio}': pulso Atras.")
    return "atras"
