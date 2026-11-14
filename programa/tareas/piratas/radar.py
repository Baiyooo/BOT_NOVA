"""Abrir el radar y encontrar con el los piratas."""
from __future__ import annotations

import time

import cv2
import numpy as np

from vision.detectores import barras_de_flota, buscar_cerrar_x
from vision.plantillas import buscar_rotulo
from vision.experiencia import experiencia


class _Radar:
    """Abrir el radar y encontrar con el los piratas."""

    def radar_abierto(self, img) -> bool:
        return buscar_rotulo(img, "radar")[0] >= self.UMBRAL_RADAR

    def abrir_radar(self) -> bool:
        """Abre la pantalla del radar. Tres caminos, por orden:
        1) el boton de la mira de la barra de abajo (no siempre esta),
        2) "Mas" de arriba y luego "Buscar pirata" en el menu lateral,
        3) como ultimo recurso, la posicion aproximada del boton de abajo."""
        img = self.cap("inicio")
        if self.radar_abierto(img):
            return True
        # Dejar el juego en el mapa: cerrar lo que haya abierto (alerta, menu
        # de seleccion, vista de batalla). Atras solo cuando hay algo que
        # cerrar: en el mapa sin nada abierto quitaria el zoom.
        for _ in range(5):
            if self._alerta(img):
                self.log("  Habia una alerta abierta; la cierro.")
            elif self.menu_abierto(img):
                self.log("  Habia un menu abierto; lo cierro.")
            elif self.en_vista_batalla(img):
                self.vigilar_defensa(img)
                self.log("  Estaba en la vista de una batalla; salgo.")
            elif buscar_cerrar_x(img) is not None:
                self.log("  Habia una ventana de evento abierta; la cierro con la X.")
                self.ctrl.tap(buscar_cerrar_x(img))
                time.sleep(1.5)
                img = self.cap("inicio")
                continue
            elif (buscar_rotulo(img, "atras")[0] >= 0.72
                  and buscar_rotulo(img, "mira")[0] < 0.65):
                self.log("  Habia una pantalla abierta; salgo con su boton Atras.")
                self.ctrl.tap(buscar_rotulo(img, "atras")[1])
                time.sleep(1.5)
                img = self.cap("inicio")
                continue
            else:
                break
            self.atras(img)
            time.sleep(1.5)
            img = self.cap("inicio")
            if self.radar_abierto(img):
                return True

        p, donde = buscar_rotulo(img, "mira")
        if p >= self.UMBRAL_ICONO:
            self.log(f"  Abro el radar con la mira de abajo ({p:.2f}).")
            self.ctrl.tap(donde)
            if self.esperar(self.radar_abierto, 6.0,
                            etiqueta="tras_mira") is not None:
                return True

        img = self.cap("antes_mas")
        p, donde = buscar_rotulo(img, "mas")
        if p >= self.UMBRAL_ICONO:
            self.log(f"  Pruebo por 'Mas' ({p:.2f}).")
            self.ctrl.tap(donde)
            time.sleep(1.5)
            img = self.cap("menu_mas")
            p2, donde2 = buscar_rotulo(img, "menu_pirata")
            if p2 >= 0.60:
                self.ctrl.tap(donde2)
                if self.esperar(self.radar_abierto, 6.0,
                                etiqueta="tras_menu") is not None:
                    return True
            else:
                self.log(f"  No veo 'Buscar pirata' en el menu ({p2:.2f}).")
                self.pulsar_rotulo(img, "atras", self.P_ATRAS)
                time.sleep(1.0)

        self.log("  Ultimo recurso: posicion aproximada.")
        img = self.cap("antes_aprox")
        self.pulsar(img, self.P_BUSCAR_PIRATA)
        return self.esperar(self.radar_abierto, 6.0, etiqueta="tras_aprox") is not None

    def _candidatos(self, img) -> list[tuple[int, int]]:
        h, w = img.shape[:2]
        cx, cy = w // 2, h // 2
        centro = [(int(cx + dx * w), int(cy + dy * h)) for dx, dy in self.ALREDEDORES[:3]]
        # Si el "Ir a" ya se habia pulsado antes para este pirata (busqueda
        # repetida), la camara baja y el pirata queda en la parte superior de
        # la pantalla, no en el centro: se busca primero arriba.
        arriba = getattr(self, "pirata_arriba", False)
        ref = (cx, int(h * 0.27)) if arriba else (cx, cy)
        barras = sorted(barras_de_flota(img),
                        key=lambda b: (b[0] - ref[0]) ** 2 + (b[1] - ref[1]) ** 2)
        pts_barras = []
        for bx, by, bw in barras[:6]:
            for k in (1.3, 0.8):            # el aro de la flota cae debajo
                pts_barras.append((bx, int(by + k * bw)))
        # anillo de puntos alrededor del centro: el pirata puede estar
        # pegado a otras flotas (las nuestras incluidas) y sin barra visible
        anillo = []
        for r in (0.13, 0.22):
            for ang in range(0, 360, 45):
                a = np.radians(ang)
                anillo.append((int(cx + r * h * np.cos(a)), int(cy + r * h * np.sin(a))))
        if arriba:
            sup = [(cx, int(h * f)) for f in (0.27, 0.20, 0.34)]
            pts = pts_barras[:4] + sup + centro + pts_barras[4:] + anillo
        else:
            pts = centro + pts_barras + anillo
        # lo aprendido va primero: donde mas veces ha aparecido el pirata
        modo = "arriba" if arriba else "centro"
        aprendidos = [(int(ref[0] + dx * w), int(ref[1] + dy * h))
                      for dx, dy in experiencia().sitios_pirata(modo)]
        self._ref_candidatos = (ref, modo)
        pts = aprendidos + pts
        # quitar repetidos muy cercanos
        unicos = []
        for p in pts:
            if all(abs(p[0] - q[0]) > 25 or abs(p[1] - q[1]) > 25 for q in unicos):
                unicos.append(p)
        # fuera de la zona de botones de la interfaz
        unicos = [p for p in unicos if 0.10 * w < p[0] < 0.82 * w and 0.12 * h < p[1] < 0.80 * h]
        return unicos[:22]

    def texto_boton_radar(self, img, caja) -> str:
        """Distingue "Ir a" de "Buscar" por el ancho del texto dentro del
        boton. Medido: "Ir a" 0.13-0.21 del ancho, "Buscar" 0.35-0.38.
        El juego usa texto ambar o blanco segun el estilo del boton, asi que
        se miden los dos (con solo el ambar, el boton blanco daba "?")."""
        x, y, w, h = caja
        hsv = cv2.cvtColor(img[y + 10:y + h - 10, x + 16:x + w - 16], cv2.COLOR_BGR2HSV)
        ambar = ((hsv[:, :, 0] > 12) & (hsv[:, :, 0] < 30)
                 & (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 90))
        claro = (hsv[:, :, 2] > 110) & (hsv[:, :, 1] < 80)
        m = (ambar | claro).astype(np.uint8)
        cols = np.nonzero(m.sum(0) >= 2)[0]
        if len(cols) == 0:
            return "?"
        r = (cols.max() - cols.min()) / w
        return "ir_a" if r < 0.27 else ("buscar" if r < 0.60 else "?")
