"""Destacamento de exploracion, con este procedimiento
(30 oct 2026, claude/destacamento.md).

Reglas fijas:
  - 6 intentos al dia en dos tandas de 3: por la mañana (9:00-17:00) y por la
    tarde-noche (17:01-1:00), hora de España. El contador se reinicia a la 1:00.
  - Nunca se gasta GEC: no se pulsa "Actualizar" (100 GEC) ni "Completar
    rapidamente". "Completo" solo se pulsa si su coste es 0 (cuando ya ha
    pasado el tiempo de la mision: es la unica forma de darla por hecha y
    cuenta para las misiones de eventos).
  - "Despacho rapido" lanza las 3 de golpe: solo si no muestra coste.
  - Si no, cada mision a mano: tocarla > Seleccionar > Seleccion automatica
    (elige almirantes que cumplen los iconos) > Iniciar mision. Maximo 3 a la
    vez ("Procesando N/3").
  - Cualquier aviso que pida confirmar algo de pago se responde con No.
Solo se tocan textos de esa lista blanca (leidos con OCR)."""
from __future__ import annotations

import re
import time

from vision import ocr
from cerebro.memoria_eventos import sin_acentos
from tareas.recompensas import Recompensas
from vision.plantillas import localizar

PROHIBIDOS = ("actualizar", "completar rapidamente", "comprar", "gec")


