"""Cosmomante: jugar el tablero, multiplicadores e imanes, y ascender de nivel."""
from __future__ import annotations

import math
import random
import time

from nucleo import config as _cfg
from tareas.cosmomante import mapa as cm
from nucleo.rutas import carpeta_diag
from vision.cifras import leer_cifras
from vision.plantillas import localizar
from tareas.cosmomante.base import _CosmomanteBase


class Cosmomante(_CosmomanteBase):
    """La unica estrategia de Cosmomante.

    1) Lee el mapa, el nivel/progreso y los recursos: dados remotos, azules,
       imanes y dados normales.
    2) ANTES de gastar, estima por estadistica si esos dados alcanzan para
       subir al nivel 6. Si no llega, no gasta ninguno y los guarda para el
       proximo evento.
    3) Si llega, usa las tiradas gratis, luego remotos/azules con imanes,
       asciende al llenar la barra y despues los normales hasta la meta mas
       alta que sea alcanzable (30, 50 o 100).
    4) Asciende hasta el nivel 6.
    5) Reclama las metas de dados completadas (30, 50 y 100).
    Anota cada jugada en cosmomante_log.jsonl."""

    NOMBRE = "Cosmomante"
    MULTIPLICADORES = True        # usar dado remoto + imanes + x2
    ASCENDER = True               # subir de nivel solo
    NIVEL_MAX = 6                 # nivel objetivo de Cosmomante
    JUGADAS_MAX = 12              # jugadas con dado remoto por pasada
    # coordenadas en una captura de 1600x900
    ICONOS = {"remoto": (87, 810), "azul": (214, 810), "dorado": (335, 810), "x2": (462, 810)}
    USAR_MULT = (972, 605)        # "Usar" del dialogo de imanes y x2
    NUM_X = {1: 421, 2: 571, 3: 721, 4: 871, 5: 1021, 6: 1171}
    NUM_Y = 523
    USAR_REMOTO = (972, 691)
    BOTON_ASCENDER = (1145, 790)
    BOTON_ASCENDER_PANEL = (1330, 758)
    UMBRAL_NIVEL = 0.70           # probabilidad minima para gastar dados

    def __init__(self, ctrl, log=None, stop=None, diag=True):
        super().__init__(ctrl, log=log, stop=stop, diag=diag)
        self.status.update({"jugadas": 0, "nivel": None, "ascensos": 0})
        self._sin_remoto = False
        self._sin_dados = False
        self._pos_pendiente = False
        self._remotos = None
        self._azules = None
        self._magnetos = 0
        self._x2 = 0

    # ------------------------------------------------------------ estado --
    def _ruta_pos(self):
        import os
        nombre = str(getattr(self.ctrl, "name", "inst")).replace(":", "_")
        return os.path.join(os.path.dirname(carpeta_diag()), f"cosmomante_pos_{nombre}.json")

    def _leer_pos(self):
        return _cfg.leer(self._ruta_pos())

    def _guardar_pos(self, pos, rec):
        datos = {"pos": pos, "rec": sorted(rec)}
        if pos is None:
            ant = self._leer_pos()
            ultimo = ant.get("pos") if ant.get("pos") is not None else ant.get("pos_antes")
            if ultimo is not None:
                datos["pos_antes"] = ultimo         # ultimo punto conocido, para deducir despues
        mem = getattr(self, "_mapa_mem", None)
        if mem:                                   # recompensas vistas del nivel
            datos["mapa"] = {str(i): [c, bool(r)] for i, (c, r) in mem.items()}
            datos["tipos"] = {str(i): t for i, t in getattr(self, "_tipos_mem", {}).items()}
        _cfg.guardar(self._ruta_pos(), datos)

    def _perder_pos(self):
        """Tras tiradas al azar: pos desconocida pero se conserva lo recogido antes."""
        g = self._leer_pos()
        self._guardar_pos(None, set(g.get("rec", [])))

    def _anotar(self, **kw):
        import json
        import os
        try:
            base = os.path.join(os.path.dirname(carpeta_diag()), "cosmomante_log")
            os.makedirs(base, exist_ok=True)
            kw.update({"hora": time.strftime("%Y%m%d_%H%M%S"),
                       "cuenta": str(getattr(self.ctrl, "name", ""))})
            with open(os.path.join(base, "cosmomante_log.jsonl"), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(kw) + "\n")
        except Exception:                                   # noqa: BLE001
            pass

    # ----------------------------------------------------------- acciones --
    def _k(self, img):
        return img.shape[1] / 1600.0

    def _tap(self, img, xy):
        k = self._k(img)
        self.ctrl.tap((int(xy[0] * k), int(xy[1] * k)))

    def _dialogo_abierto(self, img) -> bool:
        return localizar(img, "inicio")[0] < 0.75

    def _quitar_avisos(self, maximo=12):
        """Cierra recompensas y animaciones hasta ver el tablero estable."""
        estable = 0
        for _ in range(maximo):
            time.sleep(1.5)
            img = self.cap("aviso")
            if self._en_tablero(img):
                estable += 1
                if estable >= 2:
                    return True
            else:
                estable = 0
                self.ctrl.tap((img.shape[1] // 2, int(img.shape[0] * 0.15)))
        return False

    def _pulsar_multiplicador(self, clave) -> bool:
        img = self.cap("tablero")
        if not self._en_tablero(img):
            return False
        self._tap(img, self.ICONOS[clave])
        time.sleep(1.3)
        img = self.cap("dialogo")
        if not self._dialogo_abierto(img):
            return False                  # sin existencias: no se abre dialogo
        self._tap(img, self.USAR_MULT)
        time.sleep(1.8)
        ok = self._en_tablero(self.cap("tablero"))
        if ok:
            if clave == "dorado":
                self._magnetos = max(0, (self._magnetos or 0) - 1)
            elif clave == "x2":
                self._x2 = max(0, (self._x2 or 0) - 1)
        return ok

    def _dado_remoto(self, n) -> bool:
        img = self.cap("tablero")
        if not self._en_tablero(img):
            return False
        icono = "azul" if (self._remotos is not None and self._remotos <= 0) else "remoto"
        if icono == "azul" and self._azules is not None and self._azules <= 0:
            self._sin_dados = True
            return False
        self._tap(img, self.ICONOS[icono])
        time.sleep(1.3)
        img = self.cap("dialogo")
        if not self._dialogo_abierto(img):
            if icono == "remoto":
                self._remotos = 0
                self._sin_remoto = True
                return self._dado_remoto(n)      # probar con el dado azul
            self._sin_dados = True
            return False
        self._tap(img, (self.NUM_X[n], self.NUM_Y))
        time.sleep(0.8)
        self._tap(img, self.USAR_REMOTO)
        time.sleep(5.0)                   # la baliza se mueve
        if icono == "remoto" and self._remotos is not None:
            self._remotos = max(0, self._remotos - 1)
        elif icono == "azul" and self._azules is not None:
            self._azules = max(0, self._azules - 1)
        return self._quitar_avisos()

    def _ejecutar(self, j) -> bool:
        """Imanes y x2 primero (cada uno con su "Usar"), despues el dado remoto."""
        if j["dorado"] and not self._pulsar_multiplicador("dorado"):
            self.log("  No he podido activar el iman dorado; no sigo con esta jugada.")
            return False
        if j["x2"] and not self._pulsar_multiplicador("x2"):
            self.log("  No he podido activar el x2; no sigo con esta jugada.")
            return False
        return self._dado_remoto(j["dado"])

    def _mapa(self):
        res = self.leer_nivel()
        if not res or not res[1]:
            return None
        self._mapa_mem = res[0]               # se guarda con la posicion
        return res[0]

    @staticmethod
    def _recogidas(mapa):
        return {i for i, (_, r) in mapa.items() if r}

    # ------------------------------------------------------------ posicion --
    def _calibrar(self, mapa):
        """Devuelve (pos, mapa) o (None, mapa). NUNCA gasta dados para averiguar
        donde esta la baliza: usa la memoria (posicion y casillas recogidas del
        ultimo estado conocido) y deduce la casilla nueva comparando lo recogido.
        Si no hay forma segura, no juega y guarda una captura del tablero."""
        rec = self._recogidas(mapa)
        guardado = self._leer_pos()
        previo = set(guardado.get("rec", []))
        if guardado.get("pos") is not None and previo == rec:
            return guardado["pos"], mapa
        if not rec:
            return 0, mapa                    # nivel recien empezado
        if guardado.get("pos") is not None or previo:
            nuevas = rec - previo
            ant = guardado.get("pos")
            if ant is None:
                ant = guardado.get("pos_antes")
            # una casilla nueva, o varias todas por delante del ultimo punto conocido
            # (tiradas seguidas sin vuelta): la baliza esta en la mas avanzada
            if previo <= rec and nuevas and (len(nuevas) == 1 or (ant is not None and min(nuevas) > ant)):
                pos = max(nuevas)               # tiradas seguidas: la ultima casilla nueva
                self.log(f"  Baliza deducida de la memoria: casilla {pos}.")
                self._guardar_pos(pos, rec)
                self._anotar(etiqueta="deducido", pos=pos)
                return pos, mapa
        # vista: icono bajo la baliza (la camara siempre la centra) y vecinas
        tipos = {int(i): t for i, t in (guardado.get("tipos") or {}).items()}
        tipos.update(getattr(self, "_tipos_mem", {}) or {})
        img = self.cap("tablero")
        cand = []
        if tipos and self._en_tablero(img):
            obs = cm.ver_alrededor(img)
            cand = cm.localizar_baliza(mapa, tipos, obs)
            self.log(f"  Icono bajo la baliza: {obs and obs['centro']}; casillas posibles: {cand}.")
            nuevas = rec - previo
            if previo and previo <= rec and nuevas and len(set(cand) & nuevas) >= 1:
                cand = sorted(set(cand) & nuevas)         # memoria + vista
        if len(cand) == 1:
            pos = cand[0]
            self.log(f"  Baliza reconocida en el tablero: casilla {pos}.")
            self._guardar_pos(pos, rec)
            self._anotar(etiqueta="reconocido", pos=pos)
            return pos, mapa
        self._pos_pendiente = True
        self._guardar_pos(None, rec)          # recuerda lo recogido: tras las tiradas se deduce
        try:
            self._registrar("baliza_desconocida", img)
        except Exception:                                   # noqa: BLE001
            pass
        self._anotar(etiqueta="baliza_desconocida", recogidas=sorted(rec))
        return None, mapa

    # -------------------------------------------------------------- jugar --
    def jugar(self, modo_nivel=False):
        mapa = self._mapa()
        if mapa is None:
            self.log("  No he podido leer el mapa del nivel; no uso multiplicadores.")
            return 0
        pos, mapa = self._calibrar(mapa)
        if pos is None:
            self.log("  No he podido saber donde esta la baliza; no uso multiplicadores.")
            return 0
        hechas = 0
        while hechas < self.JUGADAS_MAX and not self.parado() and not self._sin_dados:
            if (self._remotos is not None or self._azules is not None) and \
                    (self._remotos or 0) + (self._azules or 0) <= 0:
                break
            if modo_nivel:
                j = self._plan_nivel(mapa, pos, self._magnetos or 0)
            else:
                j = cm.plan(mapa, pos, 99, 99, 99)
            if not j:
                break
            q = (pos + j["dado"]) % cm.N_CASILLAS
            self.log(f"  Jugada: desde {pos}, dado remoto {j['dado']}"
                     f"{' + iman dorado' if j['dorado'] else ''}{' + x2' if j['x2'] else ''} "
                     f"(valor {j['valor']}).")
            self.status["estado"] = f"jugada {hechas + 1}"
            antes = self._recogidas(mapa)
            if not self._ejecutar(j):
                break
            nuevo = self._mapa()
            if nuevo is None:
                break
            ahora = self._recogidas(nuevo)
            ok = q in ahora
            self._anotar(etiqueta="jugada", desde=pos, hasta=q, jugada=j, ok=ok,
                         nuevas=sorted(ahora - antes))
            hechas += 1
            self.status["jugadas"] += 1
            if not ok:
                self.log(f"  La baliza no ha caido donde esperaba ({q}); paro las jugadas.")
                self._guardar_pos(None, ahora)
                return hechas
            pos, mapa = q, nuevo
            self._guardar_pos(pos, ahora)
            if self.ASCENDER and self.puede_ascender(self.cap("tablero")):
                self.ascender()
                return hechas
        return hechas

    # ----------------------------------------------------------- ascender --
    def puede_ascender(self, img) -> bool:
        k = self._k(img)
        r = img[int(740 * k):int(870 * k), int(1095 * k):int(1195 * k)].astype(int)
        b, g, rr = r[..., 0], r[..., 1], r[..., 2]
        # parpadea: apagado <= 0.05, medio brillo ~0.08, encendido mucho mas
        return float(((rr > 180) & (g > 110) & (b < 110)).mean()) > 0.06

    def nivel_actual(self, img) -> int | None:
        """Nivel de Cosmomante que muestra el panel de Ascender.
        None si no se puede leer con seguridad."""
        if img is None:
            return None
        h, w = img.shape[:2]
        kx, ky = w / 1600.0, h / 900.0
        nums = leer_cifras(img, (1240 * kx, 455 * ky, 1380 * kx, 515 * ky), v_min=140)
        return nums[0] if nums else None

    def estado_nivel(self, img) -> dict | None:
        """Nivel, puntos y casillas recogidas del panel de Ascender."""
        if img is None:
            return None
        h, w = img.shape[:2]
        kx, ky = w / 1600.0, h / 900.0
        nivel = self.nivel_actual(img)
        puntos = leer_cifras(img, (1180 * kx, 515 * ky, 1420 * kx, 570 * ky), v_min=140)
        celdas = leer_cifras(img, (1180 * kx, 620 * ky, 1420 * kx, 660 * ky), v_min=140)
        est = {
            "nivel": nivel,
            "puntos": puntos[0] if len(puntos) >= 1 else None,
            "puntos_total": puntos[1] if len(puntos) >= 2 else 200,
            "celdas": celdas[0] if len(celdas) >= 1 else None,
            "celdas_total": celdas[1] if len(celdas) >= 2 else 50,
        }
        if est["puntos"] is None and est["celdas"] is not None:
            est["puntos"] = est["celdas"] * 10
        if nivel is None:
            return None
        self.status["nivel"] = nivel
        self._estado_nivel = est
        return est

    def recursos(self, img) -> dict | None:
        """Dados y objetos disponibles bajo los iconos del tablero."""
        if img is None:
            return None
        h, w = img.shape[:2]
        kx, ky = w / 1600.0, h / 900.0
        salida = {}
        for nombre, x in (("remoto", 87), ("azul", 214),
                          ("dorado", 335), ("x2", 462)):
            nums = leer_cifras(img, (int((x - 40) * kx), int(850 * ky),
                                     int((x + 40) * kx), int(880 * ky)), v_min=140)
            salida[nombre] = nums[0] if nums else None
        salida["normales"] = self.disponibles(img)
        salida["free"] = 1 if localizar(img, "free")[0] >= 0.75 else 0
        salida["fiable"] = (salida["normales"] is not None and
                            all(salida[n] is not None for n in
                                ("remoto", "azul", "dorado", "x2")))
        return salida

    def leer_estado_nivel(self):
        """Abre el panel de Ascender solo para leer nivel/progreso y lo cierra."""
        img = self.cap("tablero")
        if not self._en_tablero(img):
            return None
        p, c, _ = localizar(img, "inicio")
        if p < 0.75:
            return None
        k = self._k(img)
        self.ctrl.tap((int(c[0] - 335 * k), int(c[1] - 20 * k)))
        time.sleep(3.0)
        panel = self.cap("panel_estado")
        if not cm.filas_panel(panel):
            self.log("  No reconozco el panel de Ascender.")
            return None
        est = self.estado_nivel(panel)
        self._cerrar_panel(panel)
        return est

    def probabilidad_nivel6(self, estado, recursos, simulaciones=400) -> float | None:
        """Probabilidad estimada de llegar al nivel 6 con los dados actuales.

        Usa los remotos/azules primero (se puede elegir el numero), los
        imanes suman 5 casillas y los normales son aleatorios (0,65 por
        tirada). Devuelve None si no hay datos fiables.
        """
        if not estado or not recursos or not recursos.get("fiable"):
            return None
        nivel = estado.get("nivel")
        if nivel is None:
            return None
        if nivel >= self.NIVEL_MAX:
            return 1.0
        puntos = estado.get("puntos")
        total = estado.get("puntos_total") or 200
        celdas = estado.get("celdas")
        por_celda = (puntos / celdas) if puntos and celdas else 10.0
        # En el juego la barra sube de nivel: 200, 300... Se estima que cada
        # nivel nuevo pide 100 puntos mas. Asi el calculo es prudente y no
        # gasta dados si no hay margen claro.
        crecimiento = 100
        faltan_puntos = max(0, total - (puntos or 0))
        for k in range(nivel + 1, self.NIVEL_MAX):
            faltan_puntos += total + crecimiento * (k - nivel)
        necesarias = max(0, math.ceil(faltan_puntos / max(1.0, por_celda)))
        if necesarias <= 0:
            return 1.0
        rem = recursos.get("remoto")
        azu = recursos.get("azul")
        nor = recursos.get("normales")
        mag = recursos.get("dorado")
        if rem is None or azu is None or nor is None or mag is None:
            return None
        r = int(rem + azu + (recursos.get("free") or 0))
        n = int(nor)
        m = int(mag)
        self._est_necesarias = necesarias
        self._est_remotos = r
        self._est_normales = n
        self._est_magnetos = m
        if r + n <= 0:
            return 0.0
        aciertos = 0
        for _ in range(max(50, simulaciones)):
            falta, rr, nn, mm = necesarias, r, n, m
            while falta > 0:
                if rr > 0:
                    rr -= 1
                    if mm > 0:
                        mm -= 1
                        falta -= 5
                    else:
                        falta -= 1
                elif nn > 0:
                    nn -= 1
                    if mm > 0:
                        mm -= 1
                        falta -= 5
                    elif random.random() < 0.65:
                        falta -= 1
                else:
                    break
            if falta <= 0:
                aciertos += 1
        return aciertos / max(50, simulaciones)

    @staticmethod
    def _plan_nivel(mapa, pos, magnetos=0):
        """Jugada que mas casillas nuevas recoge (para llenar el nivel)."""
        mejor = None
        for d in range(1, 7):
            q = (pos + d) % cm.N_CASILLAS
            if q == 0:
                continue
            aterriza = not mapa.get(q, (None, True))[1]
            if not aterriza:
                continue            # la baliza tiene que caer en casilla nueva
            celdas = [(q + k) % cm.N_CASILLAS for k in range(-2, 3)]
            nuevas = sum(1 for c in celdas
                         if c != 0 and not mapa.get(c, (None, True))[1])
            usar = magnetos > 0 and nuevas >= 2
            valor = nuevas if usar else 1
            if mejor is None or valor > mejor["valor"]:
                mejor = {"dado": d, "dorado": usar, "x2": False, "valor": valor}
        return mejor

    def _cerrar_panel(self, img=None):
        if img is None:
            img = self.cap("panel")
        k = self._k(img)
        self.ctrl.tap((int(1558 * k), int(45 * k)))
        time.sleep(1.8)

    def ascender(self) -> int:
        """Sube de nivel hasta NIVEL_MAX (6). Devuelve los niveles subidos.

        Lee el nivel en el panel antes y despues de cada Ascender. Si no
        cambia, para: el boton no estaba disponible o hace falta confirmar."""
        img = self.cap("tablero")
        if not self._en_tablero(img):
            return 0
        if not self.puede_ascender(img):
            # el boton parpadea cuando se puede ascender: se mira varias veces
            for _ in range(8):
                time.sleep(0.4)
                img = self.cap("tablero")
                if self._en_tablero(img) and self.puede_ascender(img):
                    break
            else:
                self.log("  El boton Ascender no esta iluminado; no asciendo.")
                return 0
        # abrir el panel de Ascender con su icono del tablero
        self._tap(img, self.BOTON_ASCENDER)
        time.sleep(3.0)
        panel = self.cap("panel_ascender")
        if not cm.filas_panel(panel):
            self.log("  No reconozco el panel de Ascender; no asciendo.")
            if self._dialogo_abierto(panel):
                self._registrar("ascender_panel", panel)
            return 0
        subidos = 0
        for _ in range(self.NIVEL_MAX):
            if self.parado():
                break
            nivel = self.nivel_actual(panel)
            if nivel is None:
                self.log("  No he podido leer el nivel de Cosmomante; no asciendo.")
                self._registrar("ascender_nivel", panel)
                break
            self.status["nivel"] = nivel
            if nivel >= self.NIVEL_MAX:
                self.log(f"  Nivel {nivel}: ya esta en el objetivo ({self.NIVEL_MAX}).")
                break
            self.log(f"  Nivel {nivel}: pulso Ascender.")
            self._tap(panel, self.BOTON_ASCENDER_PANEL)
            time.sleep(3.0)
            nuevo = self.cap("ascender")
            if not cm.filas_panel(nuevo):
                # Puede salir una confirmacion (OK/Continuar) o cerrarse el panel.
                if self._dialogo_abierto(nuevo):
                    self._registrar("ascender_dialogo", nuevo)
                    for nombre in ("ok", "continuar"):
                        p, c, _ = localizar(nuevo, nombre)
                        if p >= 0.75:
                            self.log(f"  Confirmo el ascenso con '{nombre}'.")
                            self.ctrl.tap(c)
                            time.sleep(2.5)
                            break
                    nuevo = self.cap("ascender")
                if not cm.filas_panel(nuevo):
                    # se cerro: reabrir para leer el nivel nuevo
                    time.sleep(1.0)
                    base = self.cap("tablero")
                    if not self._en_tablero(base):
                        break
                    self._tap(base, self.BOTON_ASCENDER)
                    time.sleep(2.5)
                    nuevo = self.cap("panel_ascender")
                    if not cm.filas_panel(nuevo):
                        break
            nivel2 = self.nivel_actual(nuevo)
            if nivel2 is None or nivel2 <= nivel:
                self.log(f"  El nivel no ha subido (sigue en {nivel}); paro.")
                self._registrar("ascender_sin_cambio", nuevo)
                panel = nuevo
                break
            subidos += nivel2 - nivel
            self.status["ascensos"] = self.status.get("ascensos", 0) + (nivel2 - nivel)
            self.status["nivel"] = nivel2
            self.log(f"  Ascendido a nivel {nivel2}.")
            panel = nuevo
        if cm.filas_panel(panel):
            self._cerrar_panel(panel)
        self._quitar_avisos()
        if subidos:
            # nivel nuevo: el mapa y la posicion del anterior ya no valen
            self._mapa_mem = {}
            self._tipos_mem = {}
            self._pos_pendiente = False
            self._guardar_pos(0, [])
        return subidos


# Nombre antiguo, para que los ajustes y las llamadas de antes sigan funcionando.
CosmomanteEstrategia = Cosmomante
