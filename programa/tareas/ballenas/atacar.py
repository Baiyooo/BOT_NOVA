"""Atacar una ballena: abrirla, elegir flota, saltar cerca y esperar a que muera."""
from __future__ import annotations

import time

from vision import ocr
from cerebro.memoria_eventos import numero, sin_acentos
from tareas.ballenas.deteccion import ballena_en_zoom, rojo_cerca


class _Atacar:
    """Atacar una ballena: abrirla, elegir flota, saltar cerca y esperar a que muera."""

    def abrir_ballena(self, pos, desde_zoom=False):
        """Toca la ballena y comprueba su panel. Devuelve la fuerza o None.
        Rapido (objetivo: 5-10 s): si estoy en la vista con zoom, un
        «Atrás» fijo me deja en la vista del sistema y se toca la ballena; solo
        se lee la zona del rotulo. Si el toque coge otra cosa que esta encima,
        la ballena se busca por su forma en el zoom, o se prueba cola/cabeza."""
        r = None
        for i, (dx, dy) in enumerate(((0, 0), (22, -12), (-22, 8))):
            if i or desde_zoom:
                self._atras_rapido()                 # zoom -> vista del sistema
            self.ctrl.tap((pos[0] + dx, pos[1] + dy))
            time.sleep(1.2)
            r = self._espera_texto(("ballena de eter",), 4, "panel_ballena", zona=self.ZONA_ROTULO)
            if r is not None:
                break
            img_z, items_z = self._ocr("zoom_ballena", self.ZONA_MENU)
            z = ballena_en_zoom(img_z) if self._busca(items_z, "marcador") else None
            if z is not None:
                self.ctrl.tap(z)
                time.sleep(1.0)
                r = self._espera_texto(("ballena de eter",), 3, "panel_ballena", zona=self.ZONA_ROTULO)
                if r is not None:
                    break
        if r is None:
            self._atras_rapido()
            return None
        img, items, _ = r
        f = self._busca(items, "fuerza")
        fuerza = None
        for d in items:
            n = numero(d["texto"])
            if n and n >= 1_000_000 and (fuerza is None or n > fuerza):
                fuerza = n
        return fuerza or (1 if f else None)

    # ----------------------------------------------- 3) ataque a la vez --
    def _tarjeta_libre(self, items, h):
        """Primera tarjeta con cabecera Salto o Base. (x, y_cara, modo)."""
        cab = [d for d in items if sin_acentos(d["texto"]) in
               ("salto", "base", "inactivo", "moviendose", "estabilizando")
               and d["centro"][1] < h * 0.35]
        cab.sort(key=lambda d: d["centro"][0])
        for d in cab:
            t = sin_acentos(d["texto"])
            if t in ("salto", "base", "inactivo"):
                return d["centro"][0], int(d["centro"][1] + h * 0.2), t
        return None

    def _leer_viaje(self) -> int | None:
        """Segundos de viaje de la flota recien enviada (contador 00:00:SS)."""
        img, items = self._ocr("viaje")
        mejores = []
        for d in items:
            t = d["texto"].replace(" ", "")
            if len(t) >= 7 and t[2] == ":" and t[5] == ":" and t.replace(":", "").isdigit():
                s = int(t[:2]) * 3600 + int(t[3:5]) * 60 + int(t[6:8])
                if 0 < s < 600:
                    mejores.append(s)
        return min(mejores) if mejores else None

    def _ayudante(self):
        """Tarea de piratas para reutilizar su dialogo «Elige tu flota»
        (Seleccionar todo + Salto de flota / OK)."""
        from tareas.piratas.sigilo import PiratasSigilo
        h = PiratasSigilo(self.ctrl, log=self._log, stop=self.stop, atacar=True, usar_salto=True)
        h.diag_dir = self.diag_dir
        return h

    def _dialogo_una_flota(self, boton: str) -> bool:
        """«Elige tu flota» (con Seleccionar todo): marca SOLO la primera flota
        (la del primer almirante, POSS1 o como se llame) y pulsa «Salto de
        flota» u «OK». Nunca «Seleccionar todo» ni «Encubrimiento»."""
        import re
        r = self._espera_texto(("elige tu flota",), 6, "elige")
        if r is None:
            self.log("  No sale «Elige tu flota».")
            return False
        img, items, _ = r
        h, w = img.shape[:2]
        # la fila de las fuerzas (1.396.523.325...) marca las tarjetas
        fuerzas = sorted((d for d in items if re.fullmatch(r"[\d.,]{9,}", d["texto"].replace(" ", ""))
                          and h * 0.45 < d["centro"][1] < h * 0.75), key=lambda d: d["centro"][0])
        if not fuerzas:
            self.log("  No veo las tarjetas de las flotas.")
            self.ctrl.back()
            return False
        x, y = fuerzas[0]["centro"]
        self.ctrl.tap((x, int(y - h * 0.18)))           # la cara del almirante
        time.sleep(1.0)
        img, items = self._ocr("una_flota")
        if boton == "salto":
            b = self._busca(items, "salto de flota", zona=(0.5, 0.6, 0.85, 0.85), w=w, h=h)
        else:
            b = next((d for d in items if ocr.normal(d["texto"]).replace("0", "o") == "ok"
                      and d["centro"][0] > w * 0.6 and h * 0.6 < d["centro"][1] < h * 0.85), None)
            if b is None:
                s = self._busca(items, "salto de flota", zona=(0.5, 0.6, 0.85, 0.85), w=w, h=h)
                if s:                                   # OK va a la derecha del salto
                    b = {"centro": (int(s["centro"][0] + w * 0.155), int(s["centro"][1] + h * 0.028))}
        sel = " ".join(d["texto"] for d in items)
        if "(0/" in sel.replace(" ", ""):
            # la tarjeta ya venia marcada y el toque la ha desmarcado: otra vez
            self.ctrl.tap((x, int(y - h * 0.18)))
            time.sleep(1.0)
            img, items = self._ocr("una_flota")
            sel = " ".join(d["texto"] for d in items)
        if b is None or "(0/" in sel.replace(" ", ""):
            self.log(f"  No he podido elegir la primera flota / botón «{boton}»; no envío.")
            self.ctrl.back()
            return False
        self.ctrl.tap(b["centro"])
        time.sleep(1.5)
        return True

    def saltar_cerca(self, pos, abierta: bool = False) -> bool:
        """Salta con la PRIMERA flota a un hueco PEGADO a la ballena, en la vista
        con zoom (con su menu abierto la ballena queda en el centro). Primer
        toque fuera: cierra el menu; segundo en el hueco: «Movimiento en grupo».
        Si cae en otra cosa: «Atrás» a la vista del sistema, reabrir la ballena
        (rapido) y probar el hueco siguiente."""
        for dx, dy in ((0, 0.14), (0, -0.17), (-0.14, 0.05), (0.14, 0.05), (0, 0.24)):
            if self.parado():
                return False
            if not abierta and self.abrir_ballena(pos, desde_zoom=True) is None:
                return False
            img = self.ctrl.capture()
            h, w = img.shape[:2]
            p = (int(w / 2 + dx * w), int(h / 2 + dy * h))
            # NUNCA saltar encima de una flota (de otro jugador o nuestra): se
            # descartan los huecos cerca de barras de vida / aros de flota
            try:
                from tareas.piratas.sigilo import PiratasSigilo
                estorbos = PiratasSigilo._estorbos(img)
            except Exception:                         # noqa: BLE001
                estorbos = []
            if any((p[0] - ex) ** 2 + (p[1] - ey) ** 2 < (r + 40) ** 2 for ex, ey, r in estorbos):
                continue
            self.ctrl.tap(p)                         # cierra el menu de la ballena
            time.sleep(0.8)
            self.ctrl.tap(p)                         # abre el del hueco
            time.sleep(1.0)
            img, items = self._ocr("menu_hueco", self.ZONA_MENU)
            m = self._busca(items, "movimiento en grupo", w=w, h=h) or next(
                (d for d in items if ocr.normal(d["texto"]) == "movimiento"), None)
            # tiene que ser el menu de un HUECO vacio (Mover flota / Construir /
            # Salto de estacion), nunca el de una flota o un jugador
            hueco = any(any(k in ocr.normal(d["texto"]) for k in ("mover flota", "construir", "salto de estac"))
                        for d in items)
            peligro = any(any(k in ocr.normal(d["texto"]) for k in ("atacar flota", "defender", "llamar"))
                          for d in items)
            if m and (not hueco or peligro):
                self.log("  Ese punto no es un hueco vacío (hay una flota): no salto ahí.")
                self._cerrar_menu_mapa()
                m = None
            if m:
                self.log("  Hueco pegado a la ballena: salto con la primera flota.")
                self.ctrl.tap(m["centro"])
                if self._dialogo_una_flota("salto"):
                    time.sleep(3.0)
                    return True
                return False
            abierta = False                          # reabrir la ballena y otro hueco
        return False

    def atacar_ballena(self, ciclo: str, idx: int, pos) -> bool:
        """Las dos cuentas saltan con su PRIMERA flota al
        lado de la ballena y despues la atacan a la vez con «Ataque de grupo»
        eligiendo esa misma flota."""
        fuerza = self.abrir_ballena(pos)
        if fuerza is None:
            self.log(f"  No veo la ballena {idx + 1} en {pos}.")
            return False
        self.log(f"  Ballena {idx + 1}: fuerza {fuerza:,}.".replace(",", "."))
        if not self.saltar_cerca(pos, abierta=True):     # la ballena ya esta abierta
            self.log("  No he podido saltar al lado; ataco desde donde estoy.")
        clave = f"{ciclo}:{idx}"
        self.sync.escribir(listo=clave, listo_t=time.time(), llegada=None)
        otro = self.sync.esperar(lambda d: d.get("listo") == clave, 300, self.parado)
        if otro is None:
            self.log("  La otra cuenta no llega a tiempo; no ataco solo.")
            return False
        if self.abrir_ballena(pos, desde_zoom=True) is None:
            self.mi_sistema()
            vivas = self.ver_ballenas()
            if vivas:
                pos = min(vivas, key=lambda v: (v[0] - pos[0]) ** 2 + (v[1] - pos[1]) ** 2)
            if self.abrir_ballena(pos) is None:
                self.log("  Tras el salto no vuelvo a ver la ballena.")
                return False
        img, items = self._ocr("menu_ballena", self.ZONA_MENU)
        h, w = img.shape[:2]
        g = self._busca(items, "ataque de grupo", w=w, h=h)
        if not g:
            # el lector lo parte en dos lineas: «Ataque» / «de grupo»
            g = next((d for d in items if ocr.normal(d["texto"]) == "ataque"
                      and d["centro"][0] > w * 0.55), None)
        if not g:
            self.log("  No veo «Ataque de grupo» en el menú de la ballena.")
            self._atras_juego()
            return False
        t0 = max(self.sync.leer().get("listo_t", 0), otro.get("listo_t", 0)) + 2.0
        while time.time() < t0 and not self.parado():
            time.sleep(0.05)
        self.ctrl.tap(g["centro"])
        ok = self._dialogo_una_flota("ok")
        self.sync.escribir(enviado=clave, llegada=time.time() + 15)
        if ok:
            self.log("  Ataque lanzado con la primera flota.")
        return ok

    def esperar_muerte(self, pos, maximo=480) -> bool:
        """Espera a que no quede rojo (ni circulo ni triangulo "!") donde
        estaba la ballena, dos veces seguidas."""
        time.sleep(20)
        vacias, fin = 0, time.time() + maximo
        while time.time() < fin and not self.parado():
            self._quitar_salir()
            imgs = []
            for _ in range(5):
                imgs.append(self.ctrl.capture())
                time.sleep(0.45)
            if self.menu_abierto(imgs[-1]) or self._busca(ocr.leer(imgs[-1], (0, 0, 0.2, 0.15)),
                                                          "atras"):
                self.mi_sistema()                # no estoy en la vista general
                continue
            rojo = rojo_cerca(imgs, pos)
            vacias = 0 if rojo > 120 else vacias + 1
            if vacias >= 2:
                return True
            time.sleep(8)
        return False

    def _zoom_a_muerte(self):
        """Centra la camara donde murio la ballena y pasa a 2D: en la vista del
        sistema (3D) se toca ese punto (el juego acerca la camara alli), se
        cierra el menu que salga con un toque en el mismo sitio y se pone 2D.
        Las gemas quedan alrededor del centro de la pantalla."""
        self.mi_sistema()
        self._modo("3d")
        c0 = getattr(self, "_muerte", None)
        if c0 is not None:
            self.ctrl.tap(c0)
            time.sleep(1.5)
            img = self.ctrl.capture()
            h, w = img.shape[:2]
            self.ctrl.tap((int(w * 0.5), int(h * 0.5)))   # cerrar el menu (queda centrado)
            time.sleep(0.8)
        self._modo("2d")
        time.sleep(1.0)
