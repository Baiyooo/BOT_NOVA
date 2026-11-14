"""Ballenas de eter: invocar, matarlas con dos cuentas a la vez y recoger
las gemas que sueltan (aprendido en vivo el 5 nov 2026).

Tanda (TANDA_MAX = 3 ballenas, sin pasar del tope del dia): invocar todos los
señuelos seguidos > matarlas una a una (en 3D, cada una con sus reintentos) >
llamar a las flotas a la estacion (LlamarFlotas, siempre) > SOLO entonces
recoger, en 2D con el zoom del mapa: gemas (iconos 2D; etiquetas 3D solo de
respaldo) y escombros de todos los puntos de muerte, con los drones libres del
contador comun > volver a 3D. Las ballenas nuestras que queden vivas se guardan
(posicion + hora, ~30 min) y la siguiente tanda las ataca primero; el tope del
dia cuenta solo las que mueren.

Ciclo:
  1. La cuenta que invoca usa 2 Señuelos de eter V, desde la vista del
     SISTEMA (la barra de arriba tambien sale alli; no se pasa por la base):
     Almacen (barra de arriba) > Almacen (abajo) > Objeto comun > Señuelo de
     eter V (suele ser el 2.º objeto) > Usar. El juego confirma "Ballena de
     eter invocada correctamente, cantidad actual N/10".
  2. Cada ballena se ataca con las DOS cuentas a la vez (asi el daño es
     parecido y las dos sacan la recompensa maxima). En la vista general del
     sistema la ballena lleva un circulo rojo; al tocarla sale "Ballena de
     eter · Fuerza N" con Atacar / Ataque de grupo / Ver / Marcador.
     Atacar > "Elige tu flota": se elige la primera tarjeta con cabecera
     "Salto" o "Base" (nunca "Moviendose" ni "Estabilizando"). Una flota en
     "Base" viaja (unos 30 s) y una en "Salto" llega casi al momento: la que
     viaja sale primero y la otra espera a que le falten ~3 s. Si una ballena
     no se mata a la primera se reintenta (3 veces): el reintento va en la
     sincronizacion para que la otra cuenta repita el ataque, y la «Flota
     aliada» del panel no corta el ataque cuando es la otra cuenta de la
     pareja (se sabe porque ya lanzo su ataque a esa ballena).
  3. Muertas las dos, se recogen las gemas (organica, gamma, sagrada): boton
     redondo de la derecha > Recursos (filtro con las gemas marcadas) > tocar
     una gema > "Gema ..." > Recoger (el robot sale solo). Se reparten a
     partes iguales entre las dos cuentas (la que invoca coge una mas si son
     impares), sin pasar de sus robots (6 por defecto; se ajusta en Ajustes).
  4. Se espera la recogida (5 min + llegada del robot) y se repite, sin
     pasar del tope de ballenas al dia que se pone en Ajustes.

Modo (Ajustes > Ballenas, ver cerebro/config_ballenas.py): con pareja (una
invoca y la otra apoya; sin la otra cuenta no se gasta ningun señuelo) o, si el
usuario lo elige, SOLA (sola=True): la cuenta invoca, ataca con su flota sin
esperar el «listo» de nadie, espera la muerte y recoge TODAS las gemas con
todos sus drones. En modo sola cualquier «Flota aliada» del panel es de otro
jugador, asi que no se ataca esa ballena. Tambien son ajustes: robots, tope del
dia, grupo de batalla 2, reparar y recoger gemas.
Con pareja, las cuentas se coordinan con archivos en
%LOCALAPPDATA%\\NovaBot\\ballenas (cada una escribe solo el suyo). Nunca se
pulsa nada de pago: ni "Llamar a todos", ni comprar señuelos (se usan los que
hay), ni gastar GEC.
"""
from __future__ import annotations

import time

from vision import ocr
from tareas.recompensas import Recompensas
from tareas.ballenas.atacar import _Atacar
from tareas.ballenas.deteccion import BOTON_LADO
from tareas.ballenas.invocar import _Invocar
from tareas.ballenas.recoger import _Recoger
from tareas.ballenas.sync import Sync, puerto


ESPERA_RECOGIDA = 6 * 60          # 5 min de recogida + llegada del robot
TANDA_MAX = 3                     # ballenas por tanda: se invocan, se matan y luego se recoge todo


def cerca(a, b, radio=60) -> bool:
    """Dos posiciones de ballena en pantalla son la misma."""
    return abs(a[0] - b[0]) < radio and abs(a[1] - b[1]) < radio


