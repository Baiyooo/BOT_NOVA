"""La Rutina: el bot decide solo que hacer en cada momento.

Ya no recorre una lista fija de pasos a horas fijas. Tras cada accion le
pregunta al planificador (planificador.py) que vale mas AHORA, mirando:
  - que eventos hay y cuanto les queda (leido del juego con OCR);
  - que misiones de esos eventos hace el bot y cuanto falta en esta cuenta;
  - los temporizadores (suministros gratis, sigilo, recompensas de eventos);
  - lo diario aun sin hacer (simulacion, recompensas diarias), que se hace
    en cuanto se pulsa Empezar, sin esperar a una hora.
Las reglas del bot son limites fijos: nunca gasta GEC, no construye
naves, no abre cajas ni acelera. Los piratas de sigilo, siempre; los
normales, solo mientras un evento activo pida fuerza pirata."""
from __future__ import annotations

import time

from nucleo import config as _cfg
from nucleo.adb import SinConexion
from nucleo import diagnostico as _diag
from nucleo import estadisticas as _est
from vision import ocr
from vision import pantallas
from cerebro import planificador as _plan
from tareas.cosmomante.juego import Cosmomante
from tareas.eventos import RecogerEventos
from cerebro.lector_eventos import LectorEventos
from cerebro.memoria_eventos import Memoria
from tareas.piratas.normales import PiratasNormales
from tareas.piratas.sigilo import PiratasSigilo
from tareas.recompensas import RecogerGratis, Recompensas, Simulacion
from nucleo.rutas import carpeta_diag


