"""Llamar a las flotas que se quedan paradas fuera de la estacion.

Las flotas que acaban un ataque se quedan en el
sistema y pueden molestar a otros jugadores; si solo estan esperando, se
llaman de vuelta con su boton "Llamar".

Donde: columna derecha (igual en la vista del sistema que en la de la base,
asi que desde el sistema no se va a la estacion), el boton de debajo de
"Mas" (el de la cola
de construccion, lo que ponga, que cambia) abre un panel con pestañas
Economia / Buque insignia / Flotas / Mejoras / Alianza / Nucleo. En "Flotas"
cada fila es "POSS1 (Base)  Falom" con un boton a la derecha ("Gestionar"
si esta en la base).

Reglas fijas: solo se pulsa "Llamar" en filas cuyo estado diga que la flota
esta parada fuera (Inactivo, En espera, Estacionada...). Nunca se tocan las
que se mueven, combaten, vuelven o estan en la base, ni "Acelerar",
"Gestionar" o "Llamar a todos". Estados que no conoce: los apunta y no toca.
"""
from __future__ import annotations

import re
import time

import cv2

from vision import ocr
from vision.plantillas import localizar
from vision.recursos import imagen
from tareas.recompensas import Recompensas

PARADA = ("inactivo", "inactiva", "en espera", "esperando", "estacionad", "parad", "idle",
          "detenid", "en posicion")
NO_TOCAR = ("base", "moviendose", "movimiento", "combate", "combatiendo", "atacando",
            "regresando", "volviendo", "estabilizando", "salto", "reparando", "recolectando")

# el texto "Llamar" con la letra del juego (el lector lo confunde: "Jewe17");
# recortado de una captura a 1600x900. Si coincide >= 0.85 en el boton de la fila,
# es "Llamar" (en las 6 filas reales da 0.95-1.00; fuera del boton, 0.68 o menos)
_LLAMAR = None


def _plantilla_llamar():
    global _LLAMAR
    if _LLAMAR is None:
        _LLAMAR = cv2.cvtColor(imagen("flotas", "llamar.png"), cv2.COLOR_BGR2GRAY)
    return _LLAMAR


