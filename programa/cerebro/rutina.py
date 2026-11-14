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
from cerebro import config_ballenas as _cb
from tareas.cosmomante.juego import Cosmomante
from tareas.eventos import RecogerEventos
from cerebro.lector_eventos import LectorEventos
from tareas.restos import drones_libres, proximo_dron_libre
from cerebro.memoria_eventos import Memoria
from tareas.piratas.normales import PiratasNormales
from tareas.piratas.sigilo import PiratasSigilo
from tareas.recompensas import RecogerGratis, Recompensas, Simulacion

#  contadores del status que viajan a estadisticas.json al terminar cada accion
CLAVES_STATUS = ("sigilo", "normales", "encontrados", "ballenas", "gemas", "senuelos")


class Rutina:
    NOMBRE = "Rutina automática"
    NOMBRES = _plan.NOMBRES
    # pasos que se pueden activar en Ajustes (los demas los decide el planificador)
    PASOS = ("gratis", "recompensas", "eventos", "simulacion", "sigilo", "normales",
             "cosmomante", "roaming", "artefactos", "bingo", "destacamento", "ballenas",
             "llamar_flotas", "escombros", "gemas")
    # aun sin tarea en el bot: el planificador no los propone aunque esten marcados
    SIN_TAREA = ()
    # tras una tanda de ballenas, esperar a la recogida (5 min + viaje) antes de otra
    ESPERA_TRAS_TANDA = 6 * 60
    # la tarea «escombros» del planificador: False = escombros de todo el sistema
    # (piratas normales, sin minimos); True (Solo ballenas) = solo junto a donde han
    # muerto ballenas hace poco, con los minimos de Ajustes > Ballenas
    ESCOMBROS_DE_BALLENAS = False

    def __init__(self, ctrl, log=None, stop=None, normales=False, usar_salto=False,
                 que=None, ballenas_dia=2, ballenas=None, roaming_tickets=0, horario=None):
        self.ctrl, self._log, self.stop = ctrl, log, stop
        self.usar_salto = usar_salto
        self.roaming_tickets = int(roaming_tickets or 0)
        #  franjas en las que no se hace una tarea (Ajustes > Horario de la cuenta)
        self.horario = dict(horario) if isinstance(horario, dict) else {}
        defecto = {"gratis": True, "recompensas": False, "eventos": True,
                   "simulacion": True, "sigilo": True, "normales": bool(normales),
                   "cosmomante": False, "roaming": False, "artefactos": False, "bingo": False,
                   "escombros": True, "gemas": False,
                   "destacamento": False,
                   "ballenas": False,
                   "llamar_flotas": True}
        self.que = {k: bool((que or {}).get(k, defecto[k])) for k in self.PASOS}
        for k in self.SIN_TAREA:
            self.que[k] = False
        self.status = {"estado": "en espera", "ciclo": 0, "ciclos": 0,
                       "encontrados": 0, "atacados": 0, "recogidas": 0,
                       "normales": 0, "sigilo": 0, "plan": [], "rutina_hecho": 0,
                       "rutina_total": 0, "rutina_texto": "", "eventos_lista": []}
        self.ruta = _cb.ruta_estado(getattr(ctrl, "name", "inst"))
        self.mem = Memoria(getattr(ctrl, "name", "inst"))
        self.puerto = str(getattr(ctrl, "name", "inst")).split(":")[-1]
        # papel de esta cuenta en las ballenas: invoca / apoya / no (Ajustes > Ballenas)
        #   (sin pareja guardada, esta cuenta no hace ballenas)
        #   (la configuracion completa vive en cerebro/config_ballenas.py)
        b = dict(ballenas or {})
        b.setdefault("dia", ballenas_dia)
        b = _cb.normalizar(b)
        self.b_rol = b["rol"]                      # sola / invoca / apoya / no
        self.b_con = b["con"]
        self.b_robots = b["robots"]                # 0 = ninguno
        self.ballenas_dia = b["dia"]
        self.b_grupo, self.b_reparar, self.b_gemas = b["grupo"], b["reparar"], b["gemas"]
        self.b_escombros = b["escombros"]
        self.b_minimos = _cb.minimos_unidades(b)     # minimo de mineral / cristal / aleacion
        #  vista del sistema para detectar ballenas y gemas de ESTA cuenta (Ajustes > Ballenas)
        self.vista = b["vista"]
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

    def _lider_apoyo(self) -> tuple[str, str]:
        """(cuenta que invoca, cuenta que apoya) segun el modo de esta cuenta.
        Sola: invoca ella y no hay apoyo."""
        if self.b_rol == "sola":
            return self.puerto, ""
        if self.b_rol == "invoca":
            return self.puerto, self.b_con
        return self.b_con, self.puerto

    def _args_ballenas(self, lider, apoyo) -> dict:
        """Lo que se le pasa a la tarea Ballenas desde Ajustes > Ballenas (el
        mismo para la Rutina y para «Solo ballenas»)."""
        return {"lider": lider, "apoyo": apoyo, "robots": self.b_robots,
                "sola": self.b_rol == "sola", "preparar_grupo": self.b_grupo,
                "reparar": self.b_reparar, "con_gemas": self.b_gemas,
                "con_escombros": self.b_escombros, "minimos": self.b_minimos,
                "vista": self.vista}

    def _gemas_pedidas(self, est) -> bool:
        """Orden de recoger las gemas del sistema (ballenas/gemas.json, con su
        hora «t» y, si se quiere, la lista de «cuentas»): una vez por orden."""
        try:
            import os
            from tareas.ballenas.sync import _carpeta_sync
            d = _cfg.leer(os.path.join(_carpeta_sync(), "gemas.json"), defecto={})
            t = float(d.get("t", 0))
            cuentas = [str(c) for c in d.get("cuentas") or []]
            return (time.time() - t < 7200 and est.get("gemas_t", 0) < t
                    and (not cuentas or self.puerto in cuentas))
        except Exception:                                     # noqa: BLE001
            return False

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

    def _releer_pedido(self, est) -> bool:
        """Orden de volver a leer los eventos ya (releer_eventos.json en la
        carpeta de datos, con su hora «t» y, si se quiere, la lista de
        «cuentas»): una vez por orden."""
        try:
            import os
            from nucleo.rutas import carpeta_datos
            d = _cfg.leer(os.path.join(carpeta_datos(), "releer_eventos.json"), defecto={})
            t = float(d.get("t", 0))
            cuentas = [str(c) for c in d.get("cuentas") or []]
            if not t or est.get("releer_t", 0) >= t or (cuentas and self.puerto not in cuentas):
                return False
            est["releer_t"] = t
            est["lectura_t"] = 0                    # que el planificador lo pida otra vez
            self._leido_sesion = False
            return True
        except Exception:                                     # noqa: BLE001
            return False

    def _sumar_bal(self, t):
        """Pasa a la cuenta lo que ha hecho una tanda de ballenas (ballenas,
        gemas y señuelos gastados): la tarjeta y las estadisticas lo ven."""
        for k in ("ballenas", "gemas", "senuelos"):
            self.status[k] = self.status.get(k, 0) + int(t.status.get(k, 0) or 0)

    def _decidir(self, est):
        if self._releer_pedido(est):
            self.log("Releo los eventos ahora (pedido desde la ventana).")
        # cuando vuelve el primer dron (para despertar justo entonces)
        est["_dron_vuelve"] = proximo_dron_libre(getattr(self.ctrl, "name", "inst"))
        # al arrancar (o al relanzarse la ventana) no se vuelven a leer los
        # eventos si se leyeron hace poco: se sigue con lo que ya se sabe
        if not self._leido_sesion and \
                time.time() - est.get("lectura_t", 0) < _plan.LECTURA_RECIENTE:
            self._leido_sesion = True
        e = dict(est, _leido_sesion=self._leido_sesion, _pausa=self._pausa,
                 _ballenas_lider=self.b_rol in _cb.INVOCA,
                 _ballenas_pedido=self._pedido_ballenas(),
                 _ballenas_rol=self.b_rol,
                 _tanda_ballenas=self._tanda_otra(),
                 _sigilo_quedan=getattr(self, "_sigilo_quedan", False),
                 _sin_piratas_t=getattr(self, "_sin_piratas_t", 0),
                 _ballenas_prueba=str((self._prueba()[0] or {}).get("lider")) == self.puerto,
                 _gemas_pedidas=self._gemas_pedidas(est),
                 _drones_libres=drones_libres(getattr(self.ctrl, "name", "inst"), self.b_robots),
                 _dron_vuelve=proximo_dron_libre(getattr(self.ctrl, "name", "inst")))
        mem = self.mem if self._hay_ocr() else None
        return _plan.decidir(e, self.que, mem, opciones={"ocr": mem is not None,
                                                         "ballenas_dia": self.ballenas_dia,
                                                         "horario": self.horario})

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
        prox = self._proxima_espera(est)
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
            self._rec_paso += int(t.status.get("recogidas", 0) or 0)
            self._leido_sesion = True
            est["lectura_t"] = est["progreso_t"] = time.time()
        elif k == "progreso":
            t = self._tarea(LectorEventos)
            t.progreso_de(a.datos.get("evento", ""))
            self._rec_paso += int(t.status.get("recogidas", 0) or 0)
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
            lider, apoyo = self._lider_apoyo()
            tope = self.ballenas_dia
            tur, dp, rp = self._prueba()
            args = self._args_ballenas(lider, apoyo)
            if tur and self.puerto in (str(tur.get("lider")), str(tur.get("apoyo"))):
                lider, apoyo = str(tur.get("lider")), str(tur.get("apoyo"))
                args = {**self._args_ballenas(lider, apoyo), "sola": False}   # la prueba es de dos
            prueba = bool(a.datos.get("prueba")) and tur is not None
            if prueba:
                tope = hechas + 1                          # solo 1 ballena por turno
                self.log(f"Prueba de ballenas: invoco 1 y la matamos con {apoyo}.")
            t = self._tarea(Ballenas, **args, tope_dia=tope,
                            hechas_hoy=hechas, grupo_actual=getattr(self, "_grupo", None))
            for _k in ("ballenas", "gemas", "senuelos"):
                t.status[_k] = 0          # contadores puros: lo hecho en esta accion
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
                    est["ballenas_fallo"] = True
                else:
                    est["ballenas"] = {"dia": hoy, "n": hechas + n}
                    # sin ballena: mientras se espera al reintento, el sigilo puede ir
                    est["ballenas_fallo"] = n == 0
                    est["ballenas_prox"] = time.time() + (900 if n == 0 else 30)
                    # la recogida tarda 5 min + el viaje del robot: se sigue con
                    # otras cosas y el siguiente ciclo espera a que acabe
                    if n > 0:
                        est["ballenas_prox"] = time.time() + self.ESPERA_TRAS_TANDA
            else:
                t.ciclo_apoyo()
            self._sumar_bal(t)
            self._rec_paso += int(t.status.get("recogidas", 0) or 0)
            self._grupo = 2                                # Ballenas deja cargado el PVE
        elif k == "gemas":
            from tareas.ballenas.tarea import Ballenas
            lider, apoyo = self._lider_apoyo()
            t = self._tarea(Ballenas, **self._args_ballenas(lider, apoyo))
            for _k in ("ballenas", "gemas", "senuelos"):
                t.status[_k] = 0
            t.recoger_sueltas()
            self._sumar_bal(t)
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
            t.tanda = a.datos.get("tanda", "manana")
            t.run(1)
            d = est.get("destacamento", {})
            if d.get("dia") != hoy:
                d = {"dia": hoy}
            v = d.setdefault("visitas", {})
            v[t.tanda] = v.get(t.tanda, 0) + 1           # como mucho 2 por tanda
            d["ult"] = time.time()
            if t.status.get("ok"):
                d[t.tanda] = True                        # tanda hecha de verdad
            # la 2ª visita, cuando haya pasado el contador de «Procesando»
            fin = float(t.status.get("fin_proceso") or 0)
            est["destacamento_fin"] = fin
            if fin and v[t.tanda] < 2:
                self.log("  Destacamento: vuelvo cuando pase el contador, hacia las "
                         + time.strftime("%H:%M", time.localtime(fin)) + ".")
            est["destacamento"] = d
            self._rec_paso += int(t.status.get("recogidas", 0) or 0)
        elif k == "cosmomante":
            self._tarea(Cosmomante).run(1)
            est["cosmomante_t"] = time.time()
        elif k == "escombros" and self.ESCOMBROS_DE_BALLENAS:
            self._escombros_de_ballenas(est)
        elif k == "escombros":
            from tareas.restos import RecogerRestos
            libres = drones_libres(getattr(self.ctrl, "name", "inst"), self.b_robots)
            r = self._tarea(RecogerRestos).que_recoger(self.que.get("escombros", True), self.que.get("gemas"))
            n = r.run_sistema(cupo=libres) if libres else 0
            self._rec_paso += n
            self._apuntar_escombros(n)
            est["escombros_t"] = time.time()
        elif k in _plan.EVENTOS_JUEGO:
            t = self._tarea(LectorEventos)
            t.jugar_evento(a.datos.get("evento"), a.datos.get("nombre"))
            self._rec_paso += int(t.status.get("recogidas", 0) or 0)
            est[f"{k}_t"] = time.time()
        elif k == "roaming":
            from cerebro.roaming_rutina import RoamingRutina
            self._tarea(RoamingRutina, tickets=self.roaming_tickets).run(1)
            est["roaming_t"] = time.time()
        elif k == "simulacion":
            t = self._tarea(Simulacion)
            t.run(1)
            self._rec_paso += int(t.status.get("recogidas", 0) or 0)
            est["simulacion"] = hoy
            s = est.get("simulacion_tandas", {})
            if s.get("dia") != hoy:
                s = {"dia": hoy}
            s[a.datos.get("tanda") or "manana"] = True
            est["simulacion_tandas"] = s
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
                if self.b_rol not in _cb.INVOCA or not self.que.get("ballenas"):
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
            # mientras se ataca por una mision, se mira su progreso cada poco
            # (no solo cada hora) para parar al llegar a la meta y no pasarse
            ev = a.datos.get("evento")
            # si el evento no se ha podido abrir, no se reintenta en cada pasada
            # (cada intento recorre la lista entera): como mucho cada 10 min
            fallo_t = getattr(self, "_progreso_fallo", {}).get(ev, 0)
            if (ev and time.time() - self.mem.leido_t(ev) >= _plan.REVISAR_MISION_PIRATAS
                    and time.time() - fallo_t >= 600):
                self.log("  Miro cuánto falta en la misión antes de seguir atacando.")
                leida = LectorEventos(self.ctrl, log=self._log, stop=self.stop).progreso_de(ev)
                if not leida and not self.parado():
                    self._progreso_fallo = {**getattr(self, "_progreso_fallo", {}), ev: time.time()}
                    self.log("  No he podido mirar la misión; sigo y lo vuelvo a probar en 10 min.")
                pend = [p for p in self.mem.pendientes("fuerza_pirata") + self.mem.pendientes("piratas")
                        if p["evento"] == ev and p.get("actual") is not None]
                # sin leer no se sabe si esta completa: se sigue atacando
                if leida and not pend:
                    self.log("  La misión de piratas ya está completa: no ataco más.")
                    est["flotas_ya"] = True
                    self._guardar(est)
                    return
            t = self._tarea(PiratasNormales)
            # con memoria de misiones manda el planificador; sin ella, la
            # tarea mira la mision de Cosmomante como antes
            t.PARAR_MISION = bool(a.datos.get("sin_memoria"))
            t.run(_plan.POR_TANDA_NORMALES)
            self.status["normales"] = self.status.get("normales", 0) + int(t.status.get("ciclo", 0) or 0)
            self._contar(est, hoy)["pir_normales"] = self.status["normales"]
            self._recoger_escombros(t)
            if t.status.get("mision_hecha"):
                self._pausa["normales"] = _plan_proximo_dia()
            if t.status.get("sin_piratas"):
                self._sin_piratas_t = time.time()
            # flotas a casa solo si la mision esta hecha o no hay piratas (si no,
            # el planificador no las llama mientras la mision siga pendiente)
            if t.status.get("mision_hecha") or t.status.get("sin_piratas"):
                est["flotas_ya"] = True
        self._guardar(est)

    def _recoger_escombros(self, t):
        """Tras una tanda de piratas normales: si alguna mision pide restos,
        los drones recogen los escombros de los piratas ya muertos (los
        atacados hace mas de 45 s). Cada montón recogido se apunta en esas
        misiones (en las que no se vuelven a leer, como Artefactos, es la
        unica forma de saber cuando estan hechas)."""
        if not (self.que.get("escombros", True) or self.que.get("gemas")):
            return                                  # desactivado en Ajustes > Piratas
        pend = [p for p in self.mem.pendientes("recolectar") if p.get("actual") is not None]
        if not pend or self.parado():
            return
        ahora = time.time()
        puntos = [(x, y) for x, y, tt in getattr(t, "recientes", [])
                  if 45 <= ahora - tt <= t.RECIENTE_SEG - 60]
        if not puntos:
            return
        from tareas.restos import RecogerRestos
        r = self._tarea(RecogerRestos).que_recoger(self.que.get("escombros", True), self.que.get("gemas"))
        # primero por sus iconos (todos los del sistema); si no se ve ninguno,
        # donde murieron los piratas atacados
        from tareas.restos import iconos_restos
        if iconos_restos(r.vista_sistema()):
            n = r.recoger_iconos(drones_libres(getattr(self.ctrl, "name", "inst"), self.b_robots))
        else:
            n = r.run_en(puntos, cupo=drones_libres(getattr(self.ctrl, "name", "inst"), self.b_robots), img_ref=getattr(t, "_img_ant", None))
        self._rec_paso += n
        self._apuntar_escombros(n)

    def _apuntar_escombros(self, n):
        """Cada montón recogido cuenta en las misiones de restos pendientes."""
        if not n:
            return
        for p in [p for p in self.mem.pendientes("recolectar") if p.get("actual") is not None]:
            meta = p.get("meta") or p["mision"].get("meta")
            self.mem.apuntar_progreso(p["evento"], p["mision"]["id"], min(meta or 10 ** 9,
                                      (p.get("actual") or 0) + n), meta)

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
        antes = [self.status.get(x, 0) or 0 for x in CLAVES_STATUS]
        self._rec_paso = 0
        try:
            self._ejecutar(a, est)
            self._fallos[a.clave] = 0
            _est.sumar(cuenta, "ok")
            for x, v in zip(CLAVES_STATUS, antes, strict=False):
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

    def _proxima_espera(self, est) -> float:
        """Cuando volvera a haber algo que hacer (lo que muestra la tarjeta como «siguiente»)."""
        return _plan.proxima_espera(est, self.que)

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
            fin = min(self._proxima_espera(est), time.time() + 120)
            while time.time() < fin and not self.parado():
                time.sleep(2)
                self._tick()
                if self._pedido_ballenas():
                    break
        self._tick(forzar=True)
        self.status["estado"] = "parado"