class Destacamento(Recompensas):
    NOMBRE = "Destacamento"

    def __init__(self, ctrl, log=None, stop=None, diag=True):
        super().__init__(ctrl, log=log, stop=stop, diag=diag)
        self.status = {"estado": "en espera", "lanzadas": 0, "completadas": 0,
                       "intentos": None, "recogidas": 0}

    def _ocr(self, etiqueta):
        img = self.cap(etiqueta)
        return img, ocr.leer(img)

    @staticmethod
    def _busca(items, frase, exacto=False):
        """El lector a veces junta las palabras («DespachoRapido»,
        «Intentosdiarios»): se compara tambien sin espacios."""
        f = ocr.normal(frase).replace(" ", "")
        for x in items:
            t = ocr.normal(x["texto"])
            if exacto:
                if t == ocr.normal(frase) or t.replace(" ", "") == f:
                    return x
            elif ocr.coincide(x["texto"], frase) or ocr.coincide(t.replace(" ", ""), f):
                return x
        return None

    def abierto(self, items) -> bool:
        """Pantalla de Destacamento de exploracion (su titulo o «Intentos diarios»)."""
        return self._busca(items, "destacamento de exploracion") is not None or \
            self._busca(items, "intentos diarios") is not None

    @staticmethod
    def _leer_binario(img, x0, y0, x1, y1) -> str:
        """Lee un recorte en blanco y negro (la letra del contador, sobre el
        fondo del mapa, el lector la confunde: «9/E» por «3/6»)."""
        import cv2
        g = cv2.cvtColor(img[max(0, y0):y1, max(0, x0):x1], cv2.COLOR_BGR2GRAY)
        if g.size == 0:
            return ""
        _, b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        b = cv2.cvtColor(cv2.copyMakeBorder(b, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255),
                         cv2.COLOR_GRAY2BGR)
        return " ".join(d["texto"] for d in ocr.leer(b, escala=3))

    @staticmethod
    def contadores(items, img) -> list[int]:
        """Segundos que le quedan a cada mision en marcha (los contadores de
        la lista «Procesando», abajo a la izquierda)."""
        h, w = img.shape[:2]
        out = []
        for x in items:
            m = re.fullmatch(r"\s*(\d{1,2}):(\d{2}):(\d{2})\s*", x["texto"])
            if m and x["centro"][0] < w * 0.25 and x["centro"][1] > h * 0.62:
                out.append(int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)))
        return out[:3]

    @classmethod
    def en_proceso(cls, items, img) -> int:
        """Misiones en «Procesando» (el «3/3» el lector no lo lee bien): sus
        filas, tanto las que llevan contador como las ya acabadas, que en vez
        del contador llevan un regalo («Completado» en el mapa)."""
        h, w = img.shape[:2]
        filas = [x for x in items if x["centro"][0] < w * 0.25 and h * 0.62 < x["centro"][1] < h * 0.87
                 and len(re.sub(r"[^a-z]", "", sin_acentos(x["texto"]))) >= 4
                 and "procesando" not in sin_acentos(x["texto"])]
        return min(3, max(len(filas), len(cls.contadores(items, img))))

    @staticmethod
    def disponibles(items, img) -> list:
        """Misiones que se pueden lanzar: las filas de la lista «Mision de
        destacamento» (arriba a la izquierda). Nunca «Mision adicional» (de pago)."""
        h, w = img.shape[:2]
        out = []
        for x in items:
            t = sin_acentos(x["texto"]).replace(" ", "")
            if not (x["centro"][0] < w * 0.24 and h * 0.19 < x["centro"][1] < h * 0.55):
                continue
            if len(t) < 3 or "adicional" in t or "misiondedestacamento" in t or \
                    any(p.replace(" ", "") in t for p in PROHIBIDOS):
                continue
            out.append(x)
        return out

    @staticmethod
    def _coste_cerca(items, d, h) -> int | None:
        """Numero que acompaña a un boton (su coste), justo debajo o al lado."""
        cx, cy = d["centro"]
        for x in items:
            if x is d:
                continue
            if abs(x["centro"][0] - cx) < 130 and 0 <= x["centro"][1] - cy < 0.08 * h:
                m = re.fullmatch(r"\s*(\d[\d.,]*)\s*", x["texto"])
                if m:
                    return int(m.group(1).replace(".", "").replace(",", ""))
        return None

    @classmethod
    def _coste(cls, img, items, d) -> int | None:
        """Coste del boton d: la cifra de debajo. Un «0» suelto el lector no
        lo ve; entonces se lee el recorte en blanco y negro."""
        h = img.shape[0]
        c = cls._coste_cerca(items, d, h)
        if c is not None:
            return c
        k = h / 900.0
        cx, cy = d["centro"]
        t = cls._leer_binario(img, int(cx - 80 * k), int(cy + 12 * k), int(cx + 80 * k), int(cy + 48 * k))
        m = re.search(r"(\d[\d.,]*)", t)
        return int(m.group(1).replace(".", "").replace(",", "")) if m else None

    def intentos(self, items, img=None) -> int | None:
        """Intentos que quedan hoy (el «N/6» de arriba a la derecha)."""
        for d in items:
            t = sin_acentos(d["texto"])
            m = re.search(r"intentos\s*diarios\D*(\d)\s*/\s*6", t)
            if m:
                return int(m.group(1))
        if img is None:
            return None
        h, w = img.shape[:2]
        d = self._busca(items, "intentos diarios")
        if d is not None:
            x0 = d["caja"][0] + d["caja"][2] - 5
            y0, y1 = d["centro"][1] - int(h * 0.025), d["centro"][1] + int(h * 0.025)
        else:
            x0, y0, y1 = int(w * 0.92), int(h * 0.083), int(h * 0.136)
        m = re.search(r"(\d)\s*/\s*6", self._leer_binario(img, x0, y0, w, y1))
        return int(m.group(1)) if m else None

    @staticmethod
    def _icono_destacamento(items, w):
        """El rotulo «Destacamento de exploracion» de la columna derecha (el
        lector lo parte: «Destacam» / «ento de» / «exploraci»)."""
        for d in items:
            t = ocr.normal(d["texto"]).replace(" ", "")
            if d["centro"][0] > w * 0.6 and (t.startswith("destacam") or t.startswith("destacamento")):
                return d
        return None

    def abrir(self) -> bool:
        """Base > el «Mas» de la columna derecha (justo debajo de «Eventos»)
        > «Destacamento de exploracion». Nunca el «Mas» de abajo ni el de
        arriba."""
        if not self.ir_a_base():
            return False
        img = self.cap("base")
        h, w = img.shape[:2]
        zona = (0.6, 0.1, 1, 0.8)
        d = self._icono_destacamento(ocr.leer(img, zona=zona), w)
        if d is None:
            p, c, _ = localizar(img, "mas_lado")
            if p < 0.85:
                self.log("  No veo el «Más» de la columna derecha (debajo de Eventos).")
                return False
            self.ctrl.tap((c[0], c[1] - int(h * 0.055)))          # despliega la columna
            time.sleep(1.8)
            img = self.cap("mas_lado")
            d = self._icono_destacamento(ocr.leer(img, zona=zona), w)
        if d is None:
            self.log("  No encuentro «Destacamento de exploración» en la columna derecha.")
            return False
        self.ctrl.tap((d["centro"][0], d["centro"][1] - int(h * 0.05)))     # su icono, encima
        time.sleep(3.0)
        img, items = self._ocr("destacamento")
        return self.abierto(items)

    def _toca_seguro(self, d):
        if any(p in sin_acentos(d["texto"]) for p in PROHIBIDOS):
            return False
        self.ctrl.tap(d["centro"])
        return True

    def completar_hechas(self) -> int:
        """Pulsa "Completo" en las misiones cuyo coste ya es 0."""
        n = 0
        for _ in range(4):
            img, items = self._ocr("completo")
            botones = [d for d in items if sin_acentos(d["texto"]) == "completo"]
            hecho = False
            # todas las de «Procesando» con regalo y ningun contador: ya han
            # acabado, asi que «Completo» esta a 0 (ese «0» suelto, junto al
            # icono de GEC, el lector no siempre lo ve)
            acabadas = not self.contadores(items, img) and self.en_proceso(items, img) > 0
            for b in botones:
                coste = self._coste(img, items, b)
                if coste not in (None, 0):
                    continue
                if coste is None and not acabadas:
                    # sin cifra visible y con contadores: no se sabe si es gratis
                    continue
                if self._toca_seguro(b):
                    time.sleep(2.0)
                    img2, items2 = self._ocr("completo_aviso")
                    if self._busca(items2, "gec") or self._busca(items2, "comprar"):
                        self.log("  «Completo» pide GEC: lo cancelo.")
                        no = self._busca(items2, "no", exacto=True) or self._busca(items2, "cancelar")
                        self.ctrl.tap(no["centro"]) if no else self.atras()
                        time.sleep(1.5)
                        return n
                    self.quitar_aviso()
                    n += 1
                    hecho = True
                    break
            if not hecho:
                break
        return n

    def lanzar(self, maximo=3) -> int:
        """Lanza hasta 'maximo' misiones sin gastar GEC (solo si hay misiones
        en la lista y huecos libres en «Procesando»)."""
        img, items = self._ocr("lanzar")
        if not self.disponibles(items, img) or self.en_proceso(items, img) >= 3:
            return 0
        d = self._busca(items, "despacho rapido")
        if d is not None and self._coste_cerca(items, d, img.shape[0]) in (None, 0):
            # Despacho rapido sin coste visible: se prueba y se comprueba que
            # no sale ningun aviso de pago
            if self._toca_seguro(d):
                time.sleep(2.0)
                img2, items2 = self._ocr("despacho")
                if self._busca(items2, "gec") or self._busca(items2, "comprar"):
                    self.log("  Despacho rápido pide GEC: lo cancelo.")
                    self.atras()
                else:
                    iniciar = self._busca(items2, "iniciar") or self._busca(items2, "confirmar")
                    if iniciar and self._toca_seguro(iniciar):
                        time.sleep(2.5)
                        return maximo
                    # a veces las lanza directamente, sin preguntar
                    self.quitar_aviso()
                    img3, items3 = self._ocr("despacho_hecho")
                    if self.abierto(items3) and self.contadores(items3, img3):
                        self.log("  Despacho rápido: misiones lanzadas.")
                        return min(maximo, len(self.contadores(items3, img3)))
        lanzadas = 0
        for _ in range(maximo):
            if self.parado():
                break
            img, items = self._ocr("misiones")
            if self.en_proceso(items, img) >= 3:
                break
            filas = self.disponibles(items, img)
            if not filas:
                break
            fila = filas[0]
            self.ctrl.tap(fila["centro"])
            time.sleep(1.5)
            for paso in ("seleccionar", "seleccion automatica", "iniciar mision"):
                img, items = self._ocr(paso)
                b = self._busca(items, paso)
                if b is None or not self._toca_seguro(b):
                    self.log(f"  No veo «{paso}»; dejo esta misión.")
                    self.atras()
                    break
                time.sleep(1.8)
            else:
                lanzadas += 1
        return lanzadas

    def run(self, ciclos: int = 1):
        if not ocr.disponible():
            self.log("Destacamento: falta el lector de texto.")
            return
        self.status["estado"] = "abriendo destacamento"
        if not self.abrir():
            self.log("Destacamento: no se ha abierto.")
            self.volver_a_base()
            return
        self.status["completadas"] = self.completar_hechas()
        img, items = self._ocr("destacamento")
        quedan = self.intentos(items, img)
        self.status["intentos"] = quedan
        if quedan != 0 and not getattr(self, "solo_completar", False):
            self.status["lanzadas"] = self.lanzar(3 if quedan is None else min(3, quedan))
        img, items = self._ocr("destacamento")
        cont = self.contadores(items, img)
        marcha = self.en_proceso(items, img)            # con contador o ya acabadas
        libres = len(self.disponibles(items, img))
        self.status["en_marcha"] = marcha
        # cuando acaben los contadores, «Completo» pasa a 0 y se puede pulsar:
        # la Rutina vuelve entonces (no antes: antes cuesta GEC)
        self.status["fin_proceso"] = time.time() + max(cont) + 60 if cont else 0
        # la tanda esta hecha si se ha lanzado algo, si ya van 3 en marcha o
        # si no quedan intentos hoy; si no (aun no han salido las misiones de
        # la tarde, o algo ha fallado), la Rutina lo vuelve a intentar luego
        #  (mañana: hecha con 3/6 o menos; tarde: con 0/6)
        tope = 3 if getattr(self, "tanda", "") == "manana" else 0
        if quedan is not None:
            self.status["ok"] = bool(self.status["lanzadas"]) or quedan <= tope
        else:
            self.status["ok"] = bool(self.status["lanzadas"]) or marcha >= 3
        espera = ""
        if cont:
            fin = time.strftime("%H:%M", time.localtime(self.status["fin_proceso"]))
            espera = f" Las en marcha acaban hacia las {fin}: entonces pulso «Completo» (a 0)."
        self.log(f"Destacamento: intentos {quedan if quedan is not None else '?'}/6, "
                 f"{self.status['completadas']} completada(s), {self.status['lanzadas']} lanzada(s), "
                 f"{marcha}/3 en marcha, {libres} por lanzar.{espera}")
        self.status["recogidas"] = self.status["completadas"]
        self.volver_a_base()
        self.status["estado"] = "terminado"