def boton_llamar(img, y_fila):
    """(puntos, centro) del texto 'Llamar' en el boton de la fila (columna 0.72-0.86)."""
    h, w = img.shape[:2]
    t = _plantilla_llamar()
    if (w, h) != (1600, 900):
        t = cv2.resize(t, None, fx=w / 1600, fy=h / 900)
    y0, y1 = max(0, int(y_fila - h * 0.03)), min(h, int(y_fila + h * 0.08))
    x0, x1 = int(w * 0.72), int(w * 0.86)
    g = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    if g.shape[0] < t.shape[0] or g.shape[1] < t.shape[1]:
        return 0.0, None
    r = cv2.matchTemplate(g, t, cv2.TM_CCOEFF_NORMED)
    _, mx, _, (px, py) = cv2.minMaxLoc(r)
    return float(mx), (x0 + px + t.shape[1] // 2, y0 + py + t.shape[0] // 2)


def botones_llamar(img, umbral=0.85):
    """Centros de todos los botones «Llamar» de la lista (columna 0.72-0.86),
    de arriba abajo. No depende del nombre de las flotas (cada jugador pone
    el suyo): solo de la imagen del texto «Llamar»."""
    h, w = img.shape[:2]
    t = _plantilla_llamar()
    if (w, h) != (1600, 900):
        t = cv2.resize(t, None, fx=w / 1600, fy=h / 900)
    y0, y1 = int(h * 0.12), int(h * 0.97)
    x0, x1 = int(w * 0.72), int(w * 0.86)
    g = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    r = cv2.matchTemplate(g, t, cv2.TM_CCOEFF_NORMED)
    out = []
    while True:
        _, mx, _, (px, py) = cv2.minMaxLoc(r)
        if mx < umbral:
            break
        out.append((x0 + px + t.shape[1] // 2, y0 + py + t.shape[0] // 2))
        r[max(0, py - t.shape[0]):py + t.shape[0], :] = -1     # una por fila
    return sorted(out, key=lambda c: c[1])


class LlamarFlotas(Recompensas):
    NOMBRE = "Llamar flotas paradas"

    def __init__(self, ctrl, log=None, stop=None, diag=True):
        super().__init__(ctrl, log=log, stop=stop, diag=diag)
        self.status = {"estado": "en espera", "llamadas": 0, "recogidas": 0}
        self.desconocidos = []

    def _en_sistema(self, img) -> bool:
        """Vista del sistema (se ve el boton «Estacion espacial»)."""
        return localizar(img, "estacion")[0] >= 0.80

    def _abrir_panel(self) -> bool:
        # el boton esta igual en la vista del sistema que en la de la base:
        # desde el sistema no hace falta ir a la estacion
        img = self.cap("base_flotas")
        self._desde_sistema = self._en_sistema(img)
        if not self._desde_sistema:
            if not self.ir_a_base():
                return False
            img = self.cap("base_flotas")
        h, w = img.shape[:2]
        # siempre en el mismo sitio: columna derecha, debajo de "Mas"
        # (medido a 1600x900: "Mas" en y=411, el boton en (1555, 485))
        punto = (int(w * 1555 / 1600), int(h * 485 / 900))
        self.ctrl.tap(punto)
        # espera adaptativa: sale en cuanto se lee la pestaña Flotas (max 3 s)
        f = None
        time.sleep(1.0)
        fin = time.time() + 3.0
        while True:
            img = self.cap("panel_flotas")
            items = ocr.leer(img, zona=(0.85, 0.05, 1, 0.95))
            f = ocr.buscar(items, "flotas", zona=(0.85, 0.05, 1, 0.95), w=w, h=h)
            # el panel esta abierto de verdad solo si ademas se lee «acelerar» o «buque insignia»
            if f is not None and self._abierto(img) is None:
                f = None
            if f is not None or time.time() >= fin or self.parado():
                break
            time.sleep(0.5)
        if f is None:
            self.log("  No se ha abierto el panel con la pestaña Flotas.")
            self._cerrar()
            return False
        self.ctrl.tap(f["centro"])
        time.sleep(1.0)
        return True

    def _abierto(self, img=None):
        """'ficha' si esta abierta la ficha de una flota, 'panel' si el panel de
        flotas, None si ninguno."""
        img = self.cap("cerrar_panel") if img is None else img
        h, w = img.shape[:2]
        items = ocr.leer(img, zona=(0.3, 0.05, 1, 0.5))
        if ocr.buscar(items, "estado de la flota", w=w, h=h):
            return "ficha"
        if ocr.buscar(items, "acelerar", zona=(0.55, 0.05, 0.9, 0.2), w=w, h=h) or \
                ocr.buscar(items, "buque insignia", zona=(0.85, 0.05, 1, 0.5), w=w, h=h):
            return "panel"
        return None

    def _cerrar(self):
        """Cierra la ficha de flota (si se abrio) y el panel. Comprueba con el
        lector que de verdad se han cerrado (los iconos de la base se ven igual
        con el panel abierto)."""
        for i in range(4):
            img = self.cap("cerrar_panel")
            h, w = img.shape[:2]
            que = self._abierto(img)
            if que is None and self._cerrado_seguro(img):
                return True
            if que is None:
                time.sleep(0.6)               # el lector no ve nada claro: no es «cerrado»
                continue
            if que == "ficha" or i >= 2 or getattr(self, "_desde_sistema", False):
                # la tecla Atras cierra dialogos (en el sistema, tocar fuera
                # podria seleccionar algo del mapa)
                self.atras(img)
            else:
                # el panel se cierra tocando fuera, a la izquierda (la base)
                self.ctrl.tap((int(w * 0.30), int(h * 0.55)))
            time.sleep(0.9)
        img = self.cap("cerrar_panel")
        return self._abierto(img) is None and self._cerrado_seguro(img)

    def _cerrado_seguro(self, img) -> bool:
        """Panel cerrado de verdad: el lector no ve ni panel ni ficha Y se ve la
        base o el sistema (un OCR vacio no basta)."""
        return self.en_base(img) or self._en_sistema(img)

    def _filas(self, img):
        """[(nombre, estado, boton_dict)] de la lista de flotas. boton_dict["texto"]
        es "llamar" si el boton de la fila dice Llamar (lector o plantilla)."""
        h, w = img.shape[:2]
        items = ocr.leer(img, zona=(0.38, 0.08, 0.9, 0.95))
        filas = []
        for d in items:
            m = re.search(r"([a-z0-9]{2,10})\s*\(([^)]+)\)?", d["texto"], re.I)
            if not m or d["centro"][0] > w * 0.7:
                continue
            estado = ocr.normal(m.group(2))
            yf = d["centro"][1]
            # su boton: el texto de la derecha en esa fila (un poco mas abajo que el nombre)
            boton = min((x for x in items if x["centro"][0] > w * 0.72
                         and -h * 0.02 < x["centro"][1] - yf < h * 0.06),
                        key=lambda x: abs(x["centro"][1] - yf), default=None)
            boton = dict(boton) if boton else {"texto": "", "centro": None}
            if not ocr.coincide(boton["texto"], "llamar"):
                pt, c = boton_llamar(img, yf)
                if pt >= 0.85:
                    boton = {"texto": "llamar", "centro": c, "plantilla": round(pt, 2)}
            else:
                boton["texto"] = "llamar"
            filas.append((m.group(1).upper().replace(" ", ""), estado, boton))
        return filas

    def run(self, ciclos: int = 1):
        if not ocr.disponible():
            return
        self.status["estado"] = "mirando las flotas"
        if not self._abrir_panel():
            if not getattr(self, "_desde_sistema", False):
                self.volver_a_base()
            return
        llamadas = 0
        vacias = 0
        for _ in range(10):
            if self.parado():
                break
            img = self.cap("lista_flotas")
            bots = botones_llamar(img)
            if bots:
                vacias = 0
                self.log(f"  Flota parada fuera (botón «Llamar» {len(bots)}): la llamo.")
                self.ctrl.tap(bots[0])
                time.sleep(1.8)
                llamadas += 1
                # si en vez de llamar se ha abierto la ficha de la flota, se cierra
                if self._abierto() == "ficha":
                    self.atras()
                    time.sleep(1.2)
                continue
            # una segunda lectura antes de dar por acabado
            vacias += 1
            if vacias >= 2:
                break
            time.sleep(1.0)
        self.status["llamadas"] = llamadas
        if llamadas:
            self.log(f"Flotas: {llamadas} llamada(s) de vuelta a la estación.")
        self._cerrar()
        if not getattr(self, "_desde_sistema", False):
            self.volver_a_base()                 # desde el sistema, se queda en el sistema
        self.status["estado"] = "terminado"
