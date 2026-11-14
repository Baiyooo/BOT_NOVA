"""Invocar ballenas con los Senuelos de eter y localizarlas en el sistema."""
from __future__ import annotations

import time

from cerebro.memoria_eventos import sin_acentos
from vision import ocr
from tareas.ballenas.deteccion import SLOT2, anillos_rojos, ballenas_por_forma


class _Invocar:
    """Invocar ballenas con los Senuelos de eter y localizarlas en el sistema."""

    def _almacen_por_vecinos(self) -> bool:
        """Toca el ICONO de Almacén de la barra de arriba (tocar el rotulo no
        abre nada); la barra es la misma en la vista del sistema y en la base.
        El lector lo lee mal ("len", o junto a otros rotulos), asi que se usa
        su sitio fijo en la barra (1600x900: icono en (750, 44)) como respaldo,
        comprobando que la barra esta ahi (se ven «Alianza», «Base» o «Almacén»);
        si «Almacén» se lee en otro sitio de la barra, se toca su icono (encima
        del rotulo) en vez de la posicion fija."""
        img, items = self._ocr("almacen")
        h, w = img.shape[:2]
        z = (0.25, 0, 0.8, 0.16)
        if not (self._busca(items, "alianza", zona=z, w=w, h=h) or
                self._busca(items, "base", zona=z, w=w, h=h) or
                self._busca(items, "almacen", zona=z, w=w, h=h)):
            self.log("  No veo la barra de arriba (lee: " +
                     ", ".join(d["texto"] for d in items if d["centro"][1] < h * 0.16)[:120] + ").")
            time.sleep(1.5)
            return False
        d = self._busca(items, "almacen", zona=z, w=w, h=h)
        if d and abs(d["centro"][0] - w * 750 / 1600) < w * 0.06 and d["centro"][1] > h * 0.05:
            # rotulo bien leido, cerca de su sitio: el icono esta justo encima
            self.ctrl.tap((d["centro"][0], max(int(h * 0.03), d["centro"][1] - int(h * 0.055))))
        else:
            self.ctrl.tap((int(w * 750 / 1600), int(h * 44 / 900)))
        time.sleep(3.0)
        return True

    ZONA_SENUELO = (0.62, 0.3, 1, 0.6)        # el objeto seleccionado en el Almacen

    def _pantalla_tienda(self, items, w, h) -> bool:
        """¿Hay un «Comprar» o el titulo de la Tienda en vez del Almacén?
        («Tienda online» de la barra de arriba no cuenta: esta mas a la derecha.)"""
        from vision import ocr
        if any("comprar" in ocr.normal(d["texto"]) for d in items):
            return True
        return bool(self._busca(items, "tienda", zona=(0, 0, 0.6, 0.2), w=w, h=h))

    def _tocar_usar(self):
        """Toca el boton «Usar» a secas (abajo a la derecha). Nunca «Comprar y
        usar» (gasta GEC). Devuelve el texto tocado o None."""
        for _ in range(2):
            img, items = self._ocr("usar")
            h, w = img.shape[:2]
            d = next((x for x in items if ocr.normal(x["texto"]).strip() == "usar"
                      and x["centro"][0] > w * 0.62 and h * 0.72 < x["centro"][1] < h * 0.95), None)
            if d is not None:
                self.ctrl.tap(d["centro"])
                time.sleep(1.2)
                return d
            time.sleep(1.0)
        return None

    @staticmethod
    def _senuelos_que_hay(items, w, h):
        """La cantidad que se tiene del objeto seleccionado, si se lee
        («Cantidad: 5», «Posees 5»...); None si no se puede leer."""
        import re
        from vision import ocr
        for d in items:
            if d["centro"][0] < w * 0.55 or not h * 0.25 < d["centro"][1] < h * 0.75:
                continue
            m = re.search(r"(?:cantidad|posees|tienes)\D{0,12}(\d+)", ocr.normal(d["texto"]))
            if m and "actual" not in ocr.normal(d["texto"]):
                return int(m.group(1))
        return None

    # ------------------------------------------------------- 1) invocar --
    def invocar(self, n: int) -> int:
        """Usa n Señuelos de eter V. Devuelve cuantas ballenas se han invocado.
        Se hace DESDE LA VISTA DEL SISTEMA (el llamador ya esta ahi): la barra de
        arriba (Alianza / Almacén / Base...) sale tambien alli, asi que no se
        pasa por la base. Al acabar, Atras deja la vista del sistema."""
        self.motivo_invocar = ""          # por que no se ha invocado (lo cuenta el llamador en el log)
        abierto = False
        for intento in range(3):
            if self.parado():
                self.motivo_invocar = "parado por el usuario"
                return 0
            if intento:                       # algo tapa la barra: Atras y otra vez
                self._quitar_salir()
                self._atras_juego()
            if not self._almacen_por_vecinos():
                continue
            # se abre un menu Tienda / Cajas / Descuento / Almacén / Fragmento
            if self._toca(("almacen",), "almacen2", zona=(0.25, 0.5, 0.75, 0.9), espera=2.5,
                          intentos=2):
                abierto = True
                break
        if not abierto:
            self.log("  No se abre el Almacén desde la vista del sistema.")
            self.motivo_invocar = "no se abre el Almacén"
            self._atras_juego(2)              # a la vista del sistema, sin ir a la base
            return 0
        # si en vez del Almacen sale la Tienda (o un «Comprar»), no se toca nada
        img, items = self._ocr("almacen_abierto")
        # el Almacen se reconoce por su pestaña «Objeto común». Su primer objeto
        # (p.ej. «Cambio nombre», 0 en el almacen) trae «Comprar y usar»: eso no
        # es la Tienda; el «Comprar» solo importa con el señuelo seleccionado
        wa, ha = img.shape[1], img.shape[0]
        if (not self._busca(items, "objeto comun", zona=(0, 0.15, 0.2, 0.4), w=wa, h=ha)
                and self._pantalla_tienda(items, wa, ha)):
            self.log("  Ha salido la Tienda en vez del Almacén: no toco nada.")
            self.motivo_invocar = "ha salido la Tienda en vez del Almacén"
            self._atras_juego(2)
            return 0
        if self._toca(("objeto comun",), "objeto_comun", zona=(0, 0.15, 0.2, 0.4), espera=1.5) is None:
            self.log("  No encuentro «Objeto común» en el Almacén; no toco nada.")
            self.motivo_invocar = "no encuentro «Objeto común» en el Almacén"
            self._atras_juego(2)
            return 0
        r = self._espera_texto(("senuelo de eter",), 3, "senuelo", zona=self.ZONA_SENUELO)
        if r is None:
            self.ctrl.tap(SLOT2)                  # suele ser el 2.º objeto; se comprueba despues
            time.sleep(1.5)
            r = self._espera_texto(("senuelo de eter",), 4, "senuelo", zona=self.ZONA_SENUELO)
        if r is None:
            self.log("  No encuentro el Señuelo de éter en Objeto común; no gasto nada.")
            self.motivo_invocar = "no hay Señuelos de éter en Objeto común (¿se han acabado?)"
            self._atras_juego(2)
            return 0
        hechas = 0
        for _ in range(n):
            if self.parado():
                break
            # antes de cada «Usar»: sigue seleccionado el Señuelo de éter (y no hay una tienda)
            img, items = self._ocr("senuelo_sel")
            h, w = img.shape[:2]
            if (not self._busca(items, "senuelo de eter", zona=self.ZONA_SENUELO, w=w, h=h)
                    or self._pantalla_tienda(items, w, h)):
                self.log("  Ya no está seleccionado el Señuelo de éter; paro de invocar.")
                self.motivo_invocar = "ya no está seleccionado el Señuelo de éter"
                break
            quedan = self._senuelos_que_hay(items, w, h)
            if quedan is not None and quedan <= 0:
                self.log("  No quedan Señuelos de éter.")
                self.motivo_invocar = "no quedan Señuelos de éter"
                break
            d = self._tocar_usar()
            if d is None:
                self.log("  No encuentro el botón «Usar» (¿sin Señuelos, o el juego pide otra cosa?).")
                self.motivo_invocar = "no aparece el botón «Usar»"
                break
            r = self._espera_texto(("invocada correctamente", "cantidad actual"), 4, "invocada")
            if r is None:
                self.log("  No sale la confirmación de la invocación; paro de invocar "
                         "(¿ya hay 10/10 ballenas, o el juego no ha dejado usar el señuelo?).")
                self.motivo_invocar = "no sale la confirmación del juego"
                break
            hechas += 1
            self.status["senuelos"] = int(self.status.get("senuelos", 0)) + 1   # gastado
            if quedan is not None and hechas >= quedan:
                self.log("  Era el último Señuelo de éter.")
                break
            txt = sin_acentos(r[2]["texto"])
            self.log(f"  Ballena invocada ({txt[-6:].strip()}).")
            if "10/10" in txt.replace(" ", ""):
                break
            time.sleep(1.5)
        self._atras_juego(2)
        return hechas

    # ---------------------------------------------------- 2) el sistema --
    def mi_sistema(self, forzar: bool = False):
        """Vista general del sistema de MI estacion: Mi estacion y Atras.
        forzar=True: sin el atajo de «ya estoy aqui», para recentrar la camara
        despues de un zoom o un arrastre (toca Mi estación y Atrás)."""
        self._quitar_salir()
        img, items = self._ocr("mapa")
        h, w = img.shape[:2]
        # atajo: ya estoy en la vista general del sistema (sale «Mi estación» y
        # no hay «Atrás» arriba a la izquierda): no hace falta rehacer el camino
        if (not forzar
                and self._busca(items, "mi estacion", zona=(0.1, 0.85, 0.35, 1), w=w, h=h)
                and self._busca(items, "galaxia", zona=(0.75, 0.85, 1, 1), w=w, h=h)
                and not self._busca(items, "atras", zona=(0, 0, 0.2, 0.15), w=w, h=h)):
            return img
        if self.en_base(img):
            d = self._busca(items, "sistema", zona=(0.6, 0.8, 1, 1), w=w, h=h)
            if d:
                self.ctrl.tap((d["centro"][0], d["centro"][1] - int(h * 0.05)))
                time.sleep(4.0)
        # menu abierto o vista acercada: Atras hasta el mapa normal
        for _ in range(3):
            img, items = self._ocr("mapa")
            if self._busca(items, "mi estacion", zona=(0.1, 0.85, 0.35, 1), w=w, h=h):
                break
            if not self._atras_juego():
                break
        if not self._toca(("mi estacion",), "mi_estacion", zona=(0.1, 0.85, 0.35, 1), espera=3.5):
            return self.cap("sistema")
        self._atras_juego()                      # del zoom de la estacion al anillo
        time.sleep(1.0)
        return self.cap("sistema")

    def ver_ballenas(self) -> list[tuple[int, int]]:
        imgs = []
        for _ in range(5):
            imgs.append(self.ctrl.capture())
            time.sleep(0.45)
        vistas = anillos_rojos(imgs)
        # agente de percepcion (detector entrenado), si hay modelo
        try:
            from vision import percepcion
            esc = percepcion.ver(imgs[-1])
            if esc.fuente == "modelo":
                for o in esc.de("ballena", 0.45):
                    c = o["centro"]
                    if all(abs(c[0] - v[0]) > 40 or abs(c[1] - v[1]) > 40 for v in vistas):
                        vistas.append(c)
        except Exception:                                     # noqa: BLE001
            pass
        for c in ballenas_por_forma(imgs):
            if all(abs(c[0] - v[0]) > 40 or abs(c[1] - v[1]) > 40 for v in vistas):
                vistas.append(c)
        return vistas
