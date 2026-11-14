"""Piratas normales del sistema, una flota por pirata."""
from __future__ import annotations

import re
import time

import cv2
import numpy as np

from vision.detectores import barras_de_flota, buscar_cerrar_x
from vision.plantillas import buscar_rotulo, localizar
from vision.recursos import silueta
from tareas.piratas import reservas
from tareas.piratas.reparto import _Reparto
from tareas.piratas.sigilo import PiratasSigilo


def desplazamiento(antes, despues, minimo=0.15):
    """Cuanto se ha movido la vista del mapa entre dos capturas: (dx, dy) en
    pixeles (un punto que estaba en x esta ahora en x + dx), (0, 0) si no se
    ha movido, o None si no se puede saber (pantallas muy distintas)."""
    k = 0.25
    a = cv2.resize(cv2.cvtColor(antes, cv2.COLOR_BGR2GRAY), None, fx=k, fy=k).astype(np.float32)
    b = cv2.resize(cv2.cvtColor(despues, cv2.COLOR_BGR2GRAY), None, fx=k, fy=k).astype(np.float32)
    ventana = cv2.createHanningWindow(a.shape[::-1], cv2.CV_32F)
    (dx, dy), resp = cv2.phaseCorrelate(a, b, ventana)
    if resp < minimo:
        return None
    dx, dy = dx / k, dy / k
    if abs(dx) < 4 and abs(dy) < 4:
        return 0.0, 0.0
    return dx, dy


