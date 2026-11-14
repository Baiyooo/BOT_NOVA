"""Defensa: ver si una flota propia entra en combate con un jugador y retirarla."""
from __future__ import annotations

import time

import numpy as np

from vision.plantillas import buscar_rotulo, localizar
from vision.detectores import jugador_en_batalla
from vision.mascaras import mascara_ambar, mascara_rojo


class _Defensa:
    """Defensa: ver si una flota propia entra en combate con un jugador y retirarla."""

    def vigilar_defensa(self, img) -> bool:
        """Con la vista de una batalla en pantalla, mira la lista "Flota
        hostil": si hay alguien que no es un pirata (un jugador), retira las
        flotas una a una con su "Llamar" (nunca "Llamar a todos", que es de
        pago). Devuelve True si ha visto a un jugador.
        (Aun no se abre la batalla a proposito: el icono de combate del mapa
        se confunde con otros iconos rojos. Falta una captura de un ataque
        de un jugador para poder vigilarlo siempre.)"""
        if not self.DEFENSA or img is None or not self.en_vista_batalla(img):
            return False
        if not jugador_en_batalla(img):
            return False
        time.sleep(1.0)                   # confirmarlo con otra captura
        img = self.cap("defensa_jugador")
        if not (self.en_vista_batalla(img) and jugador_en_batalla(img)):
            return False
        self.log("  ¡AVISO! Un jugador ha entrado en combate con mis flotas: las retiro.")
        n = self.retirar_flotas()
        if n:
            self.log(f"  {n} flota(s) retirada(s) con Llamar.")
        else:
            self.log("  No he encontrado el boton Llamar de las flotas. Captura "
                     "guardada en diagnostico para ensenarselo al bot.")
        self.status["defensa"] = self.status.get("defensa", 0) + 1
        return True

    def retirar_flotas(self) -> int:
        n = 0
        for y in self.FILAS_ALIADAS:
            if self.parado():
                break
            img = self.cap("retirar")
            h, w = img.shape[:2]
            if not self.en_vista_batalla(img):
                break
            self.ctrl.tap((int(w * 0.09), int(y * h / 900)))
            time.sleep(1.3)
            img = self.cap("retirar_menu")
            p, c, _ = localizar(img, "llamar")
            if p >= 0.80:
                self.ctrl.tap(c)
                n += 1
                time.sleep(1.3)
            elif self.menu_abierto(img):
                self.cerrar_menu(img)
                time.sleep(0.8)
        return n

    def en_vista_batalla(self, img) -> bool:
        """Vista de una batalla en curso (lista de flotas a la izquierda y
        "Llamar a todos" en rojo abajo). Medido: 0.14-0.16 de rojo en esa
        esquina, 0.08 en el mapa normal; y no esta la mira de abajo."""
        h, w = img.shape[:2]
        rojo = mascara_rojo(img[int(h * 0.86):int(h * 0.93),
                                int(w * 0.01):int(w * 0.10)]).mean()
        return rojo > 0.11 and buscar_rotulo(img, "mira")[0] < self.UMBRAL_ICONO

    @staticmethod
    def ancho_fuerza(img, c_sig, e) -> float:
        """Largo del numero naranja de "Fuerza" bajo el cartel, a escala 1.
        El sigiloso tiene 1.002.240.000 (13 caracteres): mide ~151. Un pirata
        normal de 777.600 (7 caracteres) mide la mitad."""
        h, w = img.shape[:2]
        y0, y1 = int(c_sig[1] + 50 * e), int(c_sig[1] + 72 * e)
        x0, x1 = int(c_sig[0] - 300 * e), int(c_sig[0] + 95 * e)
        y0, y1 = max(0, y0), min(h, y1)
        x0, x1 = max(0, x0), min(w, x1)
        if y1 <= y0 or x1 <= x0:
            return 0.0
        cols = np.nonzero(mascara_ambar(img[y0:y1, x0:x1]).sum(0) >= 2)[0]
        if len(cols) == 0:
            return 0.0
        # bloques de texto (huecos de hasta 14 px); se queda el mas ancho. No
        # vale el de mas a la derecha: el aro naranja de seleccion puede caer
        # justo al final de la fila.
        mejor, ini, prev = 0, cols[0], cols[0]
        for c in list(cols[1:]) + [None]:
            if c is None or c - prev > 14 * e:
                mejor = max(mejor, prev - ini)
                if c is None:
                    break
                ini = c
            prev = c
        return float(mejor) / e

    @staticmethod
    def en_combate(img) -> bool:
        """Mientras hay combate sale un icono rojo fijo a la derecha del mapa.
        Medido: 0.36 de rojo en combate, 0.00 sin el."""
        h, w = img.shape[:2]
        zona = mascara_rojo(img[int(h * 0.50):int(h * 0.57), int(w * 0.905):int(w * 0.94)])
        return float(zona.mean()) > 0.15

    def esperar_fin_combate(self):
        """Espera a que el pirata quede destruido. Ni el viaje ni el combate
        duran un tiempo fijo (sin salto el viaje puede ser de minutos), asi
        que se mira el icono rojo de combate cada 1 s: primero se espera a
        que APAREZCA (dos veces seguidas: las flotas han llegado) y luego a
        que DESAPAREZCA seis veces seguidas (el pirata ya esta destruido)."""
        self.status["estado"] = "combatiendo"
        self.log("  Espero a que lleguen las flotas y termine el combate...")
        t0 = time.time()
        visto, sin_icono, con_icono = False, 0, 0
        n = 0
        while not self.parado():
            n += 1
            img = self.cap("combate") if n % 4 == 1 else self.ctrl.capture()
            if self.vigilar_defensa(img):
                self.log("  Combate con un jugador: dejo este pirata.")
                return False
            if self.en_combate(img):
                con_icono += 1
                if not visto and con_icono >= 2:
                    visto = True
                    self.log(f"  Flotas en combate ({time.time() - t0:.0f} s de viaje).")
                sin_icono = 0
                self.status["estado"] = "combatiendo"
            else:
                con_icono = 0
                if visto:
                    sin_icono += 1
                else:
                    self.status["estado"] = "flotas de camino"
            pasado = time.time() - t0
            if visto and sin_icono >= 6:
                self.log(f"  Combate terminado ({pasado:.0f} s).")
                return True
            if not visto and pasado > self.ESPERA_INICIO_COMBATE:
                # las flotas no han llegado (o no se ve el icono): no esperar mas
                self.log(f"  No veo combate tras {pasado:.0f} s; sigo.")
                return False
            if pasado > self.ESPERA_MAX_COMBATE:
                self.log(f"  El combate sigue tras {pasado:.0f} s; sigo igualmente.")
                return False
            time.sleep(1.0)
        return False
