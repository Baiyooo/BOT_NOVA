"""Elegir y enviar flotas (ataque de grupo, salto, dialogo de flotas)."""
from __future__ import annotations

import time

import cv2
import numpy as np

from vision.detectores import _fraccion_color
from vision.plantillas import buscar_rotulo, localizar


class _EnvioFlotas:
    """Elegir y enviar flotas (ataque de grupo, salto, dialogo de flotas)."""

    def _pulsar_ataque_grupo(self) -> bool:
        """Captura otra vez justo antes de atacar y lo vuelve a comprobar
        todo: si en el ultimo momento la pantalla ha cambiado (se ha
        seleccionado otra cosa), no se pulsa nada."""
        img = self.cap("antes_de_atacar")
        cg, motivo = self._objetivo_seguro(img)
        if cg is None:
            self.log(f"  NO ataco: {motivo}.")
            self.cerrar_menu(img)
            return False
        self.log("  Objetivo comprobado (Sigilo pirata, 1.000 millones). "
                 "Pulso 'Ataque de grupo'.")
        self.ctrl.tap(cg)
        return True

    def _boton_grupo(self, img, donde_atacar):
        """'Ataque de grupo' esta justo debajo de 'Atacar' (+44, +94 a escala
        1, medido por ADB). Devuelve su centro o None."""
        pg, cg, _ = localizar(img, "grupo")
        e_at = localizar(img, "atacar")[2]
        esperado = (donde_atacar[0] + self.DX_GRUPO * e_at,
                    donde_atacar[1] + self.DY_GRUPO * e_at)
        if (pg >= self.UMBRAL_ATACAR and abs(cg[0] - esperado[0]) < 60 * e_at
                and abs(cg[1] - esperado[1]) < 40 * e_at):
            return cg
        return None

    def _saltar_al_lado(self, img, donde_atacar, cg, e):
        """Salta con todas las flotas a un hueco vacio al lado del pirata
        (al pirata no se puede saltar directamente).

        Con el menu del pirata abierto, el primer toque fuera del menu solo lo
        cierra (el pirata queda en el centro del mapa). El segundo toque en el
        hueco abre su menu: Mover flota / Movimiento en grupo / Construir /
        Salto de estacion / Marcador. Se comprueba que 'Movimiento en grupo'
        esta en la misma fila que 'Ataque de grupo' antes de pulsarlo.
        Devuelve (hecho, desplazamiento del hueco respecto al centro)."""
        h, w = img.shape[:2]
        centro = (w // 2, h // 2)
        # huecos posibles: abajo, arriba, izquierda y derecha del pirata. Se
        # descartan los que caen sobre una flota (barra cian/naranja), por
        # ejemplo las nuestras si ya estan al lado del pirata.
        estorbos = self._estorbos(img)
        opciones = []
        for dx, dy in self.HUECOS:
            p = (int(centro[0] + dx * w), int(centro[1] + dy * h))
            if all((p[0] - ex) ** 2 + (p[1] - ey) ** 2 > r ** 2
                   for ex, ey, r in estorbos):
                opciones.append(p)
        for hueco in opciones[:4]:
            desplaz = (hueco[0] - centro[0], hueco[1] - centro[1])
            img2 = img
            for toque in range(3):
                self.ctrl.tap(hueco)
                # en cuanto sale el menu del hueco se sigue (antes: 1,4 s fijos)
                time.sleep(0.3)
                # solo vale 'Movimiento en grupo' o un menu que NO sea el del
                # pirata (el suyo sigue abierto hasta que el primer toque lo cierra)
                img2 = self.esperar(
                    lambda i: (localizar(i, "movimiento")[0] >= self.UMBRAL_MOVIMIENTO
                               or (self.menu_abierto(i) and not self._menu_pirata(i))),
                    1.1, 0.2, "hueco")
                if img2 is None:
                    img2 = self.cap("hueco")
                pm, cm, _ = localizar(img2, "movimiento")
                en_fila = (abs(cm[1] - cg[1]) < 45 * e
                           and abs(cm[0] - cg[0]) < 140 * e)
                if pm >= self.UMBRAL_MOVIMIENTO and en_fila:
                    self.log("  Hueco al lado del pirata: pulso 'Movimiento en "
                             f"grupo' ({pm:.2f}).")
                    self.ctrl.tap(cm)
                    r = self._dialogo_flotas("salto", comprobar_libres=False,
                                             contar=False, como="salto de flota")
                    if r == "atacado":
                        time.sleep(self.ESPERA_TRAS_SALTO)
                        return True, desplaz
                    self.log("  El salto no se ha completado.")
                    return False, desplaz
                if self.menu_abierto(img2) and not self._menu_pirata(img2):
                    # ha seleccionado otra cosa: cerrar y probar el otro lado
                    self.cerrar_menu(img2)
                    break
                # sin menu: el toque solo ha cerrado el anterior; repetir
            self.log("  Ese hueco no sirve; pruebo otro.")
            img = self.cap("hueco")
        return False, None

    def _menu_pirata(self, img) -> bool:
        """Sigue abierto el menu del pirata (tiene 'Atacar')."""
        return buscar_rotulo(img, "atacar")[0] >= self.UMBRAL_ATACAR

    def _casilla_marcada(self, img, c_sel, esc) -> bool:
        cx, cy = c_sel[0] + self.DX_CASILLA * esc, c_sel[1]
        verde = _fraccion_color(img, cx - 15 * esc, cy - 15 * esc,
                                cx + 15 * esc, cy + 15 * esc, 90, 170)
        return verde > 0.03          # 0.00 desmarcada, ~0.08 marcada

    def _flotas_libres(self, img, c_sel, esc) -> bool:
        """Cabeceras de las tarjetas: verde = Base/Inactivo, naranja =
        Moviendose. Medido: libres 0.064/0.005, ocupadas 0.000/0.15."""
        y = c_sel[1] + self.DY_CABECERAS * esc
        x0, x1 = c_sel[0] - 1120 * esc, c_sel[0] + 180 * esc
        verde = _fraccion_color(img, x0, y - 9 * esc, x1, y + 9 * esc, 70, 170)
        naranja = _fraccion_color(img, x0, y - 9 * esc, x1, y + 9 * esc, 15, 55)
        return verde > naranja

    def _tarjetas_libres(self, img, c_el, esc) -> list[int]:
        """En "Elige tu flota" cada tarjeta lleva arriba su estado: verde
        (Inactivo/Base) si esta libre, naranja si se esta moviendo.
        Devuelve la x central de las libres, de izquierda a derecha.
        Medido por ADB: cabeceras 66 px por debajo del titulo, 85 de ancho,
        separadas 225."""
        h, w = img.shape[:2]
        y = c_el[1] + self.DY_TARJETAS * esc
        y0, y1 = int(max(0, y - 12 * esc)), int(min(h, y + 12 * esc))
        x0 = int(max(0, c_el[0] - 720 * esc))
        x1 = int(min(w, c_el[0] + 720 * esc))
        if y1 <= y0 or x1 <= x0:
            return []
        hsv = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
        t = hsv[:, :, 0].astype(np.float32) * 2.0
        vivo = (hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 110)
        col = (vivo & (t > 70) & (t < 170)).sum(0)
        xs = np.nonzero(col > 0)[0]
        if len(xs) == 0:
            return []
        grupos, ini, prev = [], xs[0], xs[0]
        for x in xs[1:]:
            if x - prev > 20 * esc:
                grupos.append((ini, prev))
                ini = x
            prev = x
        grupos.append((ini, prev))
        return [int(x0 + (a + b) / 2) for a, b in grupos
                if 50 * esc < b - a < 130 * esc]

    def _elegir_una_flota(self, img) -> str:
        """Variante del dialogo: "Elige tu flota" con una tarjeta por flota.
        Pulsar una tarjeta libre la manda directamente (viaje normal: este
        dialogo no ofrece salto)."""
        p, c_el, esc = localizar(img, "elige")
        libres = self._tarjetas_libres(img, c_el, esc)
        if not libres:
            self.log("  Todas las flotas estan ocupadas; no envio nada.")
            self.atras(img)
            return "flotas_ocupadas"
        destino = (libres[0], int(c_el[1] + self.DY_CARA_TARJETA * esc))
        self.log(f"  Elijo la primera flota libre ({len(libres)} libre(s)).")
        self.ctrl.tap(destino)
        if self.esperar(lambda i: buscar_rotulo(i, "elige")[0] < 0.6,
                        6.0, 0.25, etiqueta="enviado") is None:
            self.log("  El dialogo no se cierra; algo no ha ido bien.")
            return "sin_confirmar"
        self.status["atacados"] += 1
        self.log("  Ataque lanzado (la flota va de camino).")
        return "atacado"

    def _dialogo_flotas(self, boton: str = "ok", comprobar_libres: bool = True,
                        contar: bool = True, como: str = "") -> str:
        """Dialogo "Elige tu flota" con "Seleccionar todo": marcar todas y
        enviar con el boton indicado: "salto" (Salto de flota, instantaneo,
        gasta material azul; solo vale para moverse a un hueco) u "ok"."""
        # Puede salir antes la ALERTA de furia pirata; se confirma con
        # "Continuar" y entonces aparece el dialogo de flotas.
        img, alertas = None, 0
        fin = time.time() + 10.0
        while time.time() < fin and not self.parado():
            img = self.cap("dialogo")
            if buscar_rotulo(img, "seleccionar")[0] >= self.UMBRAL_DIALOGO:
                break
            if (buscar_rotulo(img, "elige")[0] >= self.UMBRAL_DIALOGO
                    and buscar_rotulo(img, "seleccionar")[0] < 0.6):
                time.sleep(0.4)          # por si aun se esta dibujando
                img = self.cap("dialogo")
                if buscar_rotulo(img, "seleccionar")[0] >= self.UMBRAL_DIALOGO:
                    break
                return self._elegir_una_flota(img)
            if self._alerta(img):
                if alertas >= 2:
                    self.log("  La alerta no se cierra; lo dejo.")
                    return "alerta_atascada"
                alertas += 1
                _, c_cont = buscar_rotulo(img, "continuar")
                self.log("  Alerta de furia pirata: pulso Continuar.")
                self.ctrl.tap(c_cont)
                time.sleep(1.5)
                fin = max(fin, time.time() + 8.0)
                continue
            time.sleep(0.25)
            img = None
        if img is None or buscar_rotulo(img, "seleccionar")[0] < self.UMBRAL_DIALOGO:
            self.log("  No se ha abierto el dialogo de flotas.")
            return "sin_dialogo"
        p, c_sel, esc = localizar(img, "seleccionar")

        # 1) marcar "Seleccionar todo" (viene desmarcado). Pulsar la casilla
        #    la ALTERNA, asi que solo se pulsa si no esta ya marcada.
        casilla = (int(c_sel[0] + self.DX_CASILLA * esc), int(c_sel[1]))
        marcada = self._casilla_marcada(img, c_sel, esc)
        for _ in range(2):
            if marcada:
                break
            # el dialogo puede haberse movido: recalcular donde esta la casilla
            p, c_nuevo, e_nuevo = localizar(img, "seleccionar")
            if p >= self.UMBRAL_DIALOGO:
                c_sel, esc = c_nuevo, e_nuevo
                casilla = (int(c_sel[0] + self.DX_CASILLA * esc), int(c_sel[1]))
            antes = img
            self.ctrl.tap(casilla)
            time.sleep(0.3)
            # sale en cuanto la casilla se marca; si no, tras 1,5 s se queda
            # con la ultima captura (antes: 1,0 s fijo)
            img = self.esperar(lambda i, c=c_sel, k=esc: self._casilla_marcada(i, c, k),
                               1.5, 0.2, "casilla")
            if img is None:
                img = self.cap("casilla")
            # marcada si sale la marca verde, o si la casilla ha cambiado de
            # aspecto tras pulsarla (venia vacia: el cambio es marcarla)
            r = int(18 * esc)
            x0, y0 = max(0, casilla[0] - r), max(0, casilla[1] - r)
            cambio = float(np.abs(
                antes[y0:casilla[1] + r, x0:casilla[0] + r].astype(np.int16)
                - img[y0:casilla[1] + r, x0:casilla[0] + r].astype(np.int16)).mean())
            marcada = self._casilla_marcada(img, c_sel, esc) or cambio > 20
        if not marcada:
            self.log("  No consigo marcar 'Seleccionar todo'; no envio nada.")
            self.atras(img)
            return "sin_flotas"

        # 2) enviar
        if boton == "salto":
            ps, cs = buscar_rotulo(img, "salto")
            po, co = buscar_rotulo(img, "ok")
            # el salto tiene que estar A LA IZQUIERDA del OK, como en el juego
            if ps < self.UMBRAL_DIALOGO or po < self.UMBRAL_DIALOGO or cs[0] >= co[0]:
                self.log(f"  No reconozco bien los botones (salto {ps:.2f}, "
                         f"ok {po:.2f}); no envio.")
                self.atras(img)
                return "sin_boton_enviar"
            self.ctrl.tap(cs)
        else:
            if comprobar_libres and not self._flotas_libres(img, c_sel, esc):
                self.log("  Las flotas siguen ocupadas; no las desvio.")
                self.atras(img)
                return "flotas_ocupadas"
            po, co = buscar_rotulo(img, "ok")
            if po < self.UMBRAL_DIALOGO or abs(co[0] - c_sel[0]) > 140 * esc:
                self.log(f"  No reconozco el boton OK ({po:.2f}); no envio.")
                self.atras(img)
                return "sin_boton_enviar"
            self.ctrl.tap(co)

        # 3) comprobar que el dialogo se ha cerrado
        if self.esperar(lambda i: buscar_rotulo(i, "seleccionar")[0] < 0.6,
                        6.0, 0.25, etiqueta="enviado") is None:
            self.log("  El dialogo no se cierra; algo no ha ido bien.")
            return "sin_confirmar"
        if contar:
            self.status["atacados"] += 1
            self.log(f"  Ataque lanzado ({como or 'ataque de grupo con OK'}).")
        else:
            self.log(f"  Flotas enviadas ({como}).")
        return "atacado"
