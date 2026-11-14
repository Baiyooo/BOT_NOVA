"""Proceso de trabajo de cada instancia: crea la tarea elegida y la ejecuta,
avisando a la ventana por una cola.
"""
from __future__ import annotations


def _publicar_detector(dev: str) -> None:
    """Escribe el estado del detector (procesador o grafica) para la ventana.

    Va a %LOCALAPPDATA%\\NovaBot\\detector_estado.json; la última cuenta que
    escribe es la que se ve. Nunca lanza excepciones."""
    try:
        import os
        import time as tm

        from nucleo import config as _cfg
        from nucleo.rutas import carpeta_datos
        from vision import percepcion
        est = percepcion.estado_detector()
        est["t"] = tm.time()
        est["cuenta"] = dev
        _cfg.guardar(os.path.join(carpeta_datos(), "detector_estado.json"), est)
    except Exception:                                   # noqa: BLE001
        pass


def trabajo_proceso(puerto, adb, cual, partidas, opc, cola, parada, pausa=None):
    """Se ejecuta en un PROCESO aparte por instancia: asi cada una usa su
    propio nucleo del procesador y van de verdad a la vez (con hilos, el
    reconocimiento de imagen de una frenaba a las demas)."""
    import threading as th
    import time as tm
    import cv2
    from nucleo import adb as _adb
    from tareas import roaming
    from cerebro import rutina
    from tareas.cosmomante import juego
    from tareas import eventos
    from tareas.piratas import mixto
    from tareas.piratas import normales
    from tareas.piratas import sigilo
    from tareas import recompensas
    from vision import experiencia
    cv2.setNumThreads(2)          # varios procesos a la vez: que no se pisen los nucleos
    try:                          # prioridad baja: el PC (y BlueStacks) siempre responde
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),
                                                0x00004000)   # BELOW_NORMAL_PRIORITY_CLASS
    except Exception:                               # noqa: BLE001
        pass
    dev = f"127.0.0.1:{puerto}"
    motor = None
    vivo = True

    def avisos():
        t_det = 0.0
        while vivo:
            if motor is not None:
                try:
                    cola.put(("st", puerto, dict(getattr(motor, "status", {}))))
                except Exception:                   # noqa: BLE001
                    pass
            # estado del detector para la pestaña Salud (cada 5 s basta: aqui
            # ya esta cargado en este proceso; la ventana solo lee el archivo)
            if tm.time() - t_det >= 5.0:
                t_det = tm.time()
                _publicar_detector(dev)
            tm.sleep(0.5)

    th.Thread(target=avisos, daemon=True).start()
    apunta = lambda i, m: cola.put(("log", i, m))   # noqa: E731
    try:
        juego.Cosmomante.NORMALES = bool(opc.get("dados", True))
        juego.Cosmomante.MULTIPLICADORES = bool(opc.get("mult", True))
        juego.Cosmomante.ASCENDER = bool(opc.get("ascender", True))
        sigilo.PiratasSigilo.DEFENSA = bool(opc.get("defensa", True))
        # la tarea suelta de piratas normales solo mata piratas: no entra en
        # los eventos a mirar la mision (eso lo decide la Rutina con lo leido)
        normales.PiratasNormales.PARAR_MISION = False
        # salto con la flota al lado de cada pirata normal (Ajustes > Piratas)
        normales.PiratasNormales.SALTO = bool(opc.get("salto_normales", False))
        ctrl = _adb.AdbController(dev, adb)
        ctrl.pausa, ctrl.parada = pausa, parada     # «Pausar» de la tarjeta
        if cual == "piratas":
            motor = sigilo.PiratasSigilo(ctrl, log=apunta, stop=parada,
                                     atacar=opc["atacar"], usar_salto=opc["salto"])
            motor.run(ciclos=partidas)
        elif cual == "normales":
            motor = normales.PiratasNormales(ctrl, log=apunta, stop=parada)
            motor.run(ciclos=partidas)
        elif cual == "mixto":
            motor = mixto.PiratasMixto(ctrl, log=apunta, stop=parada,
                                    atacar=opc["atacar"], usar_salto=opc["salto"])
            motor.run()
        elif cual in ("simulacion", "cosmomante", "cosmo", "recompensas", "eventos"):
            cls = {"simulacion": recompensas.Simulacion, "cosmomante": juego.Cosmomante,
                   "cosmo": juego.Cosmomante,
                   "recompensas": recompensas.Recompensas, "eventos": eventos.RecogerEventos}[cual]
            motor = cls(ctrl, log=apunta, stop=parada)
            motor.run()
        elif cual in ("rutina", "ballenas"):
            # «Solo ballenas» es la Rutina con solo ese paso: mismos ajustes y contador
            clase = rutina.SoloBallenas if cual == "ballenas" else rutina.Rutina
            motor = clase(ctrl, log=apunta, stop=parada,
                              normales=opc["normales"], usar_salto=opc["salto"],
                              que=opc.get("que"), ballenas_dia=opc.get("ballenas_dia", 2),
                              ballenas=opc.get("ballenas"),
                              roaming_tickets=opc.get("roaming_tickets", 0),
                              horario=opc.get("horario"))
            motor.run()
        else:
            motor = roaming.Bot(ctrl, on_log=apunta, stop_event=parada)
            motor.run(games=partidas or int(opc.get("roaming_tickets", 0) or 0))
    except _adb.SinConexion:
        if motor is not None and isinstance(getattr(motor, "status", None), dict):
            motor.status["estado"] = "sin conexión"
        # instancia cerrada o sin ADB: un aviso claro y un solo registro, sin
        # volver a intentar capturar (cada intento tarda varios segundos)
        cola.put(("log", dev, "No veo la pantalla de esta instancia de BlueStacks (cerrada, "
                              "minimizada o sin ADB). Paro; cuando esté abierta, pulsa EMPEZAR."))
        try:
            from nucleo import diagnostico as d_
            d_.registrar("SinConexion: la instancia no da imagen", cuenta=dev, tarea=cual,
                         accion="capturar la pantalla")
        except Exception:                           # noqa: BLE001
            pass
    except Exception as e:                          # noqa: BLE001
        cola.put(("log", dev, f"ERROR: {e}"))
        try:
            from nucleo import estadisticas as e_
            e_.sumar(dev, "errores")
        except Exception:                           # noqa: BLE001
            pass
        try:
            import traceback
            from nucleo import diagnostico as d_
            img = None
            try:
                img = ctrl.capture()
            except Exception:                       # noqa: BLE001
                pass
            d_.registrar("".join(traceback.format_exception_only(type(e), e)).strip()
                         + " | " + " > ".join(f"{fr.name}:{fr.lineno}"
                                              for fr in traceback.extract_tb(e.__traceback__)[-3:]),
                         cuenta=dev, tarea=cual, accion="ejecutar la tarea", img=img)
        except Exception:                           # noqa: BLE001
            pass
    finally:
        try:
            experiencia.experiencia().guardar()              # lo aprendido, para la proxima vez
        except Exception:                           # noqa: BLE001
            pass
        if motor is not None:
            cola.put(("st", puerto, dict(getattr(motor, "status", {}))))
        vivo = False
