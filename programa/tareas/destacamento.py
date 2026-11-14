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
        for x in items:
            if (ocr.normal(x["texto"]) == ocr.normal(frase)) if exacto else ocr.coincide(x["texto"], frase):
                return x
        return None

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

    def intentos(self, items) -> int | None:
        for d in items:
            t = sin_acentos(d["texto"])
            m = re.search(r"intentos diarios\D*(\d+)\s*/\s*6", t)
            if m:
                return int(m.group(1))
        # a veces el numero va en otra linea
        d = self._busca(items, "intentos diarios")
        if d:
            for x in items:
                m = re.fullmatch(r"\s*(\d)\s*/\s*6\s*", x["texto"])
                if m and abs(x["centro"][1] - d["centro"][1]) < 30:
                    return int(m.group(1))
        return None

    def abrir(self) -> bool:
        if not self.ir_a_base():
            return False
        img, items = self._ocr("base")
        if self._busca(items, "destacamento") is None:
            d = self._busca(items, "mas", exacto=True)
            if d:
                self.ctrl.tap((d["centro"][0], d["centro"][1] - int(img.shape[0] * 0.055)))
                time.sleep(1.5)
                img, items = self._ocr("mas")
        d = self._busca(items, "destacamento")
        if d is None:
            self.log("  No encuentro Destacamento en el menú Más.")
            return False
        self.ctrl.tap((d["centro"][0], d["centro"][1] - int(img.shape[0] * 0.05)))
        time.sleep(3.0)
        img, items = self._ocr("destacamento")
        return self.intentos(items) is not None or self._busca(items, "procesando") is not None

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
            for b in botones:
                coste = self._coste_cerca(items, b, img.shape[0])
                if coste not in (None, 0):
                    continue
                if coste is None:
                    # sin cifra visible no se sabe si es gratis: no se toca
                    continue
                if self._toca_seguro(b):
                    time.sleep(2.0)
                    self.quitar_aviso()
                    n += 1
                    hecho = True
                    break
            if not hecho:
                break
        return n

    def lanzar(self, maximo=3) -> int:
        """Lanza hasta 'maximo' misiones sin gastar GEC."""
        img, items = self._ocr("lanzar")
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
        lanzadas = 0
        for _ in range(maximo):
            if self.parado():
                break
            img, items = self._ocr("misiones")
            m = re.search(r"procesando\D*(\d)\s*/\s*3", " ".join(sin_acentos(x["texto"]) for x in items))
            if m and int(m.group(1)) >= 3:
                break
            fila = next((x for x in items if re.search(r"\b(\d+\s*h|\d+\s*min)\b", sin_acentos(x["texto"]))
                         and x["centro"][0] < img.shape[1] * 0.4), None)
            if fila is None:
                break
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
        img, items = self._ocr("destacamento")
        quedan = self.intentos(items)
        self.status["intentos"] = quedan
        self.status["completadas"] = self.completar_hechas()
        if quedan:
            self.status["lanzadas"] = self.lanzar(min(3, quedan))
        self.log(f"Destacamento: intentos {quedan}/6, {self.status['completadas']} completada(s), "
                 f"{self.status['lanzadas']} lanzada(s).")
        self.status["recogidas"] = self.status["completadas"]
        self.volver_a_base()
        self.status["estado"] = "terminado"
