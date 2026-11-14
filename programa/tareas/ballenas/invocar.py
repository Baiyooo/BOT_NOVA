"""Invocar ballenas con los Senuelos de eter y localizarlas en el sistema."""
from __future__ import annotations

import time

from cerebro.memoria_eventos import sin_acentos
from tareas.ballenas.deteccion import SLOT2, anillos_rojos, ballenas_por_forma


class _Invocar:
    """Invocar ballenas con los Senuelos de eter y localizarlas en el sistema."""

    def _almacen_por_vecinos(self) -> bool:
        """Toca el ICONO de Almacén de la barra de arriba (tocar el rotulo no
        abre nada). El lector lo lee mal ("len", o junto a otros rotulos), asi
        que se usa su sitio fijo en la barra (1600x900: icono en (750, 44)),
        comprobando que la barra esta ahi (se ven «Alianza» o «Base»)."""
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
        self.ctrl.tap((int(w * 750 / 1600), int(h * 44 / 900)))
        time.sleep(3.0)
        return True

    # ------------------------------------------------------- 1) invocar --
    def invocar(self, n: int) -> int:
        """Usa n Señuelos de eter V. Devuelve cuantas ballenas se han invocado."""
        if not self.ir_a_base():
            self.log("  No encuentro la base para abrir el Almacén.")
            return 0
        time.sleep(3.0)               # la base acaba de cargar: aun no hace caso a los toques
        abierto = False
        for _ in range(3):
            if self.parado():
                return 0
            if not self._almacen_por_vecinos():
                continue
            # se abre un menu Tienda / Cajas / Descuento / Almacén / Fragmento
            if self._toca(("almacen",), "almacen2", zona=(0.25, 0.5, 0.75, 0.9), espera=2.5,
                          intentos=2):
                abierto = True
                break
        if not abierto:
            self.log("  No se abre el Almacén.")
            self.volver_a_base()
            return 0
        self._toca(("objeto comun",), "objeto_comun", zona=(0, 0.15, 0.2, 0.4), espera=1.5)
        r = self._espera_texto(("senuelo de eter",), 3, "senuelo", zona=(0.62, 0.3, 1, 0.6))
        if r is None:
            self.ctrl.tap(SLOT2)
            time.sleep(1.5)
            r = self._espera_texto(("senuelo de eter",), 4, "senuelo", zona=(0.62, 0.3, 1, 0.6))
        if r is None:
            self.log("  No encuentro el Señuelo de éter en Objeto común; no gasto nada.")
            self._atras_juego(2)
            return 0
        hechas = 0
        for _ in range(n):
            if self.parado():
                break
            d = self._toca(("usar",), "usar", zona=(0.62, 0.72, 1, 0.95), espera=1.2, intentos=2)
            if d is None:
                break
            r = self._espera_texto(("invocada correctamente", "cantidad actual"), 4, "invocada")
            if r is None:
                self.log("  No sale la confirmación de la invocación; paro de invocar.")
                break
            hechas += 1
            txt = sin_acentos(r[2]["texto"])
            self.log(f"  Ballena invocada ({txt[-6:].strip()}).")
            if "10/10" in txt.replace(" ", ""):
                break
            time.sleep(1.5)
        self._atras_juego(2)
        return hechas

    # ---------------------------------------------------- 2) el sistema --
    def mi_sistema(self):
        """Vista general del sistema de MI estacion: Mi estacion y Atras."""
        self._quitar_salir()
        img, items = self._ocr("mapa")
        h, w = img.shape[:2]
        # atajo: ya estoy en la vista general del sistema (sale «Mi estación» y
        # no hay «Atrás» arriba a la izquierda): no hace falta rehacer el camino
        if (self._busca(items, "mi estacion", zona=(0.1, 0.85, 0.35, 1), w=w, h=h)
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
