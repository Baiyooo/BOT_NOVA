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
            # espera adaptativa: sale en cuanto se ve la base
            img = self.esperar(self.en_base, 1.5, intervalo=0.3, etiqueta="inicio")
            # dos capturas seguidas con la base antes de darla por buena
            if img is not None and self.en_base(self.cap("inicio")):
                return True
            img = self.cap("inicio")
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
            def busca(fr, zona, items=items, w=w, h=h):
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
            time.sleep(0.6)
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
        time.sleep(1.4)
        img = self.cap("aviso")
        h, w = img.shape[:2]
        self.ctrl.tap((w // 2, int(h * 0.55)))
        time.sleep(0.8)

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
        if img is not None:
            # el dialogo se anima: pulsar el boton ya quieto
            img = self.esperar_quieto(2.0, etiqueta="gratis", intervalo=0.2)
        if img is None or self._ve(img, "recoger_nar") is None:
            self.log("  ¡GRATIS!: aun no esta disponible (tiene temporizador).")
            self.volver_a_base()
            return False
        self.ctrl.tap(self._ve(img, "recoger_nar"))
        self.quitar_aviso()
        self.status["recogidas"] += 1
        self.log("  ¡GRATIS!: suministros recogidos.")
        self.volver_a_base()
        try:
            time.sleep(0.5)
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
        # espera adaptativa: sale en cuanto sale el boton de recoger
        img = self.esperar(lambda i: self._ve(i, "login") is not None, 2.5,
                           intervalo=0.4, etiqueta="login")
        c = self._ve(img, "login") if img is not None else None
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
        time.sleep(0.6)
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
            time.sleep(0.9)
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
            antes = self.cap("cajas")
            self.ctrl.tap((int(x * kx), int(y * ky)))
            # la lista de la caja sale con animacion: esperar a que cambie y se quede quieta
            self.esperar_cambio(antes, 1.5, etiqueta="cajas")
            self.esperar_quieto(1.5, etiqueta="cajas", intervalo=0.2)
            self.ctrl.tap((int(w * 0.30), int(h * 0.04)))      # cerrar lo que salga
            time.sleep(0.6)
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
            # el menu se desliza: esperar a que quede quieto antes de pulsar el icono
            img = self.esperar_quieto(2.0, etiqueta="mas_lado", intervalo=0.2)
            p, c, _ = localizar(img, "simulacion")
            if p < 0.85:
                self.log("  No encuentro Simulacion en el menu lateral.")
                return False
        self.ctrl.tap((c[0], c[1] - int(img.shape[0] * 0.055)))   # el icono, encima del texto
        return self.esperar(lambda i: localizar(i, "atras")[0] >= 0.72, 4.0,
                            intervalo=0.4, etiqueta="simulacion") is not None

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
        # recorrer la lista desde donde se abre, siempre hacia la DERECHA
        # (nunca hacia la izquierda: ahi estan los capitulos ya hechos)
        img = self.cap("sim")
        h, w = img.shape[:2]
        antes = None
        for paso in range(14):
            if self.parado():
                break
            img = self.cap("sim")
            p, c, _ = localizar(img, "sim_auto")
            if p >= 0.80 and c[0] > w * 0.18:
                if self._coste_cero(img, c):
                    self.log("  Simulacion automatica (0 GEC).")
                    self.ctrl.tap(c)
                    hechas += 1
                    # cerrar el resultado si sale algo encima (sale en cuanto aparece)
                    # la X vale solo si es del popup nuevo (no estaba ya antes del toque)
                    x_antes = buscar_cerrar_x(img)
                    self.esperar_cambio(img, 4.0, etiqueta="sim_hecha")
                    nueva = self.esperar_quieto(3.0, etiqueta="sim_hecha", intervalo=0.2)
                    x = buscar_cerrar_x(nueva) if nueva is not None and x_antes is None else None
                    if x is not None:
                        self.ctrl.tap(x)
                        time.sleep(1.0)
                    continue
                self.log("  Hay una simulacion pero cuesta GEC: no la hago.")
            # final de la lista: la pantalla ya no cambia al desplazar
            if antes is not None and float(np.abs(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.int16)
                                                   - antes).mean()) < 2.0:
                break
            antes = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.int16)
            # el dedo de derecha a izquierda: la lista avanza hacia la derecha.
            # Arrastre lento y menor que una tarjeta (~480 px): rapido, la
            # inercia se salta el capitulo de hoy (pasaba de verlo cortado a
            # la derecha a verlo cortado a la izquierda)
            lento = getattr(self.ctrl, "drag_ms", None)
            try:
                if lento is not None:
                    self.ctrl.drag_ms = 1100
                self.ctrl.drag((int(w * 0.65), int(h * 0.5)), (int(w * 0.42), int(h * 0.5)))
            finally:
                if lento is not None:
                    self.ctrl.drag_ms = lento
            time.sleep(0.9)
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
                self.esperar(self.en_base, 2.0, intervalo=0.4, etiqueta="salir")
            else:
                self.volver_a_base()
                break
        self.status["estado"] = "terminado"
