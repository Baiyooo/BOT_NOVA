"""Recoger las gemas que sueltan las ballenas."""
from __future__ import annotations

import time

from nucleo.cerrojo import Cerrojo
from vision import ocr
from vision import conocimiento_vista
from tareas import descartes
from tareas.ballenas.deteccion import BOTON_LADO, centro_sol_2d, gemas_2d, lilas_primero


class _Recoger:
    """Recoger las gemas que sueltan las ballenas."""

    # ------------------------------------------------------- 4) gemas --
    def abrir_recursos(self) -> bool:
        """Abre «Filtro de recursos» con el icono «Recursos» del panel lateral
        (2D / Ayuda / Recursos). El lector junta los rotulos ("Ayuda .Recursos"),
        asi que se toca el icono en su sitio fijo (1600x900: (1538, 622))."""
        img, items = self._ocr("recursos?")
        h, w = img.shape[:2]
        if self._busca(items, "filtro de recursos"):
            return True
        abierto = any("recursos" in ocr.normal(d["texto"]) for d in items
                      if d["centro"][0] > w * 0.75 and h * 0.5 < d["centro"][1] < h * 0.75)
        if not abierto:
            self.ctrl.tap(BOTON_LADO)
            time.sleep(1.5)
        self.ctrl.tap((int(w * 1538 / 1600), int(h * 622 / 900)))
        return self._espera_texto(("filtro de recursos",), 4, "filtro") is not None

    def _cerrar_menu_mapa(self):
        """Cierra el menu de un objeto del mapa sin salir del zoom: un toque en
        una zona vacia de abajo a la izquierda del centro."""
        img = self.ctrl.capture()
        h, w = img.shape[:2]
        self.ctrl.tap((int(w * 0.30), int(h * 0.72)))
        time.sleep(0.8)

    @staticmethod
    def _es_gema(texto) -> bool:
        """Etiqueta de una gema en la vista con zoom: «Gema orgánica», «Gema
        sagrada»... (el lector se come a veces la G: «ema orgánica»)."""
        import re
        t = ocr.normal(texto)
        return bool(re.search(r"(^|\s)g?ema(\s|$)", t)) or "organic" in t or "sagrad" in t

    @staticmethod
    def _con_barra(img, d) -> bool:
        """Debajo de la etiqueta de una gema que ya se esta recogiendo sale una
        barra de progreso clara."""
        import cv2
        h = img.shape[0]
        x0, y0, bw, bh = d["caja"]
        g = cv2.cvtColor(img[y0 + bh + 2:y0 + bh + int(h * 0.03), max(0, x0):x0 + bw], cv2.COLOR_BGR2GRAY)
        return g.size > 0 and float((g > 170).mean()) > 0.05

    def recoger_por_etiquetas(self, cupo: int) -> int:
        with self._turno_drones():
            return self._por_etiquetas(self._cupo_libre(cupo))

    def _cupo_libre(self, cupo: int) -> int:
        """Los drones son los mismos para gemas y escombros: no mandar mas de
        los que estan en casa segun el contador comun (tareas/restos.py)."""
        from tareas.restos import drones_libres
        libres = drones_libres(self._cuenta_drones(), self.robots)
        if libres < cupo:
            self.log(f"  Solo hay {libres} dron(es) libre(s) (los demás están fuera).")
        return min(cupo, libres)

    def _dron_mandado(self):
        """Apunta el dron en el contador comun, igual que los escombros."""
        from tareas.restos import VIAJE_POR_DEFECTO, apuntar_dron, tiempo_viaje
        try:
            viaje = tiempo_viaje(ocr.leer(self.ctrl.capture())) or VIAJE_POR_DEFECTO
        except Exception:                                     # noqa: BLE001
            viaje = VIAJE_POR_DEFECTO
        apuntar_dron(self._cuenta_drones(), viaje)

    def _por_etiquetas(self, cupo: int) -> int:
        """En la vista 3D con zoom cada gema lleva su etiqueta escrita. Se
        busca la etiqueta, se toca la gema (arriba a la izquierda de su
        etiqueta, donde empieza la linea naranja) y se pulsa «Recoger»: cada
        «Recoger» manda un robot. Se sigue hasta mandar todos los robots de
        la cuenta o quedarse sin gemas libres. Las que ya se estan
        recogiendo (con barra) se dejan."""
        hechas, malas, fallos = 0, [], 0
        lista = descartes.de_cuenta(self._cuenta_drones())
        while hechas < cupo and fallos < cupo + 4 and not self.parado():
            img, items = self._ocr("gemas_3d")
            h, w = img.shape[:2]
            libres = [d for d in items if self._es_gema(d["texto"])
                      and d["centro"][0] < w * 0.62 and h * 0.12 < d["centro"][1] < h * 0.95
                      and not self._con_barra(img, d)
                      and not any(abs(d["centro"][0] - a) < 50 and abs(d["centro"][1] - b) < 50
                                  for a, b in malas)
                      and not lista.bloqueado(d["centro"], img)]
            if not libres:
                break
            libres.sort(key=lambda d: (d["centro"][0] - w / 2) ** 2 + (d["centro"][1] - h / 2) ** 2)
            e = libres[0]
            x0, y0, bw, bh = e["caja"]
            # la gema (la bola) queda arriba a la izquierda del principio de la etiqueta
            hecho = False
            for dx, dy in ((-0.032, -0.07), (-0.045, -0.06), (-0.02, -0.082)):
                toque = (int(x0 + w * dx), int(y0 + bh / 2 + h * dy))
                self.ctrl.tap(toque)
                time.sleep(1.3)
                img2, items2 = self._ocr("gema")
                if self._busca(items2, "recogiendo", w=w, h=h):
                    self._cerrar_menu_mapa()
                    lista.anotar(e["centro"], img, "mando")
                    malas.append(e["centro"])              # no repetir en esta pasada
                    hecho = True                           # ya va alguien: no es un fallo
                    break
                menu = [d for d in items2 if d["centro"][0] > w * 0.6 and h * 0.1 < d["centro"][1] < h * 0.6]
                b = next((d for d in menu if "recoger" in ocr.normal(d["texto"])), None)
                titulo = any(self._es_gema(d["texto"]) and w * 0.22 < d["centro"][0] < w * 0.47
                             and h * 0.43 < d["centro"][1] < h * 0.495 for d in items2)
                if b is not None and titulo:
                    if descartes.hay_movimiento(self.ctrl, img2, toque):
                        self.log("  Movimiento sobre la gema: alguien ya va, la dejo.")
                        self._cerrar_menu_mapa()
                        lista.anotar(e["centro"], img, "mando")
                        malas.append(e["centro"])
                        hecho = True                       # no es un fallo, solo se deja un rato
                        break
                    self.ctrl.tap(b["centro"])
                    time.sleep(1.5)
                    hechas += 1
                    self._dron_mandado()
                    self.log(f"  Robot a por una gema ({hechas}/{cupo}).")
                    lista.anotar(e["centro"], img, "mando")
                    hecho = True
                    break
                self._zoom_3d()                            # volver a dejar la camara igual
            if not hecho:
                malas.append(e["centro"])
                lista.anotar(e["centro"], img, "malo")
                fallos += 1
            # tras «Recoger» el juego vuelve a la vista del sistema: acercar otra vez
            if hechas < cupo:
                self._zoom_3d()
        return hechas

    def recoger_gemas(self, cupo: int, radio: bool = False, limite_s: float | None = None) -> int:
        """En la vista del sistema en 2D: toca la gema, comprueba «Gema …» y
        pulsa «Recoger»; vuelve con «Atrás» y sigue con la siguiente. limite_s: tiempo
        maximo del lote (se deja de mandar al pasarse; el resto va en el siguiente ciclo)."""
        hechas, probadas, lanzadas = 0, [], []
        tope = time.time() + limite_s if limite_s else None
        lista = descartes.de_cuenta(self._cuenta_drones())
        with self._turno_drones() as cj:
            cupo = self._cupo_libre(cupo)
            for _ in range(cupo * 3 + 3):
                if hechas >= cupo or self.parado() or (tope and time.time() > tope):
                    break
                cj.renovar()
                img = self.ctrl.capture()
                cand = [c for c in lista.filtrar(self._gemas_cerca2d(img, radio), img)
                        if not any(abs(c[0] - a) < 30 and abs(c[1] - b) < 30 for a, b in probadas)]
                if lanzadas:
                    # los robots que mande antes van por la linea del sol (la estacion) a su
                    # gema: no se confunden con gemas (y se evita tocarlos y leer su menu)
                    sol = centro_sol_2d(img)
                    if sol is not None:
                        cand = [c for c in cand if not self._en_ruta_de_robot(c, sol, lanzadas, img)]
                if not cand:
                    break
                c = cand[0]
                probadas.append(c)
                self.ctrl.tap(c)
                time.sleep(1.3)
                # el menu de la gema (Recoger / Ver / Marcador) empieza hacia el 25 % de la altura
                img2, items = self._ocr("gema", (0.1, 0.12, 0.98, 0.7))
                h, w = img2.shape[:2]
                es_gema = any("gema" in ocr.normal(d["texto"]) for d in items)
                if not es_gema and any("recoger" in ocr.normal(d["texto"]) for d in items):
                    # el lector a veces estropea el titulo («Gema gamma» -> «ewweb»):
                    # se vuelve a leer solo esa zona con sus nombres posibles
                    _, tit = self._ocr("gema_titulo", (0.2, 0.42, 0.52, 0.5))
                    es_gema = any(any(k in ocr.normal(d["texto"]) for k in
                                      ("gema", "gamma", "organic", "sagrad"))
                                  for d in tit)
                if not es_gema:
                    self.log("  Ahí no hay una gema (" + ", ".join(d["texto"] for d in items[:5]) + ").")
                    lista.anotar(c, img, "malo")
                    self._cerrar_menu_mapa()
                    continue
                if self._busca(items, "recogiendo", w=w, h=h):
                    self.log("  Esa gema ya la está recogiendo alguien.")
                    lista.anotar(c, img, "mando")
                    self._cerrar_menu_mapa()
                    continue
                d = self._busca(items, "recoger", zona=self.ZONA_MENU, w=w, h=h)
                if d is None:
                    self.log("  La gema no tiene «Recoger» (" + ", ".join(x["texto"] for x in items[:6]) + ").")
                    lista.anotar(c, img, "malo")
                    self._cerrar_menu_mapa()
                    continue
                if descartes.hay_movimiento(self.ctrl, img2, c):
                    self.log("  Movimiento sobre la gema: alguien ya va, la dejo.")
                    lista.anotar(c, img, "mando")
                    self._cerrar_menu_mapa()
                    continue
                self.ctrl.tap(d["centro"])
                time.sleep(1.2)
                lista.anotar(c, img, "mando")
                lanzadas.append(c)
                hechas += 1
                self._dron_mandado()
                self.log(f"  Drones a por una gema ({hechas}/{cupo}).")
        return hechas

    @staticmethod
    def _en_ruta_de_robot(c, sol, lanzadas, img, margen: float = 16.0) -> bool:
        """¿El punto c esta sobre la linea sol -> gema de algun robot ya enviado (sin
        ser la propia gema)? Escala 1600x900."""
        k = img.shape[1] / 1600.0
        for t in lanzadas:
            sx, sy = sol[0], sol[1]
            vx, vy = t[0] - sx, t[1] - sy
            largo2 = vx * vx + vy * vy
            if largo2 < 1:
                continue
            u = ((c[0] - sx) * vx + (c[1] - sy) * vy) / largo2     # posicion a lo largo de la ruta
            if not 0.02 <= u <= 1.0:
                continue
            px, py = sx + u * vx, sy + u * vy
            if (c[0] - px) ** 2 + (c[1] - py) ** 2 > (margen * k) ** 2:
                continue
            if (c[0] - t[0]) ** 2 + (c[1] - t[1]) ** 2 < (30 * k) ** 2:
                continue                                           # es la propia gema
            return True
        return False

    def _cuenta_drones(self) -> str:
        return str(getattr(self.ctrl, "name", "inst"))

    def _turno_drones(self) -> Cerrojo:
        """Turno compartido entre cuentas (mismo cerrojo que los escombros)."""
        return Cerrojo("drones", self._cuenta_drones(), parado=self.parado, log=self.log)

    #  las gemas aparecen de forma aleatoria por TODO el mapa (no junto a la
    #  ballena): se buscan en toda la vista del sistema en 2D. El radio solo
    #  se usa si alguien pide radio=True.
    RADIO_GEMAS = 0.30

    def _gemas_ciclo(self, lider: bool, muertas: int | None = None) -> int:
        """Las gemas se ven mejor en el modo 2D. En la vista general del
        sistema en 2D (alejando el zoom o recorriendola por zonas si hace falta)
        se buscan sus iconos por TODO el mapa, se toca cada uno y «Recoger»
        (salen los drones). Cualquier gema vale (nunca Nucleos).
        Sola (self.sola): sin sync y con TODOS los drones (no la mitad)."""
        sola = getattr(self, "sola", False)
        self.status["estado"] = "recogiendo gemas"
        # sin drones libres no hay nada que mandar: ni zoom ni esperas (con pareja, el
        # que invoca sigue contando las gemas porque la otra cuenta reparte con ese dato)
        from tareas.restos import drones_libres
        if drones_libres(self._cuenta_drones(), self.robots) <= 0 and (sola or not lider):
            self.log("  No queda ningún dron libre: dejo las gemas para luego.")
            return 0
        if not lider and not sola:
            d = self.sync.esperar(lambda d: d.get("fase") in ("gemas", "hecho"), 600, self.parado)
            if not (d or {}).get("muertas"):
                self.log("  No ha muerto nuestra ballena: no recojo gemas.")
                return 0
            if not (d or {}).get("n_gemas"):
                self.log("  La otra cuenta no ha visto gemas de nuestra ballena.")
                return 0
        time.sleep(2.0)                          # que aparezcan
        n = hechas = 0
        try:
            # la vista elegida (Ajustes > Vista de ballenas y gemas) primero y la
            # otra de respaldo: en 2D por sus iconos (con el zoom que haga falta;
            # tras cada zoom se vuelve a capturar y detectar), en 3D por las
            # etiquetas de cada gema junto a donde murio la ballena
            orden = ("3d", "2d") if self.vista == "3d" else ("2d", "3d")
            for modo in orden:
                if modo == "2d":
                    n, hechas = self._gemas_en_2d(lider, sola)
                else:
                    n, hechas = self._gemas_en_3d(lider, sola)
                if n:
                    break
            if not n and lider and not sola:
                self.sync.escribir(fase="gemas", n_gemas=0)
        finally:
            # pase lo que pase: vista normal del sistema (recentrando con mi_sistema, no
            # fiandose de que acercar deshaga exactamente alejar) y en la vista de matar
            self.status["gemas"] += hechas
            self.status["recogidas"] += hechas
            self._restaurar_vista()
            self._ir_al_sistema()
            self._modo(self.vista)
        return n

    BUSCAR_FUERA = True            # si quedan drones, barrer todo el mapa (ver _barrido_2d)

    def _barrido_2d(self, libres: int) -> int:
        """Quedan drones libres: se mira todo el mapa en dos vistas. 1) zoom medio
        con el sol en el centro (iconos legibles, todo el anillo del sistema);
        2) el sistema entero, para las gemas sueltas FUERA del anillo (manchas
        blancas aisladas). Devuelve cuantas se han mandado."""
        if not self.BUSCAR_FUERA or libres <= 0 or self.parado():
            return 0
        hechas = 0
        self._pequenas = False
        self._asegurar_2d()
        if self._contar_gemas():
            hechas += self.recoger_gemas(libres - hechas, radio=False)
        if hechas < libres and not self.parado() and self._zoom_mapa(False):
            self._zoom_mapa(False)
            self._pequenas = True
            if self._contar_gemas():
                hechas += self.recoger_gemas(libres - hechas, radio=False)
        return hechas

    def _gemas_en_2d(self, lider: bool, sola: bool) -> tuple[int, int]:
        """Vista 2D del sistema: cuenta los iconos y manda drones a las gemas.
        Devuelve (vistas, recogidas)."""
        n = self._ver_gemas_2d()
        self.log(f"  Veo {n} gema(s) en 2D.")
        if not n:
            extra = self._barrido_2d(self.robots)
            return extra, extra
        # Se quieren recoger TODAS las gemas (sin prioridad): cada cuenta manda
        # hasta todos sus drones libres. Con pareja no se parte el numero por la
        # mitad: las gemas que ya recoge la otra cuenta se ven (barra,
        # «Recogiendo» o movimiento) y se dejan, y el turno de drones compartido
        # evita que las dos toquen la misma a la vez.
        if lider and not sola:
            self.sync.escribir(fase="gemas", n_gemas=n)
        elif not lider and not sola:
            d = self.sync.esperar(lambda d: d.get("fase") in ("gemas", "hecho"), 600, self.parado)
            n = max(n, (d or {}).get("n_gemas", n))
        cupo = min(self.robots, n)
        hechas = self.recoger_gemas(cupo, radio=False) if cupo else 0
        if cupo and hechas >= cupo and hechas < n:
            self.log(f"  Quedan {n - hechas} gema(s) sin drones libres: "
                     "se recogerán cuando vuelvan los drones.")
        if hechas < self.robots:                        # quedan drones: gemas fuera de esta vista
            extra = self._barrido_2d(self.robots - hechas)
            hechas += extra
            n = max(n, hechas)
        return n, hechas

    def _gemas_en_3d(self, lider: bool, sola: bool) -> tuple[int, int]:
        """Vista 3D con zoom donde murio la ballena: cada gema lleva su etiqueta.
        Devuelve (vistas, recogidas)."""
        self._restaurar_vista()
        n = hechas = 0
        if self._zoom_3d():
            img, items = self._ocr("gemas_3d")
            n = sum(1 for d in items if self._es_gema(d["texto"]))
            self.log(f"  Veo {n} gema(s) con su etiqueta (3D).")
            if lider and not sola:
                self.sync.escribir(fase="gemas", n_gemas=n)
            hechas = self.recoger_por_etiquetas(self.robots) if n else 0
        return n, hechas

    # ---- vista de recogida: 2D y zoom del mapa (ctrl.zoom, pellizco por sendevent)
    ZOOM_FUERA = conocimiento_vista.PELLIZCO_SUAVE    # fuerza del pellizco al alejar (suave)
    _zoom_neto = 0                                # pellizcos de alejar sin deshacer
    _pequenas = False                             # mapa alejado del todo: iconos de ~10 px

    def _zoom_mapa(self, acercar: bool) -> bool:
        """Acerca o aleja el mapa con el zoom del control. False si esta
        instancia no lo permite. Hay que volver a capturar y detectar despues:
        las coordenadas de antes ya no valen."""
        zoom = getattr(self.ctrl, "zoom", None)
        if not callable(zoom) or not zoom(acercar, fuerza=self.ZOOM_FUERA, pasos=12):
            return False
        self._zoom_neto += 1 if acercar else -1
        time.sleep(1.5)
        return True

    def _zoom_normal(self):
        """Deshace el zoom aplicado para la recogida (vista normal del sistema)."""
        while self._zoom_neto < 0 and not self.parado():
            if not self._zoom_mapa(True):
                break
        self._zoom_neto = 0

    #  arrastres para recorrer el mapa por zonas (1600x900): (de, a); se deshacen al acabar
    ZONAS_MAPA = (((1100, 450), (500, 450)), ((500, 450), (1100, 450)),
                  ((800, 650), (800, 250)), ((800, 250), (800, 650)))
    _arrastre = False

    def _contar_gemas(self) -> int:
        n = 0
        for _ in range(3):                       # el 2D tarda en dibujar las gemas
            n = max(n, len(self._gemas_cerca2d(self.ctrl.capture(), radio=False)))
            if n:
                break
            time.sleep(1.0)
        return n

    def _ver_gemas_2d(self) -> int:
        """Pasa a la vista general del sistema en 2D (sin centrar en ningun
        punto: las gemas salen por todo el mapa) y cuenta los iconos de gema
        (gemas_2d). Si no sale ninguno, aleja el mapa un paso (se ve mas) y, si
        sigue sin salir, recorre el mapa por zonas con arrastres (en la primera
        que haya gemas se queda; _restaurar_vista lo deshace). Tras cada zoom o
        arrastre se vuelve a capturar y detectar."""
        # ya en el 2D del sistema (se ve el sol): sin mi_sistema() ni cambio de modo
        from tareas.ballenas.deteccion import centro_sol_2d
        if centro_sol_2d(self.ctrl.capture()) is None:
            self.mi_sistema()
            self._modo("2d")
        self._pequenas = False
        n = self._contar_gemas()
        if not n and self._zoom_mapa(False):             # zoom medio: iconos legibles
            n = self._contar_gemas()
        if not n and self._zoom_neto < 0 and self._zoom_mapa(False):
            self._pequenas = True            # sistema entero: tambien las gemas sueltas fuera del anillo
            n = self._contar_gemas()
        if not n and getattr(self.ctrl, "style", "drag") != "click":   # «click»: sin arrastre
            for de, a in self.ZONAS_MAPA:
                if self.parado():
                    break
                self.ctrl.drag(de, a)
                time.sleep(1.5)
                n = self._contar_gemas()
                if n:
                    self._arrastre = True        # nos quedamos aqui: se recentra al acabar
                    break
                self.mi_sistema(forzar=True)     # nada: recentrar (no deshacer el arrastre a ciegas)
        return n

    def _restaurar_vista(self):
        """Deja la vista normal del sistema tras la recogida: intenta deshacer el
        zoom, pero como acercar no deshace exactamente alejar (ni un arrastre se
        deshace a ciegas), recentra siempre con mi_sistema(forzar=True)."""
        movida = self._arrastre or self._zoom_neto != 0
        self._arrastre = False
        self._pequenas = False
        self._zoom_normal()
        if movida:
            # en 2D basta centrar el mapa en el sol (rapido); mi_sistema tarda ~30 s
            if not (self.vista == "2d" and self._centrar_sol_2d()):
                self.mi_sistema(forzar=True)

    def _zoom_3d(self) -> bool:
        """Vista con zoom (3D) donde murio la ballena: desde la vista del
        sistema se toca ese punto y el juego acerca la camara."""
        c0 = getattr(self, "_muerte", None)
        if c0 is None:
            return False
        self.mi_sistema()
        self._modo("3d")
        self.ctrl.tap(tuple(c0))
        time.sleep(2.0)
        return True

    def recoger_sueltas(self, lote: int | None = None, limite_s: float | None = None) -> int:
        """Gemas que han quedado en el sistema (de ballenas anteriores, o de
        cualquier ballena: salen por todo el mapa): en la vista general del
        sistema en 2D (con zoom y zonas si hace falta) se mandan los drones a
        las que haya, hasta los robots libres de la cuenta. Las que ya esta
        recogiendo alguien se dejan. Respaldo: etiquetas 3D junto a donde murio
        la ultima ballena (si se sabe). lote: como mucho esas gemas por ciclo (Recoleccion
        manda 6 seguidas en ~30 s y vuelve a empezar cuando regresan los drones)."""
        self.status["estado"] = "recogiendo gemas del sistema"
        hechas = 0
        robots = min(self.robots, lote) if lote else self.robots
        try:
            if self.vista == "3d":                      # la vista elegida primero; si no sale nada, 2D
                hechas = self._sueltas_en_3d(robots)
                if hechas:
                    self.log(f"Gemas del sistema (3D): mando drones a {hechas}.")
                    return hechas
            n = self._ver_gemas_2d()
            if n:
                hechas = self.recoger_gemas(min(robots, n), radio=False, limite_s=limite_s)
                if hechas < robots and not (limite_s and hechas):   # quedan drones: gemas fuera de esta vista
                    hechas += self._barrido_2d(robots - hechas)
                self.log(f"Gemas del sistema: veo {n}, mando drones a {hechas}.")
            else:
                self._restaurar_vista()
                sd = self.sync.leer()
                punto = sd.get("mi_ballena") or (self.sync.del_otro() or {}).get("mi_ballena")
                if punto:
                    self._muerte = tuple(punto)
                    if self._zoom_3d():
                        hechas = self.recoger_por_etiquetas(robots)
                self.log(f"Gemas del sistema: no veo ninguna en 2D; por etiquetas 3D, {hechas}.")
        finally:
            self.status["recogidas"] += hechas
            self._restaurar_vista()
            self._ir_al_sistema()
            self._modo(self.vista)
        return hechas

    def _sueltas_en_3d(self, robots: int | None = None) -> int:
        """Vista 3D: las etiquetas de las gemas solo se leen con zoom junto a un punto, asi que
        se va al de la ultima ballena muerta (si se sabe). Devuelve las mandadas."""
        sd = self.sync.leer()
        punto = sd.get("mi_ballena") or (self.sync.del_otro() or {}).get("mi_ballena")
        if not punto:
            return 0
        self._muerte = tuple(punto)
        return self.recoger_por_etiquetas(robots or self.robots) if self._zoom_3d() else 0

    def _gemas_cerca2d(self, img, radio: bool = False):
        """Gemas en 2D, de la mas cercana al centro de la pantalla. Por defecto
        todas las de la vista (aparecen por todo el mapa); radio=True limita a
        RADIO_GEMAS alrededor del centro."""
        h, w = img.shape[:2]
        cand = gemas_2d(img, pequenas=self._pequenas)
        try:
            from vision import percepcion
            esc = percepcion.ver(img)
            if esc.fuente == "modelo":
                for o in esc.de("gema", 0.45):
                    c = o["centro"]
                    if all(abs(c[0] - v[0]) > 25 or abs(c[1] - v[1]) > 25 for v in cand):
                        cand.append(c)
        except Exception:                                     # noqa: BLE001
            pass
        if radio:
            r2 = (self.RADIO_GEMAS * w) ** 2
            cand = [c for c in cand if (c[0] - w / 2) ** 2 + (c[1] - h / 2) ** 2 <= r2]
        cand.sort(key=lambda c: (c[0] - w / 2) ** 2 + (c[1] - h / 2) ** 2)
        return lilas_primero(img, cand)           # estable: lila antes que blanco, y por cercania
