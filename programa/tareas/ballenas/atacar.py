"""Atacar una ballena: abrirla, elegir flota, saltar cerca y esperar a que muera."""
from __future__ import annotations

import time

from vision import ocr
from cerebro.memoria_eventos import numero, sin_acentos
from tareas.ballenas.deteccion import ballena_en_zoom, rojo_cerca


class _Atacar:
    """Atacar una ballena: abrirla, elegir flota, saltar cerca y esperar a que muera."""

    def _panel_ballena(self, segundos, etiqueta):
        """¿Esta abierto el panel de una ballena? Por su rotulo «Ballena de
        éter» o, si el lector lo mezcla con las etiquetas de gemas de
        alrededor, por «Fuerza» + una cifra de millones y «Ataque de grupo»
        en el menu (las estaciones y flotas de jugadores no lo tienen)."""
        fin = time.time() + segundos
        while time.time() < fin and not self.parado():
            img, items = self._ocr(etiqueta, self.ZONA_ROTULO)
            h, w = img.shape[:2]
            d = self._busca(items, "ballena de eter", zona=self.ZONA_ROTULO, w=w, h=h)
            if d is None:
                fuerza = any((numero(x["texto"]) or 0) >= 1_000_000 for x in items) and \
                    any("fuerza" in ocr.normal(x["texto"]) for x in items)
                if fuerza:
                    menu = ocr.leer(img, self.ZONA_MENU)
                    if any("ataque" in ocr.normal(x["texto"]) for x in menu) and not any(
                            k in ocr.normal(x["texto"]) for x in menu for k in ("defender", "llamar")):
                        d = {"texto": "ballena", "centro": (w // 2, h // 2)}
            if d:
                return img, items, d
            time.sleep(0.4)
        return None

    def abrir_ballena(self, pos, desde_zoom=False, aliado_nuestro=False):
        """Toca la ballena y comprueba su panel. Devuelve la fuerza o None.
        Rapido (objetivo: 5-10 s): si estoy en la vista con zoom, un
        «Atrás» fijo me deja en la vista del sistema y se toca la ballena; solo
        se lee la zona del rotulo. Si el toque coge otra cosa que esta encima,
        la ballena se busca por su forma en el zoom, o se prueba cola/cabeza.

        Con aliado_nuestro=True la «Flota aliada» del panel no cuenta como
        de otro jugador: la otra cuenta de la pareja ya la esta atacando
        (solo se pasa cuando esa cuenta ha lanzado ya su ataque a ESTA
        ballena de ESTE ciclo)."""
        r = None
        for i, (dx, dy) in enumerate(((0, 0), (22, -12), (-22, 8))):
            if i or desde_zoom:
                self._atras_rapido()                 # zoom -> vista del sistema
            self.ctrl.tap((pos[0] + dx, pos[1] + dy))
            time.sleep(1.2)
            r = self._panel_ballena(4, "panel_ballena")
            if r is not None:
                break
            img_z, items_z = self._ocr("zoom_ballena", self.ZONA_MENU)
            z = ballena_en_zoom(img_z) if self._busca(items_z, "marcador") else None
            if z is not None:
                self.ctrl.tap(z)
                time.sleep(1.0)
                r = self._panel_ballena(3, "panel_ballena")
                if r is not None:
                    break
        if r is None:
            self._atras_rapido()
            return None
        return self._fuerza_del_panel(r, aliado_nuestro)

    def _fuerza_del_panel(self, r, aliado_nuestro=False, atras=None):
        """De un panel de ballena ya abierto (img, items, d): su fuerza, o None
        si la esta atacando otro jugador (y no es nuestra pareja). `atras` es lo
        que se hace para cerrar el panel en ese caso."""
        img, items, _ = r
        self._ocupada = self.ocupada_por_otro(img)
        if self._ocupada and not aliado_nuestro:
            # otro jugador (un aliado) ya la esta atacando: no es la nuestra
            (atras or self._atras_rapido)()
            return None
        f = self._busca(items, "fuerza")
        fuerza = None
        for d in items:
            n = numero(d["texto"])
            if n and n >= 1_000_000 and (fuerza is None or n > fuerza):
                fuerza = n
        return fuerza or (1 if f else None)

    # ------------------------------------------------ vista 2D (radar) --
    def _abrir_ballena_2d(self, pos, aliado_nuestro=False):
        """Vista 2D: toca el icono de la ballena mas cercana a `pos` (se vuelve a
        detectar: el zoom o el centro pueden haber cambiado) y comprueba su panel
        «Ballena de éter · Fuerza N». Devuelve la fuerza o None."""
        for intento in range(3):
            cand = self.ballenas_vistas_2d(completo=intento > 0)
            if not cand:
                continue
            c = min(cand, key=lambda v: (v[0] - pos[0]) ** 2 + (v[1] - pos[1]) ** 2)
            if (c[0] - pos[0]) ** 2 + (c[1] - pos[1]) ** 2 > 260 ** 2 and len(cand) > 1:
                continue                                  # ninguna cerca: puede ser de otro jugador
            self.ctrl.tap(self._real2d(c, getattr(self, "_sol2d", None)))   # a pantalla, con el sol de ahora
            time.sleep(1.3)
            r = self._panel_ballena(4, "panel_ballena")
            if r is not None:
                return self._fuerza_del_panel(r, aliado_nuestro, atras=self._atras_juego)
            self._atras_juego()                           # lo tocado no era la ballena
        return None

    def _atacar_ballena_2d(self, ciclo: str, idx: int, pos, intento: int = 0) -> bool:
        """Ataque en la vista 2D: sin salto junto a la ballena (el 2D no acerca la
        camara). Se abre su panel, se espera a la otra cuenta (si hay pareja),
        «Ataque de grupo» y la primera flota en «Elige tu flota»."""
        aliado = self._otro_ya_ataco(ciclo, idx, intento)
        fuerza = self._abrir_ballena_2d(pos, aliado_nuestro=aliado)
        if fuerza is None:
            if getattr(self, "_ocupada", False):
                self.log(f"  La ballena {idx + 1} la está atacando otro jugador: no me meto.")
            else:
                self.log(f"  No veo la ballena {idx + 1} en {pos}.")
            return False
        self.log(f"  Ballena {idx + 1}: fuerza {fuerza:,}.".replace(",", "."))
        clave = f"{ciclo}:{idx}:{intento}"
        self.sync.escribir(listo=clave, listo_t=time.time(), llegada=None)
        otro = {}
        if not self.sola:
            otro = self._esperar_pareja(clave, idx, intento)
            if otro is None:
                return False
            if self.abrir_o_reabrir_2d(pos, ciclo, idx, intento) is None:
                return False
        img, items = self._ocr("menu_ballena", self.ZONA_MENU)
        h, w = img.shape[:2]
        g = self._busca(items, "ataque de grupo", w=w, h=h)
        if not g:
            g = next((d for d in items if ocr.normal(d["texto"]) == "ataque"
                      and d["centro"][0] > w * 0.55), None)
        if not g:
            self.log("  No veo «Ataque de grupo» en el menú de la ballena.")
            self._atras_juego()
            return False
        if not self.sola:              # con pareja, los dos tocan a la vez
            t0 = max(self.sync.leer().get("listo_t", 0), otro.get("listo_t", 0)) + 2.0
            while time.time() < t0 and not self.parado():
                time.sleep(0.05)
        self.ctrl.tap(g["centro"])
        ok = self._dialogo_una_flota("ok")
        if ok:
            self.sync.escribir(enviado=clave, llegada=time.time() + 15)
            self.log("  Ataque lanzado con la primera flota.")
        else:
            self.sync.escribir(llegada=time.time() + 15)
        return ok

    def abrir_o_reabrir_2d(self, pos, ciclo, idx, intento):
        """Con pareja, el panel se cierra mientras se espera: lo abre otra vez."""
        f = self._abrir_ballena_2d(pos, aliado_nuestro=self._otro_ya_ataco(ciclo, idx, intento))
        if f is None:
            self.log("  Otro jugador ha empezado a atacarla: no me meto." if getattr(self, "_ocupada", False)
                     else "  Tras esperar no vuelvo a ver la ballena.")
        return f

    def _esperar_pareja(self, clave, idx, intento):
        """Espera a que la otra cuenta este lista para el mismo ataque. Devuelve
        su estado, o None si no llega, abandona o cambia de ballena."""
        def se_va(d) -> bool:
            if self.lider:
                return False
            return (d.get("fase") != "atacar" or d.get("objetivo") != idx
                    or int(d.get("intento") or 0) != intento)

        otro = self.sync.esperar(lambda d: d.get("listo") == clave or d.get("abandona") == clave
                                 or se_va(d), 300, self.parado)
        if otro is not None and otro.get("abandona") == clave:
            self.log("  La otra cuenta no puede con esta ballena; no ataco solo.")
            return None
        if otro is not None and se_va(otro):
            self.log("  La otra cuenta ha cambiado de ballena; dejo esta.")
            return None
        if otro is None:
            self.log("  La otra cuenta no llega a tiempo; no ataco solo.")
            return None
        return otro

    @staticmethod
    def ocupada_por_otro(img) -> bool:
        """En el panel de la ballena, arriba a la izquierda sale «Flota aliada»
        con cuantas flotas aliadas la estan atacando (y sus nombres). Antes de
        atacar nosotros, cualquier flota ahi es de otro jugador."""
        try:
            items = ocr.leer(img, (0, 0.08, 0.35, 0.32))
        except Exception:                                     # noqa: BLE001
            return False
        h = img.shape[0]
        for d in items:
            if "aliad" in ocr.normal(d["texto"]):
                x, y = d["centro"]
                for e in items:
                    t = e["texto"].strip()
                    if t.isdigit() and 0 < e["centro"][1] - y < h * 0.07 and abs(e["centro"][0] - x) < h * 0.1:
                        return int(t) >= 1
                # sin numero pero con un nombre debajo: tambien hay alguien
                return any(0 < e["centro"][1] - y < h * 0.15 and len(e["texto"].strip()) >= 3
                           and e is not d for e in items)
        return False

    def _otro_ya_ataco(self, ciclo: str, idx: int, intento: int) -> bool:
        """La otra cuenta ya ha lanzado su ataque contra esta ballena en ESTE
        mismo intento: la «Flota aliada» del panel seria la suya. Un envio de
        un intento anterior no vale (podria ser ya otro jugador)."""
        if getattr(self, "sola", False):
            return False                  # sin otra cuenta: toda flota aliada es de otro jugador
        return str(self.sync.del_otro().get("enviado") or "") == f"{ciclo}:{idx}:{intento}"

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

    def saltar_cerca(self, pos, abierta: bool = False, aliado_nuestro: bool = False) -> bool:
        """Salta con la PRIMERA flota a un hueco PEGADO a la ballena, en la vista
        con zoom (con su menu abierto la ballena queda en el centro). Primer
        toque fuera: cierra el menu; segundo en el hueco: «Movimiento en grupo».
        Si cae en otra cosa: «Atrás» a la vista del sistema, reabrir la ballena
        (rapido) y probar el hueco siguiente."""
        for dx, dy in ((0, 0.14), (0, -0.17), (-0.14, 0.05), (0.14, 0.05), (0, 0.24)):
            if self.parado():
                return False
            if not abierta and self.abrir_ballena(pos, desde_zoom=True,
                                                  aliado_nuestro=aliado_nuestro) is None:
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

    def atacar_ballena(self, ciclo: str, idx: int, pos, intento: int = 0) -> bool:
        """(Sola: esta cuenta sin esperar a ninguna otra.)
        Las dos cuentas saltan con su PRIMERA flota al
        lado de la ballena y despues la atacan a la vez con «Ataque de grupo»
        eligiendo esa misma flota. intento es el reintento de esta ballena
        (va en la sincronizacion para que la otra cuenta lo repita)."""
        if getattr(self, "vista", "2d") == "2d":
            return self._atacar_ballena_2d(ciclo, idx, pos, intento)
        aliado = self._otro_ya_ataco(ciclo, idx, intento)
        fuerza = self.abrir_ballena(pos, aliado_nuestro=aliado)
        if fuerza is None:
            if getattr(self, "_ocupada", False):
                self.log(f"  La ballena {idx + 1} la está atacando otro jugador: no me meto.")
            else:
                self.log(f"  No veo la ballena {idx + 1} en {pos}.")
            return False
        self.log(f"  Ballena {idx + 1}: fuerza {fuerza:,}.".replace(",", "."))
        if not self.saltar_cerca(pos, abierta=True, aliado_nuestro=aliado):  # ya esta abierta
            self.log("  No he podido saltar al lado; ataco desde donde estoy.")
        clave = f"{ciclo}:{idx}:{intento}"
        self.sync.escribir(listo=clave, listo_t=time.time(), llegada=None)

        def se_va(d) -> bool:
            """Solo la cuenta que APOYA mira el archivo del que invoca: si
            este deja esta ballena (fase, objetivo o reintento), no esperar
            mas. El que invoca no lo usa: el archivo del que apoya no dice
            en que ballena esta (su «ciclo» viejo no vale para comparar)."""
            if self.lider:
                return False
            return (d.get("fase") != "atacar" or d.get("objetivo") != idx
                    or int(d.get("intento") or 0) != intento)

        if self.sola:
            otro = {}                  # sola: no se espera el «listo» de nadie
        else:
            otro = self.sync.esperar(lambda d: d.get("listo") == clave or d.get("abandona") == clave
                                     or se_va(d), 300, self.parado)
            if otro is not None and otro.get("abandona") == clave:
                self.log("  La otra cuenta no puede con esta ballena; no ataco solo.")
                return False
            if otro is not None and se_va(otro):
                self.log("  La otra cuenta ha cambiado de ballena; dejo esta.")
                return False
            if otro is None:
                self.log("  La otra cuenta no llega a tiempo; no ataco solo.")
                return False
        if self.abrir_ballena(pos, desde_zoom=True,
                              aliado_nuestro=self._otro_ya_ataco(ciclo, idx, intento)) is None:
            if getattr(self, "_ocupada", False):
                self.log("  Otro jugador ha empezado a atacarla: no me meto.")
                return False
            self.mi_sistema()
            vivas = self.ver_ballenas()
            if vivas:
                pos = min(vivas, key=lambda v: (v[0] - pos[0]) ** 2 + (v[1] - pos[1]) ** 2)
            if self.abrir_ballena(pos) is None:
                self.log("  Otro jugador la está atacando: no me meto." if getattr(self, "_ocupada", False)
                         else "  Tras el salto no vuelvo a ver la ballena.")
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
        if not self.sola:              # con pareja, los dos tocan a la vez
            t0 = max(self.sync.leer().get("listo_t", 0), otro.get("listo_t", 0)) + 2.0
            while time.time() < t0 and not self.parado():
                time.sleep(0.05)
        self.ctrl.tap(g["centro"])
        ok = self._dialogo_una_flota("ok")
        if ok:                   # solo si ha salido de verdad (lo mira la otra cuenta)
            self.sync.escribir(enviado=clave, llegada=time.time() + 15)
            self.log("  Ataque lanzado con la primera flota.")
        else:
            self.sync.escribir(llegada=time.time() + 15)
        return ok

    def esperar_muerte(self, pos, maximo=480) -> bool:
        """Espera a que no quede rojo (ni circulo ni triangulo "!") donde
        estaba la ballena, dos veces seguidas. En 2D: que su icono ya no este."""
        time.sleep(20)
        if getattr(self, "vista", "2d") == "2d":
            return self._esperar_muerte_2d(pos, maximo)
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

    def _esperar_muerte_2d(self, pos, maximo=480) -> bool:
        """En 2D la ballena esta muerta cuando su icono ya no sale en la vista del
        sistema, dos comprobaciones seguidas. Solo cuenta si de verdad se ve la
        vista del sistema (con «Mi estación»), no un menu, una carga o la galaxia."""
        ausentes, fin = 0, time.time() + maximo
        while time.time() < fin and not self.parado():
            self._quitar_salir()
            img, items = self._ocr("muerte_2d")
            h, w = img.shape[:2]
            en_sistema = bool(self._busca(items, "mi estacion", zona=(0.1, 0.85, 0.35, 1), w=w, h=h)
                              and not self._busca(items, "atras", zona=(0, 0, 0.2, 0.15), w=w, h=h))
            if not en_sistema:
                self.mi_sistema()
                time.sleep(2)
                continue
            vistas = self.ballenas_vistas_2d(completo=True)     # la misma vista que al detectarla
            cerca_ = [v for v in vistas if (v[0] - pos[0]) ** 2 + (v[1] - pos[1]) ** 2 < 160 ** 2]
            ausentes = 0 if cerca_ else ausentes + 1
            if ausentes >= 2:
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
            # el juego acerca la camara a ese punto. No se toca el centro para
            # cerrar el menu: ahi suele haber una estacion y abre la suya (lo
            # cierra el propio cambio a 2D)
            self.ctrl.tap(c0)
            time.sleep(1.5)
        self._modo("2d")
        time.sleep(2.5)                          # que termine de pasar a 2D