class Rutina:
    NOMBRE = "Rutina automática"
    NOMBRES = _plan.NOMBRES
    # pasos que se pueden activar en Ajustes (los demas los decide el planificador)
    PASOS = ("gratis", "recompensas", "eventos", "simulacion", "sigilo", "normales",
             "cosmomante", "destacamento", "ballenas", "llamar_flotas")
    # aun sin tarea en el bot: el planificador no los propone aunque esten marcados
    SIN_TAREA = ()

    def __init__(self, ctrl, log=None, stop=None, normales=False, usar_salto=False,
                 que=None, ballenas_dia=2, ballenas=None):
        self.ctrl, self._log, self.stop = ctrl, log, stop
        self.usar_salto = usar_salto
        defecto = {"gratis": True, "recompensas": False, "eventos": True,
                   "simulacion": True, "sigilo": True, "normales": bool(normales),
                   "cosmomante": False, "destacamento": False, "ballenas": False,
                   "llamar_flotas": True}
        self.que = {k: bool((que or {}).get(k, defecto[k])) for k in self.PASOS}
        for k in self.SIN_TAREA:
            self.que[k] = False
        self.status = {"estado": "en espera", "ciclo": 0, "ciclos": 0,
                       "encontrados": 0, "atacados": 0, "recogidas": 0,
                       "normales": 0, "sigilo": 0, "plan": [], "rutina_hecho": 0,
                       "rutina_total": 0, "rutina_texto": "", "eventos_lista": []}
        import os
        nombre = str(getattr(ctrl, "name", "inst")).replace(":", "_")
        self.ruta = os.path.join(os.path.dirname(carpeta_diag()), f"rutina_{nombre}.json")
        self.mem = Memoria(getattr(ctrl, "name", "inst"))
        self.puerto = str(getattr(ctrl, "name", "inst")).split(":")[-1]
        # papel de esta cuenta en las ballenas: invoca / apoya / no (Ajustes > Ballenas)
        #   (sin pareja guardada, esta cuenta no hace ballenas)
        b = dict(ballenas or {})
        self.b_rol = b.get("rol", "no")
        self.b_con = str(b.get("con") or "")
        self.b_robots = int(b.get("robots") or 6)
        self.ballenas_dia = int(b.get("dia", ballenas_dia) or 0)
        self._ocr = None
        self._leido_sesion = False
        self._pausa: dict = {}
        self._fallos: dict = {}
        self._rec_paso = 0
        self._t_ult = 0.0

    # ------------------------------------------------------------ comun --
    def log(self, m):
        if self._log:
            self._log(getattr(self.ctrl, "name", ""), m)

    def parado(self):
        return self.stop is not None and self.stop.is_set()

    def _estado(self) -> dict:
        return _cfg.leer_config(self.ruta)

    def _guardar(self, est):
        est = {k: v for k, v in est.items() if not k.startswith("_") or k == "_v"}
        _cfg.guardar_config(self.ruta, est)

    def _tarea(self, cls, **kw):
        t = cls(self.ctrl, log=self._log, stop=self.stop, **kw)
        t.status = self.status | {k: v for k, v in t.status.items() if k not in self.status}
        return t

    def _hay_ocr(self) -> bool:
        if self._ocr is None:
            self._ocr = ocr.disponible()
            if not self._ocr:
                self.log("Aviso: falta el lector de texto (RapidOCR); la Rutina no puede leer "
                         "los eventos ni sus misiones. Abre BOT.bat (lo instala). Mientras "
                         "tanto sigue como antes.")
        return self._ocr

    # prueba de ballenas pedida a mano: ballenas/prueba.json
    #   {"t": ..., "turnos": [{"lider": "<puerto>", "apoyo": "<puerto>"}, ...], "hecho": 0}
    # cada turno: el lider invoca 1 y la matan entre las dos (vale 2 h)
    def _prueba(self):
        try:
            import os
            from tareas.ballenas.sync import _carpeta_sync
            ruta = os.path.join(_carpeta_sync(), "prueba.json")
            d = _cfg.leer(ruta, defecto={})
            tur = d.get("turnos") or []
            i = int(d.get("hecho", 0))
            if time.time() - float(d.get("t", 0)) > 7200 or i >= len(tur):
                return None, None, ruta
            return tur[i], d, ruta
        except Exception:                                     # noqa: BLE001
            return None, None, None

    def _tanda_otra(self) -> bool:
        """La otra cuenta de la pareja ha hecho una ballena hace menos de 20 min
        (esta encadenando ballenas): no cambiar de grupo con el sigilo."""
        if self.b_rol != "apoya" or not self.b_con:
            return False
        try:
            import os
            from tareas.ballenas.sync import _carpeta_sync
            d = _cfg.leer(os.path.join(_carpeta_sync(), f"{self.b_con}.json"), defecto={})
            ult = max(d.get("ult_ballena", 0), d.get("invocada_t", 0))
            return time.time() - ult < 1200 and not d.get("tanda_fin")
        except Exception:                                     # noqa: BLE001
            return False

    def _pedido_ballenas(self) -> bool:
        tur, _, _ = self._prueba()
        if tur and str(tur.get("apoyo")) == self.puerto:
            from tareas.ballenas.sync import pedido_pendiente
            return pedido_pendiente(self.puerto, str(tur.get("lider")))
        if self.b_rol != "apoya" or not self.b_con or not self.que.get("ballenas"):
            return False
        try:
            from tareas.ballenas.sync import pedido_pendiente
            return pedido_pendiente(self.puerto, self.b_con)
        except Exception:                                     # noqa: BLE001
            return False

    def _decidir(self, est):
        e = dict(est, _leido_sesion=self._leido_sesion, _pausa=self._pausa,
                 _ballenas_lider=self.b_rol == "invoca" and bool(self.b_con),
                 _ballenas_pedido=self._pedido_ballenas(),
                 _ballenas_rol=self.b_rol,
                 _tanda_ballenas=self._tanda_otra(),
                 _sigilo_quedan=getattr(self, "_sigilo_quedan", False),
                 _sin_piratas_t=getattr(self, "_sin_piratas_t", 0),
                 _ballenas_prueba=str((self._prueba()[0] or {}).get("lider")) == self.puerto)
        mem = self.mem if self._hay_ocr() else None
        return _plan.decidir(e, self.que, mem, opciones={"ocr": mem is not None,
                                                         "ballenas_dia": self.ballenas_dia})

    # ------------------------------------------------------ para la ventana --
    def _publicar(self, est, ahora_accion=None, cola=None):
        hoy = _plan.dia_juego(time.time())
        cola = cola if cola is not None else self._decidir(est)
        diarios = [k for k in ("simulacion", "recompensas") if self.que.get(k)]
        hecho = sum(1 for k in diarios if est.get(k) == hoy)
        self.status["rutina_hecho"], self.status["rutina_total"] = hecho, len(diarios)
        plan = []
        if ahora_accion is not None:
            plan.append({"k": ahora_accion.clave, "n": self.NOMBRES.get(ahora_accion.clave),
                         "e": "ahora", "m": ahora_accion.motivo})
        for a in cola:
            if ahora_accion is not None and a.clave == ahora_accion.clave:
                continue
            plan.append({"k": a.clave, "n": self.NOMBRES.get(a.clave), "e": "pendiente",
                         "m": a.motivo})
        prox = _plan.proxima_espera(est, self.que)
        self.status["plan"] = plan or [{"k": "espera", "n": "Esperando", "e": "espera", "m": ""}]
        self.status["sig_c"] = prox if not cola else 0
        self.status["sig_n"] = "siguiente tarea" if not cola else ""
        if ahora_accion is not None:
            txt = f"Ahora: {self.NOMBRES.get(ahora_accion.clave)} ({ahora_accion.motivo})"
        else:
            txt = "Ahora: esperando"
        self.status["rutina_texto"] = txt
        try:
            self.status["eventos_lista"] = self.mem.resumen()
        except Exception:                                     # noqa: BLE001
            self.status["eventos_lista"] = []

    # ------------------------------------------------------------ acciones --
    def _ejecutar(self, a, est):
        k = a.clave
        hoy = _plan.dia_juego(time.time())
        self.status["estado"] = self.NOMBRES.get(k, k).lower()
        self._publicar(est, a)
        if (k, a.motivo) != getattr(self, "_ultima", None):    # no repetir la misma linea
            self.log(f"▶ {self.NOMBRES.get(k, k)}: {a.motivo}.")
            self._ultima = (k, a.motivo)
        if k == "leer_eventos":
            t = self._tarea(LectorEventos)
            # al empezar la sesion, ademas, el progreso de ESTA cuenta en cada evento
            t.run(1, progreso_cuenta=not self._leido_sesion)
            self._leido_sesion = True
            est["lectura_t"] = est["progreso_t"] = time.time()
        elif k == "progreso":
            t = self._tarea(LectorEventos)
            t.progreso_de(a.datos.get("evento", ""))
            est["progreso_t"] = time.time()
        elif k == "gratis":
            t = self._tarea(RecogerGratis)
            t.run(1)
            self._rec_paso += int(t.status.get("recogidas", 0) or 0)
            est["gratis_t"] = time.time()
            esp = int(t.status.get("gratis_espera") or 0)
            est["gratis_prox"] = time.time() + esp + 5 if 0 < esp <= 3600 else 0
        elif k == "recompensas":
            t = self._tarea(Recompensas)
            t.run(1)
            self._rec_paso += int(t.status.get("recogidas", 0) or 0)
            est["recompensas"] = hoy
        elif k == "eventos":
            t = self._tarea(RecogerEventos)
            t.run(1)
            self._rec_paso += int(t.status.get("recogidas", 0) or 0)
            est["eventos_t"] = time.time()
        elif k in ("ballenas", "ballenas_apoyo"):
            from tareas.ballenas.tarea import Ballenas
            b = est.get("ballenas", {})
            hechas = b.get("n", 0) if b.get("dia") == hoy else 0
            lider = self.puerto if self.b_rol == "invoca" else self.b_con
            apoyo = self.b_con if self.b_rol == "invoca" else self.puerto
            tope = self.ballenas_dia
            tur, dp, rp = self._prueba()
            if tur and self.puerto in (str(tur.get("lider")), str(tur.get("apoyo"))):
                lider, apoyo = str(tur.get("lider")), str(tur.get("apoyo"))
            prueba = bool(a.datos.get("prueba")) and tur is not None
            if prueba:
                tope = hechas + 1                          # solo 1 ballena por turno
                self.log(f"Prueba de ballenas: invoco 1 y la matamos con {apoyo}.")
            t = self._tarea(Ballenas, lider=lider, apoyo=apoyo, robots=self.b_robots,
                            tope_dia=tope, hechas_hoy=hechas,
                            grupo_actual=getattr(self, "_grupo", None))
            if prueba:
                n = t.ciclo_lider()
                if n > 0:
                    est["ballenas"] = {"dia": hoy, "n": hechas + n}
                    dp["hecho"] = int(dp.get("hecho", 0)) + 1
                    dp["fallos"] = 0
                    self.log(f"Prueba de ballenas: turno hecho ({n} muerta(s)).")
                elif self.parado():
                    pass                                   # cortado (version nueva / parar): no cuenta
                else:
                    # no se ha podido (sin respuesta, sin señuelo o sin ballena):
                    # se reintenta; a los 3 fallos se salta el turno
                    dp["fallos"] = int(dp.get("fallos", 0)) + 1
                    if dp["fallos"] >= 3:
                        dp["hecho"] = int(dp.get("hecho", 0)) + 1
                        dp["fallos"] = 0
                        self.log("Prueba de ballenas: 3 intentos sin conseguirlo; paso al siguiente turno.")
                    else:
                        self.log(f"Prueba de ballenas: no ha salido (intento {dp['fallos']}); reintento.")
                # solo si sigue siendo la misma prueba (no pisar una prueba nueva)
                if _cfg.leer(rp, defecto={}).get("t") == dp.get("t"):
                    _cfg.guardar(rp, dp)
            elif k == "ballenas" and tur is not None:
                # hay una prueba en marcha: no se invoca aparte (mirar en 5 min)
                est["ballenas_prox"] = time.time() + 300
            elif k == "ballenas":
                n = t.ciclo_lider()
                if self.parado():
                    pass                                   # cortado (version nueva / parar): reintentar ya
                elif n < 0:                                # la otra cuenta no respondio
                    est["ballenas_prox"] = time.time() + 900
                else:
                    est["ballenas"] = {"dia": hoy, "n": hechas + n}
                    est["ballenas_prox"] = time.time() + (900 if n == 0 else 30)
                    # la recogida tarda 5 min + el viaje del robot: se sigue con
                    # otras cosas y el siguiente ciclo espera a que acabe
                    if n > 0:
                        est["ballenas_prox"] = time.time() + 6 * 60
            else:
                t.ciclo_apoyo()
            self._rec_paso += int(t.status.get("recogidas", 0) or 0)
            self._grupo = 2                                # Ballenas deja cargado el PVE
        elif k == "gemas":
            from tareas.ballenas.tarea import Ballenas
            lider = self.puerto if self.b_rol == "invoca" else self.b_con
            apoyo = self.b_con if self.b_rol == "invoca" else self.puerto
            t = self._tarea(Ballenas, lider=lider, apoyo=apoyo, robots=self.b_robots)
            t.recoger_sueltas()
            self._rec_paso += int(t.status.get("recogidas", 0) or 0)
            est["gemas_t"] = time.time()
        elif k == "llamar_flotas":
            from tareas.flotas import LlamarFlotas
            self._tarea(LlamarFlotas).run(1)
            est["flotas_t"] = time.time()
            est["flotas_ya"] = False
        elif k == "destacamento":
            from tareas.destacamento import Destacamento
            t = self._tarea(Destacamento)
            t.run(1)
            d = est.get("destacamento", {})
            if d.get("dia") != hoy:
                d = {"dia": hoy}
            d[a.datos.get("tanda", "manana")] = True
            est["destacamento"] = d
            self._rec_paso += int(t.status.get("recogidas", 0) or 0)
        elif k == "cosmomante":
            self._tarea(Cosmomante).run(1)
            est["cosmomante_t"] = time.time()
        elif k == "simulacion":
            t = self._tarea(Simulacion)
            t.run(1)
            self._rec_paso += int(t.status.get("recogidas", 0) or 0)
            est["simulacion"] = hoy
        elif k == "sigilo":
            # para los sigilosos, el grupo de ataque de arriba (1º)
            if self.que.get("grupo_sigilo", True) and getattr(self, "_grupo", None) != 1:
                try:
                    from tareas.grupo import preparar
                    if preparar(self.ctrl, log=self._log, stop=self.stop, grupo=1, reparar=True):
                        self._grupo = 1
                except Exception as e:                        # noqa: BLE001
                    self.log(f"No he podido cargar el grupo 1 ({e}); sigo.")
            t = self._tarea(PiratasSigilo, atacar=True, usar_salto=self.usar_salto)
            t.ESPERAR_BUSQUEDAS = False
            # si la otra cuenta pide ayuda con una ballena, se corta la tanda de
            # sigilo al acabar el pirata en curso (la ballena va primero)
            def _toca_ballena():
                if self.b_rol != "invoca" or not self.que.get("ballenas"):
                    return False
                b = est.get("ballenas", {})
                n = b.get("n", 0) if b.get("dia") == hoy else 0
                return n < self.ballenas_dia and est.get("ballenas_prox", 0) <= time.time()
            # las ballenas van antes que todo: se corta el sigilo al acabar el pirata
            t.parado = lambda: (self.parado() or self._pedido_ballenas() or _toca_ballena()
                                or str((self._prueba()[0] or {}).get("lider")) == self.puerto)
            t.run(0)
            img = t.cap("fin_sigilo")                     # no dejar el radar abierto
            if t.radar_abierto(img):
                t.atras(img)
            self.status["encontrados"] = t.status["encontrados"]
            self.status["atacados"] = self.status["sigilo"] = t.status["atacados"]
            self._contar(est, hoy)["pir_sigilo"] = self.status["sigilo"]
            est["sigilo_t"] = time.time()
            # al acabar la tanda (o cortarse por fallos) las
            # flotas NO se quedan paradas en el sistema: se llaman enseguida.
            # Si quedan busquedas, el siguiente intento las vuelve a mandar.
            self._sigilo_quedan = False
            est["flotas_ya"] = True
            if t.status.get("estado") != "sin_busquedas" and not self.parado():
                # aun quedan busquedas (se ha cortado por fallos): reintento en 5 min
                est["sigilo_t"] = time.time() - _plan.CADA_SIGILO + 300
        elif k == "normales":
            t = self._tarea(PiratasNormales)
            # con memoria de misiones manda el planificador; sin ella, la
            # tarea mira la mision de Cosmomante como antes
            t.PARAR_MISION = bool(a.datos.get("sin_memoria"))
            t.run(_plan.POR_TANDA_NORMALES)
            self.status["normales"] = self.status.get("normales", 0) + int(t.status.get("ciclo", 0) or 0)
            self._contar(est, hoy)["pir_normales"] = self.status["normales"]
            if t.status.get("mision_hecha"):
                self._pausa["normales"] = _plan_proximo_dia()
            if t.status.get("sin_piratas"):
                self._sin_piratas_t = time.time()
            # flotas a casa solo si la mision esta hecha o no hay piratas (si no,
            # el planificador no las llama mientras la mision siga pendiente)
            if t.status.get("mision_hecha") or t.status.get("sin_piratas"):
                est["flotas_ya"] = True
        self._guardar(est)

    @staticmethod
    def _contar(est, hoy) -> dict:
        c = est.get("cuenta", {})
        if c.get("dia") != hoy:
            c = {"dia": hoy}
        est["cuenta"] = c
        return c

    def _tick(self, forzar=False):
        ahora = time.time()
        if not self._t_ult:
            self._t_ult = ahora
            return
        if forzar or ahora - self._t_ult >= 30:
            _est.sumar(getattr(self.ctrl, "name", ""), "segundos", min(ahora - self._t_ult, 300))
            self._t_ult = ahora

    def _accion_segura(self, a, est):
        """Ejecuta una accion; si falla, la apunta (con captura) y sigue con lo
        demas. Tras 3 fallos seguidos, la aparca 30 min."""
        cuenta = getattr(self.ctrl, "name", "")
        antes = [self.status.get(x, 0) or 0 for x in ("sigilo", "normales", "encontrados")]
        self._rec_paso = 0
        try:
            self._ejecutar(a, est)
            self._fallos[a.clave] = 0
            _est.sumar(cuenta, "ok")
            for x, v in zip(("sigilo", "normales", "encontrados"), antes):
                _est.sumar(cuenta, x, (self.status.get(x, 0) or 0) - v)
            _est.sumar(cuenta, "recompensas", self._rec_paso)
        except SinConexion as e:
            # BlueStacks cerrado o sin ADB: no es un fallo de la tarea. Se apunta
            # UNA vez y se espera a que vuelva, en vez de un error cada minuto.
            self._esperar_conexion(est, e)
        except Exception as e:                                # noqa: BLE001
            _est.sumar(cuenta, "errores")
            self._fallos[a.clave] = self._fallos.get(a.clave, 0) + 1
            img, pantalla = None, ""
            try:
                img = self.ctrl.capture()
                pantalla = pantallas.donde_estoy(img)
            except Exception:                                 # noqa: BLE001
                pass
            _diag.registrar(f"{type(e).__name__}: {e}", cuenta=cuenta,
                            tarea=self.NOMBRES.get(a.clave, a.clave), pantalla=pantalla,
                            accion=f"ejecutar '{a.clave}' en la Rutina", img=img)
            self.log(f"  Error en «{self.NOMBRES.get(a.clave, a.clave)}»: {e}. Sigo con lo demás.")
            if self._fallos[a.clave] >= 3:
                self._pausa[a.clave] = time.time() + 1800
                self._fallos[a.clave] = 0
                self.log(f"  «{self.NOMBRES.get(a.clave, a.clave)}» falla seguido: lo dejo 30 min.")
            else:
                self._pausa[a.clave] = time.time() + 60
            if a.clave == "leer_eventos":
                self._leido_sesion = True               # no insistir en bucle
                est["lectura_t"] = time.time()
                self._guardar(est)

    CADA_CONEXION = 30          # segundos entre comprobaciones mientras no hay conexion
    INTENTOS_CONEXION = 4       # unos 2 minutos; si no vuelve, se para esta cuenta

    def _esperar_conexion(self, est, error):
        """BlueStacks no da imagen: se comprueba unas pocas veces (no para
        siempre) si vuelve, sin apuntar mas errores. Si no vuelve, se para la
        Rutina de esta cuenta (self._sin_imagen) en vez de seguir probando."""
        cuenta = getattr(self.ctrl, "name", "")
        _est.sumar(cuenta, "errores")
        _diag.registrar(f"{type(error).__name__}: {error}", cuenta=cuenta, tarea="Rutina",
                        accion="capturar la pantalla (BlueStacks cerrado o sin ADB)")
        self.log("  No veo la pantalla de esta cuenta: su ventana de BlueStacks está cerrada "
                 f"o sin ADB. Lo compruebo {self.INTENTOS_CONEXION} veces, cada "
                 f"{self.CADA_CONEXION} s; si no vuelve, paro esta cuenta.")
        self.status["estado"] = "sin conexión"
        self.status["plan"] = [{"k": "conexion", "n": "Esperando a BlueStacks", "e": "ahora",
                                "m": "la ventana de esta cuenta está cerrada o sin ADB"}]
        self.status["rutina_texto"] = "Ahora: esperando a BlueStacks"
        self.status["sig_c"], self.status["sig_n"] = 0, ""
        inicio = time.time()
        conectada = getattr(self.ctrl, "conectada", None)
        vuelve = False
        for _ in range(self.INTENTOS_CONEXION):
            if self.parado():
                break
            fin = time.time() + self.CADA_CONEXION
            while time.time() < fin and not self.parado():
                time.sleep(2)
            if self.parado():
                break
            try:
                if conectada is not None and not conectada():
                    continue
                self.ctrl.capture()                    # que de verdad se pueda capturar
                vuelve = True
                break
            except Exception:                                 # noqa: BLE001
                continue
        self._t_ult = time.time()                      # el rato sin conexion no cuenta como "en marcha"
        if not vuelve and not self.parado():
            self._sin_imagen = True
            self.status["rutina_texto"] = "Parada: BlueStacks no responde"
            self.log("  BlueStacks sigue sin responder: paro la Rutina de esta cuenta. "
                     "Cuando su ventana esté abierta, pulsa EMPEZAR.")
            return
        if vuelve:
            minutos = round((time.time() - inicio) / 60)
            self.log(f"  BlueStacks vuelve a responder (tras {minutos} min). Sigo con la Rutina.")
            self.status["estado"] = "en marcha"

    # ------------------------------------------------------------------ run --
    def run(self, ciclos: int = 0):
        activos = [self.NOMBRES.get(k, k) for k in self.PASOS if self.que.get(k)]
        if not activos:
            self.log("Rutina: no hay nada marcado para hacer.")
            return
        self.log("Rutina en marcha: decide sola qué toca en cada momento ("
                 + ", ".join(activos) + "). Para pararla, pulsa PARAR.")
        try:
            from vision import percepcion
            self.log(f"Percepción: {percepcion.info()}.")
        except Exception:                                     # noqa: BLE001
            pass
        self._t_ult = time.time()
        while not self.parado():
            self._tick()
            est = self._estado()
            c = self._contar(est, _plan.dia_juego(time.time()))
            self.status["normales"] = c.get("pir_normales", 0)
            self.status["sigilo"] = self.status["atacados"] = c.get("pir_sigilo", 0)
            cola = self._decidir(est)
            if cola:
                self._accion_segura(cola[0], est)
                if getattr(self, "_sin_imagen", False):
                    self.status["estado"] = "sin conexión"
                    return
                continue
            self.status["estado"] = "esperando"
            self._publicar(est, None, cola)
            fin = min(_plan.proxima_espera(est, self.que), time.time() + 120)
            while time.time() < fin and not self.parado():
                time.sleep(2)
                self._tick()
                if self._pedido_ballenas():
                    break
        self._tick(forzar=True)
        self.status["estado"] = "parado"


def _plan_proximo_dia(hora=2) -> float:
    t = time.localtime()
    base = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, hora, 0, 0, 0, 0, -1))
    return base if base > time.time() else base + 86400