class SoloBallenas(Rutina):
    """Tarea unica «Solo ballenas»: la Rutina con solo el paso de ballenas.

    No tiene ajustes propios: el rol (invoca/apoya), la pareja, los robots y el
    tope del dia son los de Ajustes > Ballenas, y las hechas hoy se cuentan en
    el MISMO estado de la Rutina (rutina_<cuenta>.json), asi que no se cuentan
    dos veces ni se salta el tope. Reutiliza _ejecutar (ciclo_lider/apoyo, esperas
    de recogida, reintentos) y las gemas pedidas."""
    NOMBRE = "Solo ballenas"
    SOLO = ("ballenas",)
    # aqui no hay otra cosa que hacer: si quedan ballenas, la siguiente tanda va
    # enseguida (los drones siguen fuera; lo que quede se recoge despues, con los
    # que vuelvan, con la tarea «escombros» del planificador)
    ESPERA_TRAS_TANDA = 5
    ESCOMBROS_DE_BALLENAS = True

    def _escombros_de_ballenas(self, est):
        """Recogida de lo que quede de las ballenas muertas hace menos de ~30 min:
        sus escombros (junto a los puntos de muerte guardados, con los minimos) y
        las gemas sueltas del mapa. Sin puntos recientes no recoge nada (no son
        escombros de ballena: serian de piratas o de otros)."""
        from tareas.ballenas.tarea import Ballenas
        lider, apoyo = self._lider_apoyo()
        t = self._tarea(Ballenas, **self._args_ballenas(lider, apoyo))
        puntos = t.puntos_muerte_recientes()
        if puntos:
            if self.b_escombros:
                t.recoger_escombros_muerte(puntos)
            if self.b_gemas:
                t.recoger_sueltas()
            self._rec_paso += int(t.status.get("recogidas", 0) or 0)
        est["escombros_t"] = time.time()

    def __init__(self, ctrl, *a, **kw):
        super().__init__(ctrl, *a, **kw)
        self.que = {k: k in self.SOLO for k in self.PASOS}
        # escombros del sistema mientras se espera la siguiente ballena (si la casilla
        # esta activa); sin leer eventos: el planificador no los espera para eso
        self.que["escombros"] = self.b_escombros
        self.que["gemas"] = self.b_gemas       # lo que quede de gemas, junto a los escombros
        self._leido_sesion = True

    def _decidir(self, est):
        acciones = super()._decidir(est)
        return [a for a in acciones if a.clave in ("ballenas", "ballenas_apoyo", "gemas", "escombros")]

    def _recogida_final(self, est):
        """Al llegar al tope del dia: esperar (como mucho 20 min) a que vuelva
        algun dron y recoger una vez lo que quede (escombros y gemas del
        sistema) antes de parar."""
        if not (self.b_escombros or self.b_gemas) or self.parado():
            return
        cuenta = getattr(self.ctrl, "name", "inst")
        vuelve = proximo_dron_libre(cuenta)
        if not drones_libres(cuenta, self.b_robots) and vuelve and 0 < vuelve - time.time() < 1200:
            self.log("Solo ballenas: espero a que vuelva algún dron para recoger lo que quede.")
            self.status["estado"] = "esperando a los drones"
            while time.time() < vuelve and not self.parado():
                time.sleep(2)
                self._tick()
        if self.parado() or not drones_libres(cuenta, self.b_robots):
            return
        self._accion_segura(_plan.Accion(0, "escombros", "recoger lo que quede tras las ballenas", {}), est)

    def run(self, ciclos: int = 0):
        if self.b_rol == "no":
            self.log("Solo ballenas: esta cuenta no tiene las ballenas configuradas. Pulsa "
                     "«Ajustes» de la cuenta y elige el modo en la pestaña Ballenas "
                     "(«Sola», «Invoca con ayuda» o «Ayuda a otra cuenta»).")
            self.status["estado"] = "sin configurar"
            return
        if self.b_rol in _cb.INVOCA and self.ballenas_dia <= 0:
            self.log("Solo ballenas: «Ballenas al día» está a 0: ponlo en Ajustes > Ballenas.")
            self.status["estado"] = "sin configurar"
            return
        if self.b_rol == "sola":
            self.log(f"Solo ballenas: esta cuenta invoca, mata y recoge sola, hasta "
                     f"{self.ballenas_dia} al día. Para pararlo, pulsa PARAR.")
        elif self.b_rol == "invoca":
            self.log(f"Solo ballenas: invoco y mato con la cuenta {self.b_con}, hasta "
                     f"{self.ballenas_dia} al día. Para pararlo, pulsa PARAR.")
        else:
            self.log(f"Solo ballenas: espero los pedidos de la cuenta {self.b_con} y la ayudo. "
                     "Para pararlo, pulsa PARAR.")
        self._t_ult = time.time()
        while not self.parado():
            self._tick()
            est = self._estado()
            hoy = _plan.dia_juego(time.time())
            cola = self._decidir(est)
            if cola:
                self._accion_segura(cola[0], est)
                if getattr(self, "_sin_imagen", False):
                    self.status["estado"] = "sin conexión"
                    return
                continue
            b = est.get("ballenas", {})
            hechas = b.get("n", 0) if b.get("dia") == hoy else 0
            if self.b_rol in _cb.INVOCA and hechas >= self.ballenas_dia:
                self._recogida_final(est)
                self.log(f"Solo ballenas: tope del día alcanzado ({hechas} de "
                         f"{self.ballenas_dia}). Paro.")
                self.status["estado"] = "tope alcanzado"
                break
            self.status["estado"] = "esperando"
            self._publicar(est, None, cola)
            fin = min(_plan.proxima_espera(est, self.que), time.time() + 120)
            while time.time() < fin and not self.parado():
                time.sleep(2)
                self._tick()
                if self._pedido_ballenas() or self._gemas_pedidas(est):
                    break
        self._tick(forzar=True)
        if self.status["estado"] != "tope alcanzado":
            self.status["estado"] = "parado"


