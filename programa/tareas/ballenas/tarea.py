"""Ballenas de eter: invocar, matarlas con dos cuentas a la vez y recoger
las gemas que sueltan (aprendido en vivo el 5 nov 2026).

Ciclo:
  1. La cuenta que invoca usa 2 Señuelos de eter V:
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
     viaja sale primero y la otra espera a que le falten ~3 s.
  3. Muertas las dos, se recogen las gemas (organica, gamma, sagrada): boton
     redondo de la derecha > Recursos (filtro con las gemas marcadas) > tocar
     una gema > "Gema ..." > Recoger (el robot sale solo). Se reparten a
     partes iguales entre las dos cuentas (la que invoca coge una mas si son
     impares), sin pasar de sus robots (6 por defecto; se ajusta en Ajustes).
  4. Se espera la recogida (5 min + llegada del robot) y se repite, sin
     pasar del tope de ballenas al dia que se pone en Ajustes.

Que cuenta invoca y cual apoya (y sus robots) se elige en Ajustes > Ballenas.
Las dos cuentas se coordinan con archivos en %LOCALAPPDATA%\\NovaBot\\ballenas
(cada cuenta escribe solo el suyo). Nunca se pulsa nada de pago: ni "Llamar a
todos", ni comprar señuelos, ni "Ataque de grupo".
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


class Ballenas(_Invocar, _Atacar, _Recoger, Recompensas):
    NOMBRE = "Ballenas de éter"
    POR_CICLO = 2

    def __init__(self, ctrl, log=None, stop=None, diag=True, lider="", apoyo="",
                 robots=None, tope_dia=2, hechas_hoy=0, preparar_grupo=True, grupo_actual=None):
        super().__init__(ctrl, log=log, stop=stop, diag=diag)
        self.preparar_grupo = preparar_grupo
        self.grupo_actual = grupo_actual
        self.yo = puerto(getattr(ctrl, "name", "inst"))
        self.lider = self.yo == str(lider)
        self.otro = str(apoyo) if self.lider else str(lider)
        self.sync = Sync(self.yo, self.otro)
        self.robots = robots or 6
        self.tope_dia, self.hechas_hoy = int(tope_dia), int(hechas_hoy)
        self.status = {"estado": "en espera", "ballenas": 0, "gemas": 0, "recogidas": 0}

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
            if preparar(self.ctrl, log=self._log, stop=self.stop, grupo=2, reparar=True):
                self.sync.escribir(prep_t2=time.time(), tanda_fin=False)
        except Exception as e:                                # noqa: BLE001
            self.log(f"  No he podido preparar el grupo ({e}); sigo.")

    def _reparar_final(self):
        """Fin de la tanda: reparar (con aceleraciones de reparacion)."""
        self.sync.escribir(tanda_fin=True)
        try:
            from tareas.grupo import solo_reparar
            self.status["estado"] = "reparando al acabar las ballenas"
            self.log("Ballenas: tanda del día acabada; reparo las naves.")
            solo_reparar(self.ctrl, log=self._log, stop=self.stop)
        except Exception as e:                                # noqa: BLE001
            self.log(f"  No he podido reparar al final ({e}).")

    def ciclo_lider(self) -> int:
        """Lo hace la cuenta que invoca. Devuelve las ballenas muertas."""
        n = min(self.POR_CICLO, max(0, self.tope_dia - self.hechas_hoy))
        if n <= 0:
            self.log("Ballenas: tope del día alcanzado.")
            return 0
        self._preparar()
        ciclo = time.strftime("%H%M%S")
        # 0) avisar a la otra cuenta y esperar a que este libre: sin ella no
        #    se gasta ningun señuelo (no se ataca nunca solo)
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
        self.mi_sistema()
        vivas = self.ver_ballenas()
        inv_t = self.sync.leer().get("invocada_t", 0)
        if len(vivas) < n and time.time() - inv_t < 30 * 60:
            # ya invoque una hace menos de 30 min y no la encuentro: sigue en
            # el sistema; NO gastar otro señuelo, buscarla otra vez
            self.log("Ballenas: ya hay una invocada (hace menos de 30 min); no invoco otra.")
            time.sleep(2)
            vivas = self.ver_ballenas() or vivas
            if not vivas:
                self.sync.escribir(fase="cancelado")
                return 0
        elif len(vivas) < n:
            hechas = self.invocar(n - len(vivas))
            self.log(f"Ballenas: {hechas} invocada(s).")
            if hechas:
                self.sync.escribir(invocada_t=time.time())
            self.mi_sistema()
            time.sleep(2)
            vivas = self.ver_ballenas()
        vivas = vivas[:n]
        if not vivas:
            self.log("Ballenas: no veo ninguna ballena en el sistema.")
            return 0
        self.sync.escribir(ciclo=ciclo, ballenas=[list(p) for p in vivas], fase="atacar",
                           gemas=[], muertas=0)
        muertas = 0
        for i, pos in enumerate(vivas):
            if self.parado():
                break
            self.status["estado"] = f"atacando ballena {i + 1}"
            self.sync.escribir(objetivo=i)
            if not self.atacar_ballena(ciclo, i, pos):
                self.mi_sistema()
                continue
            self.mi_sistema()
            if self.esperar_muerte(pos):
                self._muerte = pos
                self.sync.escribir(ult_ballena=time.time())
                muertas += 1
                self.status["ballenas"] += 1
                self.log(f"  Ballena {i + 1} muerta.")
            self.sync.escribir(muertas=muertas)
        total = self._gemas_ciclo(lider=True)
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

    def ciclo_apoyo(self) -> int:
        """Lo hace la otra cuenta: sigue al lider ballena a ballena."""
        d = self.sync.del_otro()
        ciclo = d.get("ciclo")
        if not ciclo or d.get("fase") not in ("pedido", "atacar", "gemas"):
            return 0
        self._preparar()
        self.sync.escribir(presente=ciclo)
        self.log("Ballenas: la otra cuenta me pide ayuda; voy.")
        d = self.sync.esperar(lambda d: d.get("ciclo") != ciclo or d.get("fase") != "pedido",
                              600, self.parado)
        if not d or d.get("ciclo") != ciclo or d.get("fase") not in ("atacar", "gemas"):
            return 0
        ballenas = d.get("ballenas", [])
        hechas = set()
        while not self.parado():
            d = self.sync.del_otro()
            if d.get("ciclo") != ciclo or d.get("fase") != "atacar":
                break
            i = d.get("objetivo")
            if i is None or i in hechas or i >= len(ballenas):
                time.sleep(1)
                continue
            hechas.add(i)
            self.status["estado"] = f"atacando ballena {i + 1} con la otra cuenta"
            # reintentar mientras la otra cuenta siga esperando esta ballena
            for intento in range(4):
                if self.parado():
                    break
                self.mi_sistema()
                pos = tuple(ballenas[i])
                # en esta cuenta la ballena sale en otro sitio: la mas cercana
                vivas = self.ver_ballenas()
                if vivas:
                    pos = min(vivas, key=lambda p: abs(p[0] - pos[0]) + abs(p[1] - pos[1]))
                self._muerte = pos
                if self.atacar_ballena(ciclo, i, pos):
                    break
                d = self.sync.del_otro()
                if d.get("ciclo") != ciclo or d.get("fase") != "atacar" or d.get("objetivo") != i:
                    break
                self.log(f"  Reintento la ballena {i + 1} ({intento + 2}/4).")
            self.mi_sistema()
        if self.sync.del_otro().get("ciclo") == ciclo:
            self._gemas_ciclo(lider=False)
        self.sync.escribir(hecho=ciclo, ult_ballena=time.time())
        # la otra cuenta ha acabado su tanda del dia: reparar tambien
        d = self.sync.esperar(lambda d: d.get("fase") == "hecho", 120, self.parado) or {}
        if d.get("ciclo") == ciclo and d.get("final"):
            self._reparar_final()
        return len(hechas)

    def run(self, ciclos: int = 1):
        if not ocr.disponible():
            self.log("Ballenas: falta el lector de texto (RapidOCR).")
            return
        self.log(f"Ballenas de éter ({'invoca' if self.lider else 'apoya'}).")
        if self.lider:
            self.ciclo_lider()
        else:
            self.ciclo_apoyo()
        self.status["estado"] = "parado" if self.parado() else "terminado"

# pausa ballenas 5 nov 17:03
