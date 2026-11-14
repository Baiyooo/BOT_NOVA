"""Recoger las gemas que sueltan las ballenas."""
from __future__ import annotations

import time

from vision import ocr
from tareas.ballenas.deteccion import BOTON_LADO, gemas_2d


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

    def recoger_gemas(self, cupo: int) -> int:
        """En la vista del sistema en 2D: toca la gema, comprueba «Gema …» y
        pulsa «Recoger»; vuelve con «Atrás» y sigue con la siguiente."""
        hechas, probadas = 0, []
        for _ in range(cupo * 3 + 3):
            if hechas >= cupo or self.parado():
                break
            img = self.ctrl.capture()
            cand = [c for c in self._gemas_cerca2d(img)
                    if not any(abs(c[0] - a) < 30 and abs(c[1] - b) < 30 for a, b in probadas)]
            if not cand:
                break
            c = cand[0]
            probadas.append(c)
            self.ctrl.tap(c)
            time.sleep(1.3)
            img, items = self._ocr("gema", (0.1, 0.25, 0.98, 0.7))
            h, w = img.shape[:2]
            if not any("gema" in ocr.normal(d["texto"]) for d in items):
                self._cerrar_menu_mapa()
                continue
            if self._busca(items, "recogiendo", w=w, h=h):
                self.log("  Esa gema ya la está recogiendo alguien.")
                self._cerrar_menu_mapa()
                continue
            d = self._busca(items, "recoger", zona=self.ZONA_MENU, w=w, h=h)
            if d is None:
                self._cerrar_menu_mapa()
                continue
            self.ctrl.tap(d["centro"])
            time.sleep(1.2)
            hechas += 1
            self.log(f"  Drones a por una gema ({hechas}/{cupo}).")
        return hechas

    def _gemas_ciclo(self, lider: bool) -> int:
        """Las gemas se ven mejor en el modo 2D. En la vista
        del sistema en 2D se buscan sus iconos (cerca de donde murio la
        ballena), se toca cada uno y «Recoger» (salen los drones)."""
        self.status["estado"] = "recogiendo gemas"
        time.sleep(2.0)                          # que aparezcan
        self._zoom_a_muerte()
        n = len(self._gemas_cerca2d(self.ctrl.capture()))
        self.log(f"  Veo {n} gema(s) en 2D.")
        if lider:
            self.sync.escribir(fase="gemas", n_gemas=n)
            cupo = min(self.robots, (n + 1) // 2)
        else:
            d = self.sync.esperar(lambda d: d.get("fase") in ("gemas", "hecho"), 600, self.parado)
            n = max(n, (d or {}).get("n_gemas", n))
            cupo = min(self.robots, max(1, n // 2)) if n else 0
        hechas = self.recoger_gemas(cupo) if cupo else 0
        self.status["gemas"] += hechas
        self.status["recogidas"] += hechas
        self.mi_sistema()
        self._modo("3d")                          # la ballena se busca en 3D
        return n

    def recoger_sueltas(self) -> int:
        """Gemas que han quedado en el sistema (de ballenas anteriores): en 2D,
        se mandan los drones a las que haya, hasta los robots de la cuenta."""
        self.status["estado"] = "recogiendo gemas sueltas"
        self.mi_sistema()
        self._modo("2d")
        time.sleep(1.0)
        n = len(gemas_2d(self.ctrl.capture()))
        hechas = self.recoger_gemas(min(self.robots, n)) if n else 0
        if n:
            self.log(f"Gemas sueltas: veo {n}, mando drones a {hechas}.")
        self.status["recogidas"] += hechas
        self.mi_sistema()
        self._modo("3d")
        return hechas

    def _gemas_cerca2d(self, img):
        """Gemas en 2D, de la mas cercana al centro (donde murio la ballena)."""
        h, w = img.shape[:2]
        cand = gemas_2d(img)
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
        cand.sort(key=lambda c: (c[0] - w / 2) ** 2 + (c[1] - h / 2) ** 2)
        return cand