def _plan_proximo_dia(hora=2) -> float:
    t = time.localtime()
    base = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, hora, 0, 0, 0, 0, -1))
    return base if base > time.time() else base + 86400


class SoloRecoleccion(Rutina):
    """Tarea unica «Recolección»: recoge SOLO gemas y/o escombros del sistema, lo que se
    marque en Ajustes > Recolección de la cuenta. Suministros gratis, recompensas y el
    resto de la Rutina no las hace (eso es de la Rutina o de sus tareas sueltas).

    Los escombros van por el planificador (los drones libres, cada ~10 min o cuando
    vuelve un dron). Las gemas las recoge Ballenas.recoger_sueltas con la vista de la
    cuenta (2D o 3D) cada CADA_GEMAS segundos si hay algun dron libre, o cuando se
    piden a mano (menu «Mas» > Recoger gemas)."""
    NOMBRE = "Recolección"
    COLECCION = ("escombros", "gemas")
    CADA_GEMAS = 5 * 60

    def __init__(self, ctrl, *a, **kw):
        super().__init__(ctrl, *a, **kw)
        # solo cuentan las casillas que se pasan marcadas (Ajustes > Recolección): la Rutina
        # rellena las que faltan con sus valores por defecto y aqui no deben colarse
        marcadas = kw.get("que") or {}
        self._elegidas = {k for k in self.COLECCION if marcadas.get(k)}
        self.recoger_gemas = "gemas" in self._elegidas
        self.que = {k: k in self._elegidas for k in self.PASOS}
        self.que["gemas"] = False                 # las gemas van por _gemas_pedidas (vista de la cuenta)
        self._leido_sesion = True                 # no hace falta leer los eventos para recoger

    def _gemas_pedidas(self, est) -> bool:
        """Gemas: por orden manual (Mas > Recoger gemas) o cada CADA_GEMAS con algun dron libre."""
        if not self.recoger_gemas:
            return False
        if super()._gemas_pedidas(est):
            return True
        if time.time() - est.get("gemas_t", 0) < self.CADA_GEMAS:
            return False
        return drones_libres(getattr(self.ctrl, "name", "inst"), self.b_robots) > 0

    def _decidir(self, est):
        acciones = super()._decidir(est)
        return [a for a in acciones if a.clave in self._elegidas]

    def run(self, ciclos: int = 0):
        que = " y ".join(n for k, n in (("gemas", "gemas"), ("escombros", "escombros")) if k in self._elegidas)
        if not que:
            self.log("Recolección: no hay nada marcado. Marca «Gemas» y/o «Escombros» en Ajustes > Recolección.")
            return
        self.log(f"Recolección: voy al visor del sistema (vista {self.vista.upper()}) y recojo {que} con los "
                 "drones libres; repito cada pocos minutos. Para pararla, pulsa PARAR.")
        super().run(ciclos)

    def _proxima_espera(self, est) -> float:
        """Solo lo de esta tarea: gemas cada CADA_GEMAS y escombros cada CADA_ESCOMBROS (o en cuanto
        vuelve un dron). Sin esto saldria la proxima lectura de eventos (horas), que aqui no se usa."""
        ahora = time.time()
        cand = []
        if self.recoger_gemas:
            cand.append(est.get("gemas_t", 0) + self.CADA_GEMAS)
        if "escombros" in self._elegidas:
            cand.append(est.get("escombros_t", 0) + _plan.CADA_ESCOMBROS)
            if est.get("_dron_vuelve"):
                cand.append(est["_dron_vuelve"])
        futuros = [c for c in cand if c > ahora]
        return min(futuros) if futuros else ahora + 120