class Ballenas(_Invocar, _Atacar, _Recoger, Recompensas):
    NOMBRE = "Ballenas de éter"
    TANDA_MAX = TANDA_MAX

    def __init__(self, ctrl, log=None, stop=None, diag=True, lider="", apoyo="",
                 robots=None, tope_dia=2, hechas_hoy=0, preparar_grupo=True, grupo_actual=None,
                 sola=False, reparar=True, con_gemas=True, con_escombros=True, minimos=None):
        super().__init__(ctrl, log=log, stop=stop, diag=diag)
        self.con_escombros = con_escombros
        # minimo por tipo de escombro de ballena (unidades); ver config_ballenas.minimos_unidades
        self.minimos = dict(minimos) if minimos else {"mineral": 18_000_000, "cristal": 2_000_000,
                                                      "aleacion": 1_000_000}
        self.preparar_grupo = preparar_grupo
        self.reparar = reparar
        self.con_gemas = con_gemas
        self.grupo_actual = grupo_actual
        self.yo = puerto(getattr(ctrl, "name", "inst"))
        #  sola: esta cuenta invoca, mata y recoge sin otra cuenta (no hay pareja,
        #  no se espera a nadie y toda «Flota aliada» del panel es de otro jugador)
        self.sola = bool(sola)
        self.lider = self.sola or self.yo == str(lider)
        self.otro = "" if self.sola else (str(apoyo) if self.lider else str(lider))
        self.sync = Sync(self.yo, self.otro)
        self.robots = 6 if robots is None else int(robots)      # 0 = no manda robots
        self.tope_dia, self.hechas_hoy = int(tope_dia), int(hechas_hoy)
        self.status = {"estado": "en espera", "ballenas": 0, "gemas": 0, "recogidas": 0,
                       "senuelos": 0}

    # ------------------------------------------------------------ texto --
    def _ocr(self, etiqueta, zona=None):
        img = self.cap(etiqueta)
        return img, ocr.leer(img, zona)

    @staticmethod
    def _busca(items, *frases, zona=None, w=1600, h=900):
        return ocr.buscar(items, *frases, zona=zona, w=w, h=h)

    def _toca(self, frases, etiqueta, zona=None, espera=2.0, intentos=3):
        """Busca un texto (OCR) y lo toca. Devuelve el texto o None."""
        if isinstance(frases, str):
            frases = (frases,)
        for _ in range(intentos):
            if self.parado():
                return None
            img, items = self._ocr(etiqueta)
            h, w = img.shape[:2]
            d = self._busca(items, *frases, zona=zona, w=w, h=h)
            if d:
                self.ctrl.tap(d["centro"])
                time.sleep(espera)
                return d
            time.sleep(1.0)
        return None

    def _espera_texto(self, frases, segundos, etiqueta, zona=None):
        if isinstance(frases, str):
            frases = (frases,)
        fin = time.time() + segundos
        while time.time() < fin and not self.parado():
            img, items = self._ocr(etiqueta, zona)
            h, w = img.shape[:2]
            d = self._busca(items, *frases, zona=zona, w=w, h=h)
            if d:
                return img, items, d
            time.sleep(0.4)
        return None

    def _atras_juego(self, veces=1):
        """Boton "Atras" de arriba a la izquierda (nunca la tecla de Android
        en el mapa: abre "¿Seguro que quieres salir?")."""
        for _ in range(veces):
            d = self._toca(("atras",), "atras", zona=(0, 0, 0.2, 0.15), espera=1.6, intentos=2)
            if d is None:
                return False
        return True

    def _quitar_salir(self):
        """Si ha salido "¿Seguro que quieres salir?", pulsa No."""
        img, items = self._ocr("salir")
        if self._busca(items, "seguro que quieres salir"):
            d = self._busca(items, "no")
            if d:
                self.ctrl.tap(d["centro"])
                time.sleep(1.2)

    # zonas de la vista con zoom (1600x900): rotulo «Ballena de éter / Fuerza»
    # a la izquierda del centro, y el menu (Atacar, Ataque de grupo...) a la derecha
    ZONA_ROTULO = (0.1, 0.3, 0.55, 0.62)
    ZONA_MENU = (0.55, 0.12, 0.98, 0.8)

    def _atras_rapido(self):
        """«Atrás» de arriba a la izquierda en su sitio fijo (sin leer)."""
        img, items = self._ocr("atras", (0, 0, 0.15, 0.1))
        h, w = img.shape[:2]
        if not self._busca(items, "atras", w=w, h=h):
            return False                         # ya estoy en la vista del sistema
        self.ctrl.tap((int(w * 112 / 1600), int(h * 37 / 900)))
        time.sleep(1.2)
        return True

    # -------------------------------------------------------- ciclo --
    def _preparar(self):
        """Antes de las ballenas: flotas a casa, reparar
        y cargar el grupo de batalla 2 («PvE PirateS», las Poseidón)."""
        if not self.preparar_grupo:
            return
        # reparar y cargar el PVE al EMPEZAR una tanda de
        # ballenas (y reparar al acabarla), no antes de cada ballena. Una tanda
        # sigue mientras se encadenan ballenas (menos de 20 min entre una y
        # otra) y no se ha cambiado de grupo (piratas de sigilo = grupo 1)
        yo = self.sync.leer()
        inv = max(yo.get("invocada_t", 0), self.sync.del_otro().get("invocada_t", 0))
        if inv and 20 * 60 < time.time() - inv < 30 * 60:
            self.log("  La ballena desaparece en menos de 10 min: voy sin preparar.")
            return
        if (yo.get("prep_t2") and time.time() - max(yo.get("prep_t2", 0), yo.get("ult_ballena", 0)) < 1200
                and not yo.get("tanda_fin") and self.grupo_actual != 1):
            return
        try:
            from tareas.grupo import preparar
            self.status["estado"] = "preparando el grupo de batalla"
            if preparar(self.ctrl, log=self._log, stop=self.stop, grupo=2, reparar=self.reparar):
                self.sync.escribir(prep_t2=time.time(), tanda_fin=False)
        except Exception as e:                                # noqa: BLE001
            self.log(f"  No he podido preparar el grupo ({e}); sigo.")

    def _reparar_final(self):
        """Fin de la tanda: reparar (con aceleraciones de reparacion)."""
        self.sync.escribir(tanda_fin=True)
        if not self.reparar:
            return
        try:
            from tareas.grupo import solo_reparar
            self.status["estado"] = "reparando al acabar las ballenas"
            self.log("Ballenas: tanda del día acabada; reparo las naves.")
            solo_reparar(self.ctrl, log=self._log, stop=self.stop)
        except Exception as e:                                # noqa: BLE001
            self.log(f"  No he podido reparar al final ({e}).")

    def ciclo_lider(self) -> int:
        """Lo hace la cuenta que invoca: UNA TANDA de hasta TANDA_MAX ballenas
        (sin pasar del tope del dia): invoca todos los señuelos seguidos, las
        mata una a una y SOLO cuando estan todas muertas recoge las gemas y los
        escombros de todos los puntos de muerte. Devuelve las muertas."""
        n = min(self.TANDA_MAX, max(0, self.tope_dia - self.hechas_hoy))
        if n <= 0:
            self.log("Ballenas: tope del día alcanzado.")
            return 0
        self._muertes, self._img_muerte = [], None       # los puntos de muerte de ESTA tanda
        self._preparar()
        ciclo = time.strftime("%H%M%S")
        # 0) con pareja: avisar a la otra cuenta y esperar a que este libre (sin
        #    ella no se gasta ningun señuelo). Sola: no se espera a nadie.
        if not self.sola:
            self.status["estado"] = "esperando a la otra cuenta"
            self.sync.escribir(ciclo=ciclo, fase="pedido", gemas=[], muertas=0)
            self.log(f"Ballenas: aviso a la cuenta {self.otro} y espero a que esté libre.")
            t_pedido = time.time()

            def listo(d):
                if d.get("presente") == ciclo:
                    return True
                # la otra cuenta tambien esta pidiendo (las dos quieren invocar):
                # cede la que pidio despues, para que no se esperen la una a la otra
                if d.get("fase") == "pedido" and d.get("t_pedido", 1e18) < t_pedido:
                    return True
                return False

            self.sync.escribir(t_pedido=t_pedido)
            d = self.sync.esperar(listo, 900, self.parado)
            if d is not None and d.get("presente") != ciclo:
                self.log("Ballenas: la otra cuenta también va a invocar; la ayudo yo primero.")
                self.sync.escribir(fase="cancelado")
                return -1
            if d is None:
                self.log("Ballenas: la otra cuenta no responde; lo dejo para luego.")
                self.sync.escribir(fase="cancelado")
                return -1
        self.status["estado"] = "invocando ballenas"
        self._vista_matar()                              # 3D y zoom normal antes de buscar ballenas
        # las ballenas que YA hay son de otros jugadores (aliados): nunca se
        # tocan, SALVO las nuestras que quedaron vivas de una tanda anterior (se
        # recuerdan con su posicion y hora de invocacion: duran ~30 min). La
        # nueva es la que aparece despues de invocar.
        antes = self.ver_ballenas()
        propias = self._pendientes_propias(antes)[:n]
        if propias:
            self.log(f"Ballenas: sigue(n) ahí {len(propias)} ballena(s) mía(s) invocada(s) antes "
                     "(menos de 30 min): voy a por ellas primero.")
        if len(antes) > len(propias):
            self.log(f"Ballenas: ya hay {len(antes) - len(propias)} ballena(s) de otros jugadores; no las toco.")
        vivas = [tuple(p["pos"]) for p in propias]
        pend = [dict(p) for p in propias]
        faltan = n - len(propias)
        if faltan > 0:
            hechas = self.invocar(faltan)
            motivo = getattr(self, "motivo_invocar", "")
            self.log(f"Ballenas: {hechas} invocada(s)" + (f" ({motivo})." if not hechas and motivo else "."))
            nuevas = []
            if hechas:
                t_inv = time.time()
                self.sync.escribir(invocada_t=t_inv)
                for _ in range(3):                    # puede tardar en aparecer
                    self.mi_sistema()
                    time.sleep(2)
                    nuevas = [v for v in self.ver_ballenas() if not any(cerca(v, a) for a in antes)]
                    if nuevas:
                        break
                if len(nuevas) > hechas:
                    self.log("  Han salido más ballenas nuevas que señuelos usados: "
                             "alguna puede ser de otro jugador.")
                nuevas = nuevas[:hechas]         # solo las que se han invocado
                if not nuevas:
                    self.log(f"  Se han invocado {hechas} pero no veo ninguna nueva en el mapa.")
            vivas += [tuple(v) for v in nuevas]
            pend += [{"pos": list(v), "t": t_inv} for v in nuevas]
        vivas = vivas[:n]
        if not vivas:
            self.log("Ballenas: no distingo cuál es la mía (no ha salido ninguna nueva); "
                     "no ataco ninguna de otros.")
            self.sync.escribir(fase="cancelado")
            return 0
        # lo que se invoca queda guardado hasta que muera (cuenta para el tope solo al morir)
        self._pend = pend[:len(vivas)]
        self.sync.escribir(mi_ballena=list(vivas[0]), pendientes=self._pend,
                           con_pendientes=bool(propias))
        self.sync.escribir(ciclo=ciclo, ballenas=[list(p) for p in vivas], fase="atacar",
                           gemas=[], muertas=0)
        muertas = 0
        try:
            for i, pos in enumerate(vivas):
                if self.parado():
                    break
                self.status["estado"] = f"atacando ballena {i + 1}"
                muerta = False
                for intento in range(3):          # reintenta la misma ballena
                    if self.parado():
                        break
                    self.sync.escribir(objetivo=i, intento=intento)
                    if self.atacar_ballena(ciclo, i, pos, intento=intento):
                        self.mi_sistema()
                        # el ataque ha salido: nunca se vuelve a atacar una ballena
                        # que ya estan atacando nuestras flotas; solo se espera mas
                        muerta = self.esperar_muerte(pos) or self.esperar_muerte(pos, maximo=300)
                        if muerta:
                            self._muerte = pos
                            self._muertes.append(tuple(pos))
                            self._img_muerte = self.ctrl.capture()   # vista del sistema al morir (img_ref)
                            self._registrar_muerte(pos, self._img_muerte)   # para «escombros» (~30 min, con huella)
                            self.sync.escribir(ult_ballena=time.time())
                        else:
                            self.log(f"  La ballena {i + 1} no muere tras el ataque; la dejo.")
                        break
                    # la vista puede haber cambiado: donde esta ahora la ballena
                    self.mi_sistema()
                    vivas_ahora = self.ver_ballenas()
                    if vivas_ahora:
                        pos = min(vivas_ahora, key=lambda v: (v[0] - pos[0]) ** 2 + (v[1] - pos[1]) ** 2)
                    if intento < 2:
                        self.log(f"  Ballena {i + 1} sin matar; reintento ({intento + 2}/3).")
                if i < len(self._pend):
                    self._pend[i]["pos"] = list(pos)
                    self._pend[i]["muerta"] = bool(muerta)
                if muerta:
                    muertas += 1
                    self.status["ballenas"] += 1
                    self.log(f"  Ballena {i + 1} muerta.")
                else:
                    self.log(f"  La ballena {i + 1} queda viva: la recuerdo para la siguiente tanda.")
                self._guardar_pendientes()
                self.sync.escribir(muertas=muertas)
        finally:
            # tanda acabada, o cortada / ballena abandonada: las flotas vuelven a la estacion
            # (salvo si se ha pulsado PARAR), antes de pasar a 2D a recoger
            self._llamar_flotas()
        # ya estan todas muertas (o dadas por perdidas): ahora, a recoger
        # 1) las gemas, por TODO el mapa (salen al azar); con pareja, un solo reparto
        total = self._gemas_ciclo(lider=True, muertas=muertas) if self.con_gemas else 0
        # 2) los escombros, solo junto a donde han muerto las ballenas de la tanda
        if muertas:
            self.recoger_escombros_muerte()
        final = self.hechas_hoy + muertas >= self.tope_dia
        self.sync.escribir(fase="hecho", fin=time.time(), final=final)
        self.log(f"Ballenas: {muertas} muerta(s), {total} gema(s) a recoger.")
        if final and muertas:
            self._reparar_final()
        return muertas

    def _modo(self, quiero: str) -> bool:
        """Cambia la vista del sistema a '2d' o '3d' con el boton del panel
        lateral (2D / Ayuda / Recursos). El rotulo dice el modo al que pasa
        («2D» = ahora estoy en 3D). El lector lee «2D» como «20»."""
        def rotulo(items):
            for d in items:
                t = ocr.normal(d["texto"]).replace(" ", "").replace("o", "0")
                t = "".join(ch for ch in t if ch.isalnum())
                if t[:2] in ("2d", "20"):
                    return "2d", d
                if t[:2] in ("3d", "30"):
                    return "3d", d
            return None, None
        for intento in range(2):
            img, items = self._ocr("modo", (0.7, 0.55, 1, 0.78))
            h, w = img.shape[:2]
            r, d = rotulo(items)
            abierto = any("ayuda" in ocr.normal(x["texto"]) or "recursos" in ocr.normal(x["texto"])
                          for x in items)
            if r is not None and r != quiero:
                return True                       # ya estoy en el modo pedido
            if r == quiero:
                # icono encima del rotulo (1600x900: rotulo y=573, icono y=622?) -> el icono
                # esta DEBAJO del rotulo en este panel
                self.ctrl.tap((d["centro"][0], d["centro"][1] + int(h * 0.055)))
                time.sleep(1.5)
                return True
            if not abierto and intento == 0:
                # desplegar el panel lateral (boton redondo de la derecha)
                self.ctrl.tap(BOTON_LADO)
                time.sleep(1.2)
        return False

    VIDA_BALLENA = 30 * 60            # una ballena invocada dura ~30 min

    def _guardar_pendientes(self):
        """Las ballenas nuestras que siguen vivas (posicion + hora de invocacion),
        en el estado de esta cuenta: la siguiente tanda las ataca primero."""
        vivas = [{"pos": p["pos"], "t": p["t"]} for p in getattr(self, "_pend", []) if not p.get("muerta")]
        self.sync.escribir(pendientes=vivas)

    def _pendientes_propias(self, antes) -> list[dict]:
        """Las ballenas que invoque yo y siguen en el mapa: las guardadas (menos
        de 30 min) que coinciden con alguna de las que se ven ahora. Se ataca
        con su posicion actual; nunca una de otro jugador."""
        sd = self.sync.leer()
        lista = sd.get("pendientes")
        if lista is None:                          # estado de una version anterior
            mia = sd.get("mi_ballena")
            lista = [{"pos": mia, "t": sd.get("invocada_t", 0)}] if mia else []
        usadas, out = [], []
        for p in lista:
            try:
                pos, t = tuple(p["pos"]), float(p.get("t", 0))
            except (KeyError, TypeError, ValueError):
                continue
            if time.time() - t >= self.VIDA_BALLENA:
                continue
            cand = [v for v in antes if cerca(v, pos) and v not in usadas]
            if cand:
                v = min(cand, key=lambda q: (q[0] - pos[0]) ** 2 + (q[1] - pos[1]) ** 2)
                usadas.append(v)
                out.append({"pos": list(v), "t": t})
        return out

    def _llamar_flotas(self):
        """Siempre tras una tanda: las flotas que se han quedado paradas fuera
        vuelven a la estacion (la misma tarea que usan los piratas de sigilo).
        Desde la vista del sistema, sin ir a la base. No rompe si no hay flotas
        fuera ni si el lector falla."""
        if self.parado():
            return
        from nucleo.adb import SinConexion
        try:
            self.status["estado"] = "llamando a las flotas"
            self.mi_sistema()
            from tareas.flotas import LlamarFlotas
            LlamarFlotas(self.ctrl, log=self._log, stop=self.stop).run(1)
            self.mi_sistema()
        except SinConexion:
            raise
        except Exception as e:                                # noqa: BLE001
            self.log(f"  No he podido llamar a las flotas ({e}); sigo.")

    def _vista_matar(self):
        """Matar se hace en 3D y con el zoom normal del sistema (ver_ballenas,
        anillos_rojos y ballenas_por_forma estan calibrados asi): se deshace
        cualquier zoom o modo 2D que haya dejado una recogida."""
        self._zoom_normal()
        self._modo("3d")
        self.mi_sistema()

    RADIO_ESCOMBROS = 0.25            # fraccion del ancho alrededor del punto de muerte

    def _ruta_ref(self, nombre) -> str:
        import os
        return os.path.join(self.sync.d, nombre)

    def _registrar_muerte(self, pos, img=None):
        """Guarda donde ha muerto una ballena: posicion + hora + una huella
        pequena de la vista del sistema en ese momento (gris a 1/4). Las
        posiciones son coordenadas de PANTALLA: mas tarde la camara puede haberse
        movido, y la huella permite compensar el desplazamiento (como run_en con
        img_ref). Sus escombros se buscan solo ahi, tambien despues (tarea
        «escombros» de Solo ballenas)."""
        import os
        import cv2
        ahora = time.time()
        guardadas, viejas = [], []
        for m in (self.sync.leer().get("muertes") or []):
            (guardadas if ahora - float(m.get("t", 0)) < self.VIDA_BALLENA else viejas).append(m)
        for m in viejas:                                  # huellas caducadas
            if m.get("ref"):
                try:
                    os.remove(self._ruta_ref(m["ref"]))
                except OSError:
                    pass
        entrada = {"pos": list(pos), "t": ahora}
        if img is not None:
            try:
                nombre = f"ref_{self.yo}_{int(ahora * 1000)}.png"
                chica = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), None, fx=0.25, fy=0.25)
                if cv2.imwrite(self._ruta_ref(nombre), chica):
                    entrada["ref"] = nombre
            except Exception:                             # noqa: BLE001
                pass
        guardadas.append(entrada)
        self.sync.escribir(muertes=guardadas)

    def puntos_muerte_recientes(self) -> list[tuple]:
        """Donde han muerto ballenas hace menos de ~30 min, YA COMPENSADOS a la
        vista de ahora: se compara la huella guardada con una captura actual de
        la vista del sistema (desplazamiento, como run_en con img_ref) y se mueve
        cada punto. Los que no se pueden compensar (sin huella o vistas muy
        distintas) se descartan: es mejor no recoger que tocar donde no es."""
        import cv2
        from tareas.piratas.normales import desplazamiento
        ahora = time.time()
        recientes = [m for m in (self.sync.leer().get("muertes") or [])
                     if ahora - float(m.get("t", 0)) < self.VIDA_BALLENA and m.get("pos")]
        self._origen_muerte = {}
        if not recientes:
            return []
        self._vista_matar()                               # 3D y zoom normal, como al guardar
        ahora_img = self.ctrl.capture()
        h, w = ahora_img.shape[:2]
        out = []
        for m in recientes:
            ref = m.get("ref")
            if not ref:
                continue
            ref_img = cv2.imread(self._ruta_ref(ref), cv2.IMREAD_GRAYSCALE)
            if ref_img is None:
                continue
            ref_img = cv2.cvtColor(cv2.resize(ref_img, (w, h)), cv2.COLOR_GRAY2BGR)
            d = desplazamiento(ref_img, ahora_img)
            if d is None:
                continue
            p = (int(m["pos"][0] + d[0]), int(m["pos"][1] + d[1]))
            if 0 < p[0] < w and 0 < p[1] < h:
                out.append(p)
                self._origen_muerte[p] = tuple(m["pos"])
        return out

    def _olvidar_muerte(self, punto):
        """Quita de lo guardado el punto (el de pantalla de ahora o el original)."""
        original = getattr(self, "_origen_muerte", {}).get(tuple(punto), tuple(punto))
        lista = [m for m in (self.sync.leer().get("muertes") or [])
                 if not cerca(tuple(m.get("pos") or (-999, -999)), original)]
        self.sync.escribir(muertes=lista)

    def recoger_escombros_muerte(self, puntos=None) -> int:
        """Los escombros de las ballenas muertas (mineral, aleacion, cristal;
        nunca Nucleos) SOLO junto a sus puntos de muerte (los de la tanda, o los
        guardados de los ultimos ~30 min), con los drones que queden libres segun
        el contador comun de tareas/restos.py y solo los que superen su minimo
        (ajustes: mineral 18 M, cristal 2 M, aleacion 1 M). Por cada punto: se
        centra la camara ahi (3D > tocar el punto > 2D), se aleja un paso si no
        se ve ningun icono y solo se miran los iconos cercanos al centro
        (RADIO_ESCOMBROS): los lejanos son de piratas o de otros. Respaldo: si no
        se ve ningun icono en 2D, en 3D con run_en alrededor del punto y la
        captura tomada al morir como referencia. Mismo turno de drones y
        descartes que los escombros de siempre (RecogerRestos)."""
        if not self.con_escombros or self.parado():
            return 0
        if puntos is None:
            puntos = list(getattr(self, "_muertes", None) or
                          ([tuple(self._muerte)] if getattr(self, "_muerte", None) is not None else []))
        puntos = [tuple(p) for p in puntos]
        if not puntos:
            return 0
        from tareas.restos import RecogerRestos, drones_libres
        libres = drones_libres(self._cuenta_drones(), self.robots)
        if libres <= 0:
            self.log("  Escombros de la ballena: no queda ningún dron libre.")
            return 0
        self.status["estado"] = "recogiendo escombros"
        r = RecogerRestos(self.ctrl, log=self._log, stop=self.stop).que_recoger(True, False)
        r.con_minimos(self.minimos)

        def cerca_centro(c, img):
            h, w = img.shape[:2]
            return (c[0] - w / 2) ** 2 + (c[1] - h / 2) ** 2 <= (self.RADIO_ESCOMBROS * w) ** 2
        n = 0
        try:
            for punto in puntos:
                if self.parado() or libres <= 0:
                    break
                self._muerte = punto
                self._zoom_a_muerte()                 # 3D > tocar el punto > 2D, centrado
                dentro = r.recoger_iconos(libres, cerca=cerca_centro, fija=True)
                if not r.iconos_vistos and self._zoom_mapa(False):
                    dentro = r.recoger_iconos(libres, cerca=cerca_centro, fija=True)
                if r.iconos_vistos:
                    # se vieron iconos pero solo montones bajo el minimo: ya no hay nada aqui
                    if not dentro and r.sitios_poco and not r.sitios_utiles:
                        self._olvidar_muerte(punto)
                else:
                    # respaldo en 3D (donde estan calibrados los puntos y la referencia)
                    self._restaurar_vista()
                    self._modo("3d")
                    dentro = r.run_en([punto], cupo=libres, img_ref=getattr(self, "_img_muerte", None))
                    if not dentro:
                        self._olvidar_muerte(punto)   # sin nada que recoger aqui
                n += dentro
                libres = drones_libres(self._cuenta_drones(), self.robots)
                self._restaurar_vista()
        finally:
            self._restaurar_vista()
            self._modo("3d")                      # matar / buscar ballenas se hace en 3D
            self.mi_sistema()
        if n:
            self.log(f"  Escombros de la ballena: {n} recogida(s) con los drones.")
            self.status["recogidas"] += n
        return n

    def ciclo_apoyo(self) -> int:
        """Lo hace la otra cuenta: sigue al lider ballena a ballena."""
        d = self.sync.del_otro()
        ciclo = d.get("ciclo")
        if not ciclo or d.get("fase") not in ("pedido", "atacar", "gemas"):
            return 0
        self._preparar()
        self._muertes, self._img_muerte = [], None
        # las ballenas que ya hay antes de que la otra cuenta invoque son de
        # otros jugadores: no se tocan
        self._vista_matar()
        antes = self.ver_ballenas()
        # si el que invoca va a por ballenas suyas de una tanda anterior, las que yo
        # lance entonces (menos de 30 min) y siguen ahi no son de otros: cuentan como nuevas
        previas = [p for p in (self.sync.leer().get("lanzadas") or [])
                   if time.time() - float(p.get("t", 0)) < self.VIDA_BALLENA]
        if previas and self.sync.del_otro().get("con_pendientes"):
            antes = [v for v in antes if not any(cerca(v, p["pos"]) for p in previas)]
        self.sync.escribir(presente=ciclo)
        self.log("Ballenas: la otra cuenta me pide ayuda; voy.")
        d = self.sync.esperar(lambda d: d.get("ciclo") != ciclo or d.get("fase") != "pedido",
                              600, self.parado)
        if not d or d.get("ciclo") != ciclo or d.get("fase") not in ("atacar", "gemas"):
            return 0
        ballenas = d.get("ballenas", [])
        hechas = set()              # (ballena, reintento) ya intentadas
        while not self.parado():
            d = self.sync.del_otro()
            if d.get("ciclo") != ciclo or d.get("fase") != "atacar":
                break
            i = d.get("objetivo")
            intento = int(d.get("intento") or 0)
            if i is None or (i, intento) in hechas or i >= len(ballenas):
                time.sleep(1)
                continue
            hechas.add((i, intento))
            self.status["estado"] = f"atacando ballena {i + 1} con la otra cuenta"
            # reintentar mientras la otra cuenta siga esperando esta ballena
            lanzado = False
            for mio in range(4):
                if self.parado():
                    break
                self.mi_sistema()
                pos = tuple(ballenas[i])
                # en esta cuenta la ballena sale en otro sitio: de las NUEVAS
                # (las que no estaban antes), la mas cercana
                nuevas = [v for v in self.ver_ballenas() if not any(cerca(v, a) for a in antes)]
                if not nuevas:
                    self.log("  No distingo la ballena de la otra cuenta; no ataco ninguna de otros.")
                    time.sleep(3)
                    continue
                pos = min(nuevas, key=lambda p: abs(p[0] - pos[0]) + abs(p[1] - pos[1]))
                self._muerte = pos
                if self.atacar_ballena(ciclo, i, pos, intento=intento):
                    lanzado = True
                    if not any(cerca(pos, q) for q in self._muertes):
                        self._muertes.append(tuple(pos))
                        self._img_muerte = self.ctrl.capture()
                        self._registrar_muerte(pos, self._img_muerte)
                    self._img_muerte = self.ctrl.capture()
                    # recordar donde la lance (si no muere, la siguiente tanda del que invoca)
                    lanz = [p for p in (self.sync.leer().get("lanzadas") or [])
                            if time.time() - float(p.get("t", 0)) < self.VIDA_BALLENA
                            and not cerca(pos, p["pos"])]
                    self.sync.escribir(lanzadas=lanz + [{"pos": list(pos), "t": time.time()}])
                    break
                d = self.sync.del_otro()
                if (d.get("ciclo") != ciclo or d.get("fase") != "atacar"
                        or d.get("objetivo") != i or int(d.get("intento") or 0) != intento):
                    break
                self.log(f"  Reintento la ballena {i + 1} ({mio + 2}/4).")
            if not lanzado and not self.parado():
                # avisar para que la otra cuenta no espere 5 min en balde
                self.sync.escribir(abandona=f"{ciclo}:{i}:{intento}")
            self.mi_sistema()
        self._llamar_flotas()            # acabada la tanda: las flotas, a la estacion (antes de recoger)
        d = self.sync.del_otro()
        if d.get("ciclo") == ciclo and self.con_gemas:
            self._gemas_ciclo(lider=False)
        if d.get("ciclo") == ciclo and d.get("muertas"):
            self.recoger_escombros_muerte()
        self.sync.escribir(hecho=ciclo, ult_ballena=time.time())
        # la otra cuenta ha acabado su tanda del dia: reparar tambien
        d = self.sync.esperar(lambda d: d.get("fase") == "hecho", 120, self.parado) or {}
        if d.get("ciclo") == ciclo and d.get("final"):
            self._reparar_final()
        return len({i for i, _ in hechas})

    def run(self, ciclos: int = 1):
        if not ocr.disponible():
            self.log("Ballenas: falta el lector de texto (RapidOCR).")
            return
        self.log(f"Ballenas de éter ({'sola' if self.sola else 'invoca' if self.lider else 'apoya'}).")
        if self.lider:
            self.ciclo_lider()
        else:
            self.ciclo_apoyo()
        self.status["estado"] = "parado" if self.parado() else "terminado"

# pausa ballenas 5 nov 17:03
