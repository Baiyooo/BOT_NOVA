"""Memoria corta de puntos de la pantalla que no hay que volver a tocar, y
deteccion de «alguien ya va hacia ahi».

Descartes: dos clases, las dos con caducidad y por cuenta (en memoria del
proceso: no hace falta que sobrevivan a un reinicio, caducan en minutos).
  - "malo":  un punto que se toco y no era un objetivo valido -> 5 min, radio
             pequeno (~15 px a 1600x900).
  - "mando": un objetivo al que ya se mando (o ya va) un dron -> ~50 s, radio
             grande (~80 px): cubre el icono aunque lo veamos desplazado.

Las coordenadas dependen de la camara. Cada apunte guarda una huella pequena
(gris 32x18) de la captura en que se tomo; al consultar se compara con la
captura actual y, si la vista ha cambiado, el apunte se ignora (no se borra:
si la camara vuelve, sigue valiendo). Ante la duda, no se descarta nada.
"""
from __future__ import annotations

import threading
import time

MALO_SEG, MALO_RADIO = 5 * 60, 15
MANDO_SEG, MANDO_RADIO = 50, 80
#  diferencia media (0-255) de huellas por encima de la cual la vista "se ha movido"
VISTA_UMBRAL = 14.0

#  comprobacion de movimiento alrededor del objetivo tocado antes de «Recoger».
#  DESACTIVADA por defecto: no esta calibrada con capturas reales de lineas de
#  vuelo y las animaciones del juego dan ruido. Para activarla, ponla a True
#  y ajusta MOVIMIENTO_UMBRAL midiendo antes (objetivo libre vs. con dron en camino).
COMPROBAR_MOVIMIENTO = False
MOVIMIENTO_RECORTE = 40          # lado del recorte a 1600x900
MOVIMIENTO_ESPERA = 1.2
MOVIMIENTO_UMBRAL = 2.5          # media de absdiff en gris; el original usaba 0.1


def huella(img):
    """Gris reducido de la captura (o None si no se puede)."""
    try:
        import cv2
        return cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (32, 18), interpolation=cv2.INTER_AREA)
    except Exception:                                          # noqa: BLE001
        return None


def _misma_vista(a, b) -> bool:
    if a is None or b is None:
        return False
    import numpy as np
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean()) <= VISTA_UMBRAL


class Descartes:
    def __init__(self):
        self._l: list = []        # (hasta, x, y, radio_en_1600, huella, ancho)
        self._m = threading.Lock()

    def _podar(self, ahora):
        self._l = [e for e in self._l if e[0] > ahora]

    def anotar(self, punto, img, clase="malo"):
        seg, radio = (MALO_SEG, MALO_RADIO) if clase == "malo" else (MANDO_SEG, MANDO_RADIO)
        ahora = time.time()
        with self._m:
            self._podar(ahora)
            self._l.append((ahora + seg, punto[0], punto[1], radio, huella(img), img.shape[1]))

    def bloqueado(self, punto, img) -> bool:
        ahora = time.time()
        h = huella(img)
        with self._m:
            self._podar(ahora)
            for _t, x, y, r, hu, w0 in self._l:
                k = img.shape[1] / float(w0 or 1600)
                rr = r * img.shape[1] / 1600.0
                if abs(punto[0] - x * k) <= rr and abs(punto[1] - y * k) <= rr and _misma_vista(hu, h):
                    return True
        return False

    def filtrar(self, puntos, img):
        return [p for p in puntos if not self.bloqueado(p, img)]

    def vaciar(self):
        with self._m:
            self._l.clear()


_POR_CUENTA: dict = {}


def de_cuenta(cuenta) -> Descartes:
    return _POR_CUENTA.setdefault(str(cuenta), Descartes())


def hay_movimiento(ctrl, img=None, punto=None, espera: float = MOVIMIENTO_ESPERA) -> bool:
    """True si cambia el recorte alrededor de `punto` (el objetivo tocado; por
    defecto el centro) entre dos capturas: la linea de vuelo de otro dron o
    flota hacia ese objetivo. `img` es la primera captura si ya se tiene. Si
    falla algo, False (no se bloquea la recogida)."""
    if not COMPROBAR_MOVIMIENTO:
        return False
    try:
        import cv2
        import numpy as np
        a = img if img is not None else ctrl.capture()
        time.sleep(espera)
        b = ctrl.capture()
        if a is None or b is None or a.shape != b.shape:
            return False
        h, w = a.shape[:2]
        m = max(8, int(MOVIMIENTO_RECORTE * w / 1600.0) // 2)
        cx, cy = (int(punto[0]), int(punto[1])) if punto is not None else (w // 2, h // 2)
        cx = min(max(cx, m), w - m)
        cy = min(max(cy, m), h - m)
        ra = cv2.cvtColor(a[cy - m:cy + m, cx - m:cx + m], cv2.COLOR_BGR2GRAY).astype(np.int16)
        rb = cv2.cvtColor(b[cy - m:cy + m, cx - m:cx + m], cv2.COLOR_BGR2GRAY).astype(np.int16)
        return float(np.abs(ra - rb).mean()) > MOVIMIENTO_UMBRAL
    except Exception:                                          # noqa: BLE001
        return False