class PiratasNormales(_Reparto, PiratasSigilo):
    """Piratas normales (simbolo rojo) del mapa del propio sistema.

    Por cada pirata: se pulsa su simbolo, se comprueba que es una "Flota
    pirata" (no el de sigilo, no un Elite, nunca un jugador) y se pulsa
    "Atacar" con UNA sola flota libre, sin salto. Asi van varias flotas a
    la vez a piratas distintos. Los piratas reaparecen solos al rato."""

    NOMBRE = "Piratas normales"
    UMBRAL_FLOTA = 0.85        # "Flota pirata": 1.00 el normal; 0.73 el de sigilo; <=0.41 jugadores
    RECIENTE_SEG = 480         # no volver a pulsar un simbolo ya atacado en este tiempo
    ESPERA_SIN_PIRATAS = 60

    def __init__(self, ctrl, log=None, stop=None, diag=True):
        super().__init__(ctrl, log=log, stop=stop, atacar=True, diag=diag,
                         usar_salto=False)
        self.status.update({"estado": "en espera", "ciclo": 0, "ciclos": 0,
                            "encontrados": 0, "atacados": 0})
        self.recientes = []            # (x, y, hora) en la vista del sistema
        self._ultimo_p = None

    @staticmethod
    def simbolos_pirata(img):
        """Simbolos rojos de los piratas normales en la vista del sistema,
        buscados POR SU FORMA en toda la pantalla (asi tambien salen los que
        estan encima del sol o pegados a otros iconos). Las estaciones de
        jugadores son doradas y las aliadas cian/verdes: no entran por color;
        el simbolo del pirata de sigilo tiene otra forma (da <= 0.45)."""
        h, w = img.shape[:2]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        t = hsv[:, :, 0].astype(np.float32) * 2.0
        # rojo-anaranjado del simbolo: el rojo puro cae cerca de 0/360
        m0 = (((t <= 32) | (t >= 350)) & (hsv[:, :, 1] > 170)
              & (hsv[:, :, 2] > 170)).astype(np.float32)
        tpl = silueta("icono_pirata").astype(np.float32)
        f = w / 1600.0
        mapa = np.zeros((h, w), np.float32)
        for esc in (1.15, 1.3, 1.45, 1.6):
            tt = (cv2.resize(tpl, None, fx=esc * f, fy=esc * f) > 0.5).astype(np.float32)
            r = cv2.matchTemplate(m0, tt, cv2.TM_CCOEFF_NORMED)
            oy, ox = tt.shape[0] // 2, tt.shape[1] // 2
            sub = mapa[oy:oy + r.shape[0], ox:ox + r.shape[1]]
            np.maximum(sub, r, out=sub)
        # 1) por manchas de color con la forma del simbolo (los sueltos)
        pts = []
        md = cv2.dilate(m0.astype(np.uint8), np.ones((5, 5), np.uint8))
        n, _, st, cen = cv2.connectedComponentsWithStats(md)
        for i in range(1, n):
            x, y, bw, bh, area = st[i]
            if area < 300 * f * f or not (15 * f <= bw <= 60 * f and 15 * f <= bh <= 60 * f):
                continue
            cx, cy = int(cen[i][0]), int(cen[i][1])
            if PiratasNormales.forma_normal(m0.astype(np.uint8), cx, cy) >= 0.55:
                pts.append((cx, cy))
        # 2) por forma en toda la pantalla (los pegados al sol u otros iconos)
        radio = int(28 * f)
        for _ in range(25):
            _, mx, _, (cx, cy) = cv2.minMaxLoc(mapa)
            if mx < 0.60:
                break
            mapa[max(0, cy - radio):cy + radio, max(0, cx - radio):cx + radio] = 0
            # fuera de los botones de la interfaz (arriba, abajo, columna derecha)
            if all(abs(cx - a) > radio or abs(cy - b) > radio for a, b in pts):
                pts.append((int(cx), int(cy)))
        # fuera de los botones de la interfaz (arriba, abajo, columna derecha)
        # (arriba queda fuera la franja de los avisos de alianza, que tiene
        # iconos naranjas)
        return [(x, y) for x, y in pts if 0.04 * w < x < 0.86 * w and 0.21 * h < y < 0.86 * h]

    @staticmethod
    def forma_normal(m, cx, cy) -> float:
        tpl = silueta("icono_pirata").astype(np.float32)
        reg = m[max(0, cy - 40):cy + 40, max(0, cx - 40):cx + 40].astype(np.float32)
        mejor = 0.0
        for esc in np.arange(0.8, 1.75, 0.05):
            t = (cv2.resize(tpl, None, fx=esc, fy=esc) > 0.5).astype(np.float32)
            if t.shape[0] >= reg.shape[0] or t.shape[1] >= reg.shape[1]:
                continue
            mejor = max(mejor, cv2.minMaxLoc(cv2.matchTemplate(reg, t, cv2.TM_CCOEFF_NORMED))[1])
        return float(mejor)

    def _es_normal(self, img):
        """Devuelve el centro de "Atacar" si la seleccion es un pirata normal
        con su menu propio, o None."""
        pf, c_f, e_f = localizar(img, "flota_pirata")
        if pf < self.UMBRAL_FLOTA:
            return None
        if localizar(img, "sigilo")[0] >= self.UMBRAL_SIGILO:
            return None                       # es el de sigilo: no es esta tarea
        pa, donde = buscar_rotulo(img, "atacar")
        e = e_f * 1.19                        # escala de "atacar" (plantilla de ventana)
        esperado = (c_f[0] + self.DX_ATACAR * e, c_f[1] + self.DY_ATACAR * e)
        if (pa >= self.UMBRAL_ATACAR and abs(donde[0] - esperado[0]) < 80 * e
                and abs(donde[1] - esperado[1]) < 60 * e):
            return donde
        return None

    def vista_sistema(self):
        """Vuelve a la vista general del sistema: cierra menus y, si hay
        boton Atras (vista acercada), lo pulsa. Nunca pulsa Atras sin
        menu ni boton Atras en pantalla."""
        for _ in range(5):
            img = self.cap("sistema")
            if self.menu_abierto(img):
                self.cerrar_menu(img)
                continue
            # en la base: boton "Sistema" (abajo a la derecha)
            p, c, _ = localizar(img, "sistema")
            if p >= 0.80 and c[0] > img.shape[1] * 0.6 and c[1] > img.shape[0] * 0.8:
                self.log("  Estoy en la base: voy a la vista del sistema.")
                self.ctrl.tap((c[0], c[1] - int(img.shape[0] * 0.06)))
                time.sleep(3.0)
                self.esperar_quieto(5.0, "carga_sistema")   # que acaben de salir las naves
                continue
            if localizar(img, "atras")[0] >= 0.72:
                self.atras(img)
                time.sleep(1.5)
                continue
            return img
        return self.cap("sistema")

    # alrededor del centro, tras acercar la vista: los restos de piratas
    # muertos (minerales, cristales, aleacion) quedan pegados y a veces el
    # toque los coge a ellos en vez de al pirata
    CERCA = ((0, -0.06), (0.04, 0), (-0.04, 0), (0, 0.06), (0.05, -0.08),
             (-0.05, -0.08), (0, -0.12), (0.07, 0.05), (-0.07, 0.05))

    def _esperar_menu(self, segundos, etiqueta="objetivo"):
        """Tras un toque en el mapa: vuelve en cuanto aparece el menu de
        seleccion (con un respiro para que termine de abrirse) o, si no
        sale, al acabar el tiempo con la ultima captura."""
        time.sleep(0.25)
        img = self.esperar(self.menu_abierto, segundos - 0.25, 0.15, etiqueta)
        if img is None:
            return self.cap(etiqueta)
        time.sleep(0.15)             # que termine de abrirse el menu
        return self.cap(etiqueta)

    def _buscar_cerca(self, img):
        """La vista ya esta acercada al sitio del simbolo pero lo elegido no es
        la flota pirata: probar puntos alrededor del centro. Nunca pulsa
        nada mas que el mapa; Atacar solo se pulsa luego, tras comprobar."""
        h, w = img.shape[:2]
        if localizar(img, "atras")[0] < 0.72 and not self.menu_abierto(img):
            return None                        # no se ha acercado: no insistir
        if self.menu_abierto(img):
            self.cerrar_menu(img)
            img = self.cap("cerca")
        # primero, debajo de las barras de vida de las flotas que se ven
        # (el pirata acercado son unas naves pequenas con su barra encima),
        # de la mas cercana al centro a la mas lejana; luego el anillo fijo
        cx, cy = w / 2, h / 2
        barras = sorted(barras_de_flota(img),
                        key=lambda b: (b[0] - cx) ** 2 + (b[1] - cy) ** 2)
        pts = []
        for bx, by, bw in barras[:5]:
            if abs(bx - cx) < 0.30 * w and abs(by - cy) < 0.32 * h:
                pts.append((int(bx), int(by + 0.6 * bw)))
        pts += [(int(cx + dx * w), int(cy + dy * h)) for dx, dy in self.CERCA]
        unicos = []
        for p in pts:
            if all(abs(p[0] - q[0]) > 25 or abs(p[1] - q[1]) > 25 for q in unicos):
                unicos.append(p)
        for punto in unicos[:self.MAX_CERCA]:
            if self.parado():
                return None
            self.ctrl.tap(punto)
            img = self._esperar_menu(1.4, "cerca")
            donde = self._es_normal(img)
            if donde is not None:
                self.log("  Habia restos encima; el pirata estaba al lado.")
                return donde
            if self.menu_abierto(img):
                self.cerrar_menu(img)
            elif buscar_cerrar_x(img) is not None or localizar(img, "llamar")[0] >= 0.80:
                self._recuperar(img)
        return None

    def _recuperar(self, img):
        """Un toque abrio algo que no es el menu del pirata: cerrarlo con su X
        o su boton Atras; si no tiene, Atras de Android (nunca en la base)."""
        if self.menu_abierto(img):
            self.cerrar_menu(img)
            return
        x = buscar_cerrar_x(img)
        if x is not None:
            self.log("  He abierto otra ventana; la cierro con la X.")
            self.ctrl.tap(x)
        elif buscar_rotulo(img, "atras")[0] >= 0.72:
            self.ctrl.tap(buscar_rotulo(img, "atras")[1])
        elif (localizar(img, "estacion")[0] < 0.80 and localizar(img, "sistema")[0] < 0.80
              and localizar(img, "diario")[0] < 0.80):
            self.log("  Pantalla desconocida; pulso Atras.")
            self.atras(img)
        else:
            return
        time.sleep(1.3)

    # --- reparto entre cuentas: todas estan en el mismo sistema y ven el
    # mapa igual, asi que un pirata al que ya va una flota de OTRA cuenta
    # (otra instancia) se apunta en un archivo comun y las demas lo saltan.
    RECLAMO_SEG = 480
    MAX_CERCA = 6          # toques a ciegas alrededor (cada uno ~3,5 s)

    # --- paso por turnos SOLO para elegir pirata y pulsar Atacar (unos
    # segundos): asi dos cuentas nunca eligen el mismo a la vez. En cuanto una
    # ataca, su pirata queda reclamado (archivo comun) y la siguiente elige
    # otro. Las flotas de todas las cuentas luchan a la vez, en piratas distintos.
    POR_TURNO = 4              # flotas que una cuenta puede mandar seguidas en su turno
    TURNO_MAX = 300            # elegir pirata + pulsar Atacar: nunca dura mas de esto
    LATIDO_SEG = 90            # una cuenta sin dar señales deja de contar
    LIBRE_SEG = 60             # si el turno queda libre y la elegida no llega, entra otra
    _ruta_turno_f = None       # solo para pruebas

    def _esperar_muerte(self, p):
        """Con el turno en la mano: espera a que el pirata atacado muera
        (su simbolo desaparece del mapa) o a que se acabe el tiempo."""
        fin = time.time() + self.TURNO_MAX - 20
        self.status["estado"] = "esperando a que muera el pirata"
        self.log("  Mi flota va al pirata; el turno pasa a la siguiente cuenta cuando muera.")
        self._esperar(40)                                  # el viaje
        while time.time() < fin and not self.parado():
            self.turno_latido()
            try:
                img = self.vista_sistema()
                cerca = [q for q in self.simbolos_pirata(img)
                         if abs(q[0] - p[0]) < 45 and abs(q[1] - p[1]) < 45]
                if not cerca:
                    self.log("  El pirata ya no esta: paso el turno.")
                    return
            except Exception as e:                         # noqa: BLE001
                self.log(f"  No he podido mirar el pirata: {e}")
            self._esperar(15)
        self.log("  Tiempo de turno agotado: paso el turno.")

    def _seguir_mapa(self, img):
        """Al pulsar un pirata el juego centra el mapa en el: los piratas ya
        atacados (apuntados por su sitio en pantalla) se mueven con el mapa.
        Se mide cuanto se ha movido la vista desde la ultima captura y se
        mueven igual, para no mandar una segunda flota al mismo pirata."""
        ant, self._img_ant = getattr(self, "_img_ant", None), img
        centro, self._centro_pend = getattr(self, "_centro_pend", None), None
        if ant is None or ant.shape != img.shape or not self.recientes:
            return
        d = desplazamiento(ant, img)
        if d is None:
            if centro is not None:
                self.recientes.append((centro[0], centro[1], time.time()))
            return
        dx, dy = d
        self.recientes = [(x + dx, y + dy, t) for x, y, t in self.recientes]

    # --- salto con UNA flota al lado del pirata (Ajustes > Piratas > Usar
    # salto). Como en sigilo, al pirata no se puede saltar: se salta a un
    # hueco vacio pegado a el y luego se ataca. Pero aqui solo salta la flota
    # que va a atacar (las demas pueden estar luchando con otros piratas).
    SALTO = False

    def _salto_una_flota(self) -> bool:
        """Dialogo «Elige tu flota» de «Movimiento en grupo»: marca SOLO la
        primera flota libre, comprueba «Salto de flota (1/6)» y lo pulsa."""
        img = self.esperar(lambda i: buscar_rotulo(i, "elige")[0] >= self.UMBRAL_DIALOGO, 6.0,
                           etiqueta="dialogo_salto")
        if img is None:
            self.log("  No se ha abierto la eleccion de flota para el salto.")
            return False
        _, c_el, esc = localizar(img, "elige")
        libres = self._tarjetas_libres(img, c_el, esc)
        if not libres:
            self.log("  No hay flotas libres para saltar.")
            self.atras(img)
            return False
        self.ctrl.tap((libres[0], int(c_el[1] + self.DY_CARA_TARJETA * esc)))
        time.sleep(1.0)
        img = self.cap("salto_marcada")
        from vision import ocr
        texto = "".join(d["texto"] for d in ocr.leer(img, zona=(0.55, 0.62, 0.8, 0.82))).replace(" ", "")
        ps, cs = buscar_rotulo(img, "salto")
        po, co = buscar_rotulo(img, "ok")
        if not re.search(r"[(\[]1/", texto) or ps < self.UMBRAL_DIALOGO or \
                po < self.UMBRAL_DIALOGO or cs[0] >= co[0]:
            self.log(f"  No veo «Salto de flota (1/…)» con una flota marcada ({texto}); no salto.")
            self.atras(img)
            return False
        self.ctrl.tap(cs)
        if self.esperar(lambda i: buscar_rotulo(i, "elige")[0] < 0.6, 6.0,
                        etiqueta="salto_hecho") is None:
            self.log("  El dialogo del salto no se cierra.")
            return False
        self.log("  Salto de flota: una flota al lado del pirata.")
        return True

    def _saltar_junto(self, img, donde) -> bool:
        """Con el menu del pirata abierto (el pirata en el centro): busca un
        hueco vacio a su lado y salta alli con la primera flota libre."""
        cg = self._boton_grupo(img, donde)
        if cg is None:
            return False
        e = localizar(img, "atacar")[2]
        h, w = img.shape[:2]
        centro = (w // 2, h // 2)
        estorbos = self._estorbos(img)
        for dx, dy in self.HUECOS:
            hueco = (int(centro[0] + dx * w), int(centro[1] + dy * h))
            if any((hueco[0] - ex) ** 2 + (hueco[1] - ey) ** 2 <= r ** 2 for ex, ey, r in estorbos):
                continue
            for _ in range(3):
                if self.parado():
                    return False
                self.ctrl.tap(hueco)
                time.sleep(1.4)
                img2 = self.cap("hueco")
                pm, cm, _ = localizar(img2, "movimiento")
                if pm >= self.UMBRAL_MOVIMIENTO and abs(cm[1] - cg[1]) < 45 * e \
                        and abs(cm[0] - cg[0]) < 140 * e:
                    self.ctrl.tap(cm)
                    return self._salto_una_flota()
                if self.menu_abierto(img2):
                    self.cerrar_menu(img2)          # otra cosa: probar otro hueco
                    break
        return False

    def _reabrir_pirata(self, p, img_antes):
        """Tras el salto el juego vuelve a la vista general: se mide cuanto
        se ha movido el mapa y se toca el pirata donde esta ahora. Devuelve
        donde esta su «Atacar» o None."""
        if self.esperar(lambda i: localizar(i, "flota_mov")[0] < 0.70, 20.0,
                        intervalo=1.5, etiqueta="salto_llegando") is None:
            self.log("  La flota sigue en movimiento; sigo igualmente.")
        img = self.vista_sistema()
        d = desplazamiento(img_antes, img) if img_antes.shape == img.shape else None
        q = (int(p[0] + (d[0] if d else 0)), int(p[1] + (d[1] if d else 0)))
        self.ctrl.tap(q)
        img2 = self._esperar_menu(2.0)
        donde = self._es_normal(img2)
        if donde is None:
            donde = self._buscar_cerca(img2)
        return donde

    _liberar_pend = ()

    def un_ataque(self) -> str:
        if not self._liberar_pend:
            self._liberar_pend = []
        self._reintentar_liberar()
        img = self.vista_sistema()
        self._seguir_mapa(img)
        self._limpiar_recientes()
        reclamos = self._leer_reclamos()
        pts = [p for p in self.simbolos_pirata(img)
               if not self._reciente(p) and not self._de_otra_cuenta(p, reclamos)
               and not reservas.reservado_por_otro(
                   self._yo(), (p[0] * 1600.0 / img.shape[1], p[1] * 1600.0 / img.shape[1]))]
        if not pts:
            return "sin_piratas"
        h, w = img.shape[:2]
        # primero los piratas sueltos: si estan pegados a estaciones, el toque
        # suele elegir la estacion y hay que buscarlo a ciegas (lento)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        tono = hsv[:, :, 0].astype(np.float32) * 2.0
        cian = ((tono > 175) & (tono < 215) & (hsv[:, :, 1] > 90)
                & (hsv[:, :, 2] > 120)).astype(np.uint8)
        r = int(45 * w / 1600)

        def apinado(p):
            return cian[max(0, p[1] - r):p[1] + r, max(0, p[0] - r):p[0] + r].mean()
        pts.sort(key=lambda p: (round(apinado(p) * 20),
                                (p[0] - w / 2) ** 2 + (p[1] - h / 2) ** 2))
        for p in pts[:5]:
            if self.parado():
                return "parado"
            # si no sale bien, se puede volver a probar este sitio en 60 s
            self.recientes.append((p[0], p[1], time.time() - self.RECIENTE_SEG + 60))
            self._reclamar(p, seg=40)          # reservado mientras lo intento
            self.ctrl.tap(p)
            # en cuanto sale el menu se sigue (antes: 1,6 s fijos siempre)
            img2 = self._esperar_menu(2.0)
            if not self.menu_abierto(img2):
                # puede que el toque solo acercara la vista: probar el centro
                self.ctrl.tap((img2.shape[1] // 2, img2.shape[0] // 2))
                img2 = self._esperar_menu(1.8)
            donde = self._es_normal(img2)
            if donde is None:
                donde = self._buscar_cerca(img2)
            if donde is None:
                # no se ha podido elegir: dejar este pirata 5 min y probar otros
                self.recientes[-1] = (p[0], p[1], time.time() - self.RECIENTE_SEG + 300)
                self._recuperar(self.cap("objetivo"))
                img = self.vista_sistema()
                self._seguir_mapa(img)
                continue
            self.status["encontrados"] += 1
            # comprobar otra vez justo antes de pulsar
            img3 = self.cap("antes_de_atacar")
            donde = self._es_normal(img3)
            if donde is None:
                self.log("  NO ataco: la seleccion ha cambiado.")
                self.cerrar_menu(img3)
                continue
            # otra cuenta ya va a este pirata (flota aliada en el panel, o
            # reserva compartida por sitio + fuerza): saltarlo
            pos1600 = (p[0] * 1600.0 / w, p[1] * 1600.0 / w)
            fuerza = reservas.leer_fuerza(img3)
            if reservas.con_flota_aliada(img3):
                self.log("  Ya lo esta atacando una flota aliada: lo salto.")
                motivo = True
            elif not reservas.reservar(self._yo(), pos1600, fuerza, parado=self.parado,
                                       log=self.log):
                self.log("  Otra cuenta ya ha reservado este pirata: lo salto.")
                motivo = True
            else:
                motivo = False
            if motivo:
                self.recientes[-1] = (p[0], p[1], time.time() - self.RECIENTE_SEG + 90)
                self.cerrar_menu(img3)
                img = self.vista_sistema()
                self._seguir_mapa(img)
                continue
            atacado = False
            try:
                if self.SALTO:
                    # saltar con la flota al lado y volver a abrir el pirata
                    if not self._saltar_junto(img3, donde):
                        self.log("  No he podido saltar al lado; ataco sin salto.")
                        self.vista_sistema()
                    donde = self._reabrir_pirata(p, img)
                    if donde is None:
                        self.log("  No vuelvo a encontrar el pirata tras el salto.")
                        self._recuperar(self.cap("objetivo"))
                        img = self.vista_sistema()
                        continue
                self.log("  Flota pirata comprobada: pulso Atacar (una flota).")
                self.ctrl.tap(donde)
                r = self._dialogo_una_flota()
                if r == "atacado":
                    atacado = True
                    self.recientes[-1] = (p[0], p[1], time.time())   # ya va una flota
                    # el juego lo ha llevado al centro del mapa: si no se puede
                    # medir cuanto se ha movido la vista, se apunta el centro
                    self._centro_pend = (w // 2, h // 2)
                    self._reclamar(p)          # las otras cuentas no lo atacan
                    self._ultimo_p = (p[0], p[1])
                return r
            finally:
                if not atacado:                # salto fallido, parado, error...: queda libre
                    self._liberar_reserva(pos1600, fuerza)
        return "sin_piratas"

    def _liberar_reserva(self, pos, fuerza):
        """Quita la reserva propia; si no se consigue el turno del archivo, se
        apunta y se reintenta al empezar el siguiente ataque."""
        if not reservas.liberar(self._yo(), pos, fuerza, parado=self.parado):
            self._liberar_pend.append((pos, fuerza))

    def _reintentar_liberar(self):
        pend, self._liberar_pend = self._liberar_pend, []
        for pos, fuerza in pend:
            self._liberar_reserva(pos, fuerza)

    def _dialogo_una_flota(self) -> str:
        """Tras "Atacar": puede salir la alerta de furia (Continuar) y luego
        "Elige tu flota", donde se manda la primera flota libre."""
        alertas = 0
        fin = time.time() + 8.0
        while time.time() < fin and not self.parado():
            img = self.cap("dialogo")
            if buscar_rotulo(img, "elige")[0] >= self.UMBRAL_DIALOGO:
                return self._elegir_una_flota(img)
            if self._alerta(img) and alertas < 2:
                alertas += 1
                self.ctrl.tap(buscar_rotulo(img, "continuar")[1])
                time.sleep(1.5)
                fin = max(fin, time.time() + 6.0)
                continue
            time.sleep(0.25)
        self.log("  No ha salido la eleccion de flota.")
        self.atras()
        return "sin_dialogo"

    # parar al completar la mision de fuerza pirata, mirandola en Cosmomante.
    # Solo la Rutina lo enciende, y solo si no tiene memoria de misiones; la
    # tarea suelta nunca entra en los eventos.
    PARAR_MISION = False
    CADA_MISION = 30 * 60
    _mision_vista = 0.0
    _mision_hecha = ""            # dia (del juego) en que se vio completa

    def mision_completa(self) -> bool:
        """Mira en Cosmomante si "Destruye una fuerza de mas de N flotas
        piratas" ya esta completa. Lo mira como mucho cada 30 min."""
        if not self.PARAR_MISION:
            return False
        dia = time.strftime("%Y-%m-%d", time.localtime(time.time() - 2 * 3600))
        if PiratasNormales._mision_hecha == dia:
            return True
        if time.time() - PiratasNormales._mision_vista < self.CADA_MISION:
            return False
        PiratasNormales._mision_vista = time.time()
        self.log("  Miro si la mision de fuerza pirata ya esta completa...")
        from tareas.cosmomante.juego import Cosmomante
        c = Cosmomante(self.ctrl, log=self._log, stop=self.stop, diag=self.diag_dir is not None)
        filas = c.fuerza_pirata()
        self.vista_sistema()
        if not filas:
            self.log("  No he podido leer la mision; sigo.")
            return False
        hecho, meta = max(filas, key=lambda f: f[1])
        if hecho >= meta:
            self.log(f"  Mision de fuerza pirata completa ({hecho:,} / {meta:,}).".replace(",", "."))
            PiratasNormales._mision_hecha = dia
            return True
        self.log(f"  Mision de fuerza pirata: {hecho:,} / {meta:,}; sigo.".replace(",", "."))
        return False

    def run(self, ciclos: int = 0, base: int = 0):
        self.status.update({"ciclos": ciclos, "ciclo": base})
        self.log(f"Piratas normales (una flota por pirata, sin salto). Ataques: "
                 f"{'sin limite' if ciclos == 0 else ciclos}.")
        hechos, vacios = 0, 0
        while (ciclos == 0 or hechos < ciclos) and not self.parado():
            try:
                if self.mision_completa():
                    self.log("Termino los piratas normales: la mision ya esta hecha.")
                    self.status["mision_hecha"] = True
                    break
            except Exception as e:                       # noqa: BLE001
                self.log(f"  Error al mirar la mision: {e}")
            if not self.turno_pedir():
                self.status["estado"] = "esperando a otra cuenta (eligiendo pirata)"
                self._esperar(2)
                continue
            self.status["estado"] = "buscando piratas"
            self._ultimo_p = None
            try:
                r = self.un_ataque()      # el reclamo del pirata queda escrito antes de soltar
                # en su turno una cuenta puede mandar varias flotas (cada una a un
                # pirata distinto) mientras le queden flotas libres
                extra = 0
                while (r == "atacado" and extra < self.POR_TURNO - 1 and not self.parado()
                       and (ciclos == 0 or hechos + 1 < ciclos)):
                    extra += 1
                    hechos += 1
                    vacios = 0
                    self.status["ciclo"] = base + hechos
                    time.sleep(0.3)
                    r = self.un_ataque()
            finally:
                self.turno_soltar()
            if r == "parado":
                break
            if r == "atacado":
                hechos += 1
                vacios = 0
                self.status["ciclo"] = base + hechos
                time.sleep(0.5)
                continue
            if r == "flotas_ocupadas":
                self.status["estado"] = "flotas ocupadas"
                self.log("  Todas las flotas estan ocupadas; espero 45 s.")
                self._esperar(45)
                continue
            vacios += 1
            if ciclos and vacios >= 6:
                self.log("No quedan piratas libres en el sistema; termino.")
                self.status["sin_piratas"] = True
                break
            # la primera vez puede ser que el mapa aun no haya cargado: mirar
            # enseguida otra vez; luego esperas cada vez mas largas
            espera = min((4, 15, 30)[vacios - 1] if vacios <= 3 else 60, self.ESPERA_SIN_PIRATAS)
            self.status["estado"] = "esperando piratas"
            if vacios > 1:
                self.log(f"  No veo piratas libres; vuelvo a mirar en {espera} s.")
            self._esperar(espera)
        self.turno_salir()
        self.status["estado"] = "parado" if self.parado() else "terminado"
        self.log(f"Hecho: {hechos} ataque(s) a piratas normales.")

    def _esperar(self, seg):
        fin = time.time() + seg
        while time.time() < fin and not self.parado():
            time.sleep(0.5)
