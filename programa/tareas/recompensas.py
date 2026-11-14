"""Recompensas diarias, suministros gratis y simulacion de batalla."""
from __future__ import annotations

import cv2
import numpy as np
import time
from vision.detectores import _diferencia, buscar_cerrar_x
from vision.plantillas import buscar_rotulo, localizar
from vision.cifras import leer_cifras
from vision.mascaras import mascara_blanco
from vision.recursos import silueta
from tareas.base import TareaBase


class Recompensas(TareaBase):
    """Recoge lo que se puede recoger gratis, sin gastar nada:
      1. "¡GRATIS!" (suministros gratuitos con temporizador)
      2. la recompensa diaria por inicio de sesion (nunca "Rellenar")
      3. los "Recoger" verdes de las Tareas diarias (nunca "Comprar")
    Todo desde la vista de la base, con los iconos de abajo a la izquierda."""

    NOMBRE = "Recompensas diarias"
    # umbral por plantilla: las de la base salen de capturas ADB (1.00 en
    # la base, <=0.63 en el resto); las de los dialogos, de un video
    # reescalado (0.71-0.79 positivas, <=0.56 negativas)
    UMBRALES = {"diario": 0.80, "recompensa": 0.80, "recoger_nar": 0.65,
                "login": 0.65, "recoger_ver": 0.65, "estacion": 0.80}
    DX_GRATIS = 107          # el hueco de ¡GRATIS! a la derecha de Recompensa (ADB, escala 1)

    def __init__(self, ctrl, log=None, stop=None, diag=True):
        super().__init__(ctrl, log=log, stop=stop, atacar=False, diag=diag)
        self.status = {"estado": "en espera", "recogidas": 0, "paso": 0, "pasos": 3}

    def _ve(self, img, nombre, umbral=None):
        p, c, _ = localizar(img, nombre)
        return c if p >= (umbral or self.UMBRALES.get(nombre, 0.75)) else None

    def en_base(self, img) -> bool:
        if self._ve(img, "diario") is not None or self._ve(img, "recompensa") is not None:
            return True
        p, c, _ = localizar(img, "sistema")
        h, w = img.shape[:2]
        return p >= 0.85 and c[0] > w * 0.6 and c[1] > h * 0.8

    def ir_a_base(self) -> bool:
        img = self.cap("inicio")
        if self.en_base(img):
            return True
        for _ in range(5):
            c = self._ve(img, "estacion")
            if c is not None:
                self.log("  Voy a la vista de la base (Estacion espacial).")
                self.ctrl.tap(c)
                if self.esperar(self.en_base, 8.0, etiqueta="base") is not None:
                    return True
                img = self.cap("inicio")
                continue
            # en el mapa (sistema o galaxia): boton "Base" de la barra de arriba.
            # Nunca Atras de Android en el mapa: abriria "¿Seguro que quieres salir?"
            pb, cb, _ = localizar(img, "base_btn")
            h = img.shape[0]
            if pb >= 0.85 and cb[1] < h * 0.15:
                self.log("  Voy a la vista de la base (boton Base).")
                self.ctrl.tap((cb[0], cb[1] - int(h * 0.04)))
                if self.esperar(self.en_base, 8.0, etiqueta="base") is not None:
                    return True
                img = self.cap("inicio")
                continue
            # una ventana abierta (eventos, tareas, menus...): su X, su boton
            # Atras o, si no tiene ninguno, Atras de Android
            x = buscar_cerrar_x(img)
            pa, ca, _ = localizar(img, "atras")
            if x is not None:
                self.ctrl.tap(x)
            elif pa >= 0.72 and ca[0] < img.shape[1] * 0.2 and ca[1] < h * 0.15:
                self.ctrl.tap(ca)
            elif localizar(img, "eventos")[0] >= 0.80:
                break                     # mapa sin boton Base a la vista: no insistir
            else:
                self.atras(img)
            time.sleep(1.5)
            img = self.cap("inicio")
            if self.en_base(img):
                return True
        if self.en_base(self.cap("inicio")):
            return True
        return self._base_por_texto()

    def _base_por_texto(self) -> bool:
        """Ultimo recurso, leyendo la pantalla: el boton "Atras" de arriba a
        la izquierda (vistas como Recursos), "No" en el aviso de salir y el
        boton "Base" o "Estacion espacial"."""
        try:
            from vision import ocr
            if not ocr.disponible():
                return False
        except Exception:                                  # noqa: BLE001
            return False
        for _ in range(4):
            img = self.cap("base_texto")
            if self.en_base(img):
                return True
            h, w = img.shape[:2]
            items = ocr.leer(img)
            def busca(fr, zona):
                return ocr.buscar(items, fr, zona=zona, w=w, h=h)
            if busca("seguro que quieres salir", (0, 0, 1, 1)):
                d = busca("no", (0.2, 0.5, 0.5, 0.8))
                if d:
                    self.ctrl.tap(d["centro"])
                    time.sleep(1.2)
                    continue
            d = busca("atras", (0, 0, 0.2, 0.15))
            if d:
                self.log("  Salgo con Atrás (leído en pantalla).")
                self.ctrl.tap(d["centro"])
                time.sleep(1.8)
                continue
            d = busca("estacion espacial", (0.75, 0.8, 1, 1)) or busca("base", (0.3, 0, 0.8, 0.16))
            if d:
                self.ctrl.tap((d["centro"][0], d["centro"][1] - int(h * 0.04)))
                if self.esperar(self.en_base, 8.0, etiqueta="base") is not None:
                    return True
                continue
            break
        return self.en_base(self.cap("base_texto"))

    def volver_a_base(self, intentos=4) -> bool:
        """Cierra dialogos con Atras, pero SOLO mientras no se vea la base:
        en la base, Atras abriria el aviso de salir del juego."""
        esperas = 0
        for _ in range(intentos + 3):
            time.sleep(1.0)
            img = self.cap("cerrar")
            if self.en_base(img):
                return True
            x = buscar_cerrar_x(img)
            pa, ca, _ = localizar(img, "atras")
            h, w = img.shape[:2]
            if x is not None:
                self.ctrl.tap(x)
            elif pa >= 0.72 and ca[0] < w * 0.2 and ca[1] < h * 0.15:
                self.ctrl.tap(ca)
            elif (localizar(img, "base_btn")[0] >= 0.70 or localizar(img, "eventos")[0] >= 0.70
                  or _diferencia(img, self.ctrl.capture()) > 3.0):
                # mapa, base a medio cargar o pantalla en movimiento: Atras aqui
                # abriria "¿Seguro que quieres salir?". Esperar o ir con Base.
                esperas += 1
                if esperas >= 3:
                    return self.ir_a_base()
                time.sleep(1.2)
            else:
                self.atras(img)
        return self.en_base(self.cap("cerrar"))

    def quitar_aviso(self):
        """Tras recoger sale "¡Nuevos objetos!": un toque en el centro lo cierra."""
        time.sleep(1.8)
        img = self.cap("aviso")
        h, w = img.shape[:2]
        self.ctrl.tap((w // 2, int(h * 0.55)))
        time.sleep(1.2)

    # ------------------------------------------------------------ pasos --
    def _icono_gratis(self, img):
        """Centro del icono del regalo de ¡GRATIS! en la base, o None."""
        h = img.shape[0]
        pg, cg, _ = localizar(img, "gratis_adb")
        if pg >= 0.85:
            return (cg[0], cg[1] - int(h * 0.055))
        p, c, e = localizar(img, "recompensa")
        if p >= self.UMBRALES["recompensa"]:
            e = e / 1.333 if e > 1.2 else e
            return (int(c[0] + self.DX_GRATIS * e), int(c[1]))
        p, c, e = localizar(img, "diario")
        if p < self.UMBRALES["diario"]:
            return None
        e = e / 1.333 if e > 1.2 else e
        return (int(c[0] + self.DX_GRATIS * e), int(c[1] - h * 0.055))

    def gratis_restante(self, img=None):
        """Segundos que faltan para ¡GRATIS! leyendo el temporizador MM:SS que
        sale debajo del regalo. None si no se puede leer (o si ya pone
        ¡GRATIS!, que se mira aparte)."""
        if img is None:
            img = self.cap("base")
        ic = self._icono_gratis(img)
        if ic is None:
            return None
        h, w = img.shape[:2]
        f = w / 1600.0
        caja = (ic[0] - 48 * f, ic[1] + 0.04 * h, ic[0] + 48 * f, ic[1] + 0.095 * h)
        cifras = leer_cifras(img, caja, v_min=140)
        if not cifras:
            return None
        n = int("".join(str(c).zfill(2) if i else str(c) for i, c in enumerate(cifras)))
        mm, ss = n // 100, n % 100
        if n >= 10000 or ss > 59 or mm > 59 or (mm == 0 and ss == 0):
            return None
        return mm * 60 + ss

    def gratis(self):
        # El rotulo cambia: "¡GRATIS!" o un temporizador. Se pulsa el hueco
        # (a la derecha de Recompensa) y solo se recoge si sale "Recoger".
        img = self.cap("base")
        h = img.shape[0]
        pg, cg, _ = localizar(img, "gratis_adb")
        if pg < 0.85:
            falta = self.gratis_restante(img)
            self.status["gratis_espera"] = falta or 0
            if falta:
                self.log(f"  ¡GRATIS!: faltan {falta // 60} min {falta % 60:02d} s; vuelvo entonces.")
                return False
        if pg >= 0.85:
            # rotulo "¡GRATIS!" a la vista: se pulsa su icono, encima
            self.ctrl.tap((cg[0], cg[1] - int(h * 0.055)))
        else:
            # con temporizador no pone "¡GRATIS!": el hueco va a la derecha de
            # Recompensa, o de Diario si Recompensa ya no esta (recogida hoy)
            p, c, e = localizar(img, "recompensa")
            if p >= self.UMBRALES["recompensa"]:
                e = e / 1.333 if e > 1.2 else e
                self.ctrl.tap((int(c[0] + self.DX_GRATIS * e), int(c[1])))
            else:
                p, c, e = localizar(img, "diario")
                if p < self.UMBRALES["diario"]:
                    self.log("  No veo los iconos de abajo; salto ¡GRATIS!.")
                    return False
                e = e / 1.333 if e > 1.2 else e
                self.ctrl.tap((int(c[0] + self.DX_GRATIS * e), int(c[1] - h * 0.055)))
        img = self.esperar(lambda i: self._ve(i, "recoger_nar") is not None, 4.0,
                           etiqueta="gratis")
        if img is None:
            self.log("  ¡GRATIS!: aun no esta disponible (tiene temporizador).")
            self.volver_a_base()
            return False
        self.ctrl.tap(self._ve(img, "recoger_nar"))
        self.quitar_aviso()
        self.status["recogidas"] += 1
        self.log("  ¡GRATIS!: suministros recogidos.")
        self.volver_a_base()
        try:
            time.sleep(1.0)
            self.status["gratis_espera"] = self.gratis_restante() or 0
        except Exception:                                # noqa: BLE001
            self.status["gratis_espera"] = 0
        return True

    def login(self):
        img = self.cap("base")
        c = self._ve(img, "recompensa")
        if c is None:
            # el icono desaparece cuando ya se ha recogido la de hoy
            self.log("  Recompensa diaria: ya recogida hoy (no esta el icono).")
            return
        self.ctrl.tap((c[0], c[1] - int(img.shape[0] * 0.055)))
        img = self.esperar(lambda i: not self.en_base(i), 5.0, etiqueta="login")
        if img is None:
            self.log("  No se ha abierto la recompensa diaria.")
            return
        time.sleep(0.8)
        img = self.cap("login")
        c = self._ve(img, "login")
        if c is None:
            self.log("  Recompensa diaria: ya recogida hoy.")
        else:
            self.ctrl.tap(c)
            self.quitar_aviso()
            self.status["recogidas"] += 1
            self.log("  Recompensa diaria recogida.")
        self.volver_a_base()

    def diarias(self):
        img = self.cap("base")
        c = self._ve(img, "diario")
        if c is None:
            return
        self.ctrl.tap((c[0], c[1] - int(img.shape[0] * 0.055)))      # el icono, encima del texto
        if self.esperar(lambda i: not self.en_base(i), 5.0, etiqueta="diarias") is None:
            self.log("  No se han abierto las Tareas diarias.")
            return
        time.sleep(1.0)
        n, pasadas = 0, 0
        while n < 15 and pasadas < 5 and not self.parado():
            img = self.cap("diarias")
            c = self._ve(img, "recoger_ver")
            if c is not None:
                self.ctrl.tap(c)
                n += 1
                self.quitar_aviso()
                continue
            # bajar por la lista
            h, w = img.shape[:2]
            antes = img
            self.ctrl.drag((int(w * 0.45), int(h * 0.80)), (int(w * 0.45), int(h * 0.40)))
            time.sleep(1.2)
            pasadas += 1
            if _diferencia(antes, self.cap("diarias")) < 2.0:
                break                      # fin de la lista
        self.status["recogidas"] += n
        self.log(f"  Tareas diarias: {n} recompensa(s) recogida(s).")
        if not self.parado():
            self.cajas_diarias()
        self.volver_a_base()

    # cajas de "Puntos de hoy" (arriba: 30/60/90/120/150) y "semanal" (abajo:
    # 250/500/1000) de las Tareas diarias, en una pantalla de 1600x900.
    # Las listas se abren al tocarlas; las demas solo ensenan lo que dan.
    CAJAS_DIARIAS = ((527, 145), (768, 145), (1007, 145), (1250, 145), (1493, 145),
                     (696, 820), (1101, 820), (1504, 820))

    def cajas_diarias(self):
        img = self.cap("cajas")
        h, w = img.shape[:2]
        if self.en_base(img):
            return
        kx, ky = w / 1600.0, h / 900.0
        for x, y in self.CAJAS_DIARIAS:
            if self.parado():
                break
            self.ctrl.tap((int(x * kx), int(y * ky)))
            time.sleep(1.5)
            self.ctrl.tap((int(w * 0.30), int(h * 0.04)))      # cerrar lo que salga
            time.sleep(1.0)
        self.log("  Cajas de puntos diarios y semanales revisadas.")

    def run(self, ciclos: int = 1):
        self.log("Recompensas diarias: ¡GRATIS!, inicio de sesion y Tareas diarias.")
        self.status["estado"] = "yendo a la base"
        if not self.ir_a_base():
            self.log("No encuentro la vista de la base. Dejala abierta y repite.")
            self.status["estado"] = "sin_base"
            return
        for i, (nombre, paso) in enumerate((("gratis", self.gratis),
                                            ("inicio de sesion", self.login),
                                            ("tareas diarias", self.diarias)), 1):
            if self.parado():
                break
            self.status.update({"estado": nombre, "paso": i})
            try:
                paso()
            except Exception as e:                       # noqa: BLE001
                self.log(f"  Error en {nombre}: {e}")
                self.volver_a_base()
        self.status["estado"] = "parado" if self.parado() else "terminado"
        self.log(f"Hecho: {self.status['recogidas']} recompensa(s) recogida(s).")


class RecogerGratis(Recompensas):
    """Solo el hueco "¡GRATIS!" de la base (suministros con temporizador de
    unos 30-40 min). Devuelve en status["gratis_ok"] si ha recogido algo."""

    NOMBRE = "Suministros gratis"

    def run(self, ciclos: int = 1):
        self.status["gratis_ok"] = False
        if not self.ir_a_base():
            self.log("¡GRATIS!: no encuentro la vista de la base.")
            return
        try:
            self.status["gratis_ok"] = bool(self.gratis())
        except Exception as e:                           # noqa: BLE001
            self.log(f"  Error en ¡GRATIS!: {e}")
            self.volver_a_base()
        self.status["estado"] = "terminado"


class Simulacion(Recompensas):
    """Simulacion de batalla por tiempo: pulsa "Simulacion automatica" en los
    capitulos desbloqueados (de lunes a sabado uno; el domingo los que hayan
    quedado). Solo si el coste es 0 GEC. Nunca pulsa "Restablecer"."""

    NOMBRE = "Simulación"

    def _abrir(self) -> bool:
        if not self.ir_a_base():
            return False
        img = self.cap("base")
        p, c, _ = localizar(img, "simulacion")
        if p < 0.85:
            p2, c2, _ = localizar(img, "mas_lado")
            # se pulsa el icono (las flechas), que esta ENCIMA del texto "Mas"
            self.ctrl.tap((c2[0], c2[1] - int(img.shape[0] * 0.055)) if p2 >= 0.85
                          else (int(img.shape[1] * 0.964), int(img.shape[0] * 0.405)))
            img = self.esperar(lambda i: localizar(i, "simulacion")[0] >= 0.85, 5.0,
                               etiqueta="mas_lado")
            if img is None:
                self.log("  No encuentro Simulacion en el menu lateral.")
                return False
            p, c, _ = localizar(img, "simulacion")
        self.ctrl.tap((c[0], c[1] - int(img.shape[0] * 0.055)))   # el icono, encima del texto
        time.sleep(3.0)
        return localizar(self.cap("simulacion"), "atras")[0] >= 0.72

    def _coste_cero(self, img, c) -> bool:
        """El coste va debajo del boton: icono de GEC y la cifra. Solo vale un 0."""
        h, w = img.shape[:2]
        x, y = c[0] - int(44 * w / 1600), c[1] + int(31 * h / 900)
        r = int(28 * w / 1600)
        trozo = mascara_blanco(img[max(0, y - r):y + r, max(0, x - r):x + r * 2])
        cero = silueta("cero").astype(np.float32)
        if trozo.shape[0] < cero.shape[0] or trozo.shape[1] < cero.shape[1]:
            return False
        res = cv2.matchTemplate(trozo.astype(np.float32), cero, cv2.TM_CCOEFF_NORMED)
        if res.max() < 0.70:
            return False
        # solo una cifra: nada blanco a la derecha del cero
        _, _, _, ml = cv2.minMaxLoc(res)
        derecha = trozo[:, ml[0] + cero.shape[1] + 3:]
        return derecha.sum() < 15

    def run(self, ciclos: int = 1):
        self.log("Simulacion: abro la pantalla.")
        hechas = 0
        if not self._abrir():
            self.status["estado"] = "sin_simulacion"
            self.volver_a_base()
            return
        # ir al principio de la lista y recorrerla hacia la derecha
        img = self.cap("sim")
        h, w = img.shape[:2]
        for _ in range(4):
            self.ctrl.drag((int(w * 0.25), int(h * 0.5)), (int(w * 0.75), int(h * 0.5)))
            time.sleep(0.8)
        for paso in range(10):
            if self.parado():
                break
            img = self.cap("sim")
            p, c, _ = localizar(img, "sim_auto")
            if p >= 0.80 and c[0] > w * 0.18:
                if self._coste_cero(img, c):
                    self.log("  Simulacion automatica (0 GEC).")
                    self.ctrl.tap(c)
                    hechas += 1
                    time.sleep(4.0)
                    # cerrar el resultado si sale algo encima
                    img = self.cap("sim_hecha")
                    x = buscar_cerrar_x(img)
                    if x is not None:
                        self.ctrl.tap(x)
                        time.sleep(1.5)
                    continue
                self.log("  Hay una simulacion pero cuesta GEC: no la hago.")
            self.ctrl.drag((int(w * 0.70), int(h * 0.5)), (int(w * 0.40), int(h * 0.5)))
            time.sleep(1.0)
        self.status["recogidas"] = self.status.get("recogidas", 0) + hechas
        self.log(f"Simulacion: {hechas} hecha(s).")
        # salir con su boton Atras (nunca Atras de Android en la base)
        for _ in range(3):
            img = self.cap("salir")
            if self.en_base(img):
                break
            p, c = buscar_rotulo(img, "atras")
            if p >= 0.72:
                self.ctrl.tap(c)
                time.sleep(2.0)
            else:
                self.volver_a_base()
                break
        self.status["estado"] = "terminado"
