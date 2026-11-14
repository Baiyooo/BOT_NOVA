"""El planificador de la Rutina: mira el estado y decide que toca AHORA.

No sigue una lista fija. Cada vez que acaba una accion, puntua todas las
posibles y elige la de mas valor. Las reglas del bot son limites fijos
(nunca gastar GEC, ni construir naves, ni abrir cajas: esas misiones ni
siquiera llegan aqui). Todo es logica pura y se puede probar sin el juego.

Puntos (mas = antes):
  100  leer eventos nuevos / al arrancar (sin saber que piden no se decide bien)
   92  recoger recompensas de un evento que cierra en menos de 1 h
   90  suministros gratis cuando acaba su temporizador
   85  simulacion del dia (en cuanto se arranca, sin esperar a una hora)
   84  destacamento: tanda de la manana (9-17) y de la tarde (17-1)
   80  recompensas diarias
   70  recoger recompensas de eventos (cada 6 h)
   60  piratas de sigilo (cada 30 min; siempre, sin tope)
   55  ballenas de eter (si estan activadas)
   40+ piratas normales SOLO si un evento activo pide fuerza pirata y esta
       cuenta no la ha completado; +30 si ese evento cierra en menos de 24 h
   50+ volver a leer el progreso de las misiones del bot (cada 2 h)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(order=True)
class Accion:
    puntos: float
    clave: str = field(compare=False)
    motivo: str = field(compare=False, default="")
    datos: dict = field(compare=False, default_factory=dict)


NOMBRES = {"leer_eventos": "Leer eventos y misiones", "gratis": "Suministros gratis",
           "recompensas": "Recompensas diarias", "eventos": "Recompensas de eventos",
           "simulacion": "Simulación", "destacamento": "Destacamento",
           "sigilo": "Piratas de sigilo", "normales": "Piratas normales",
           "progreso": "Progreso de misiones", "ballenas": "Ballenas de éter",
           "ballenas_apoyo": "Ballenas de éter (apoyo)",
           "cosmomante": "Cosmomante", "roaming": "Roaming Test",
           "artefactos": "Artefactos", "bingo": "Bingo Estelar",
           "escombros": "Recoger escombros",
           "llamar_flotas": "Llamar flotas paradas",
           "gemas": "Recoger gemas"}

CADA_LECTURA = 6 * 3600
CADA_EVENTOS = 6 * 3600
CADA_SIGILO = 30 * 60
CADA_GRATIS = 30 * 60
CADA_PROGRESO = 3600            # mirar cuanto falta en una mision del bot (cada hora)
PROGRESO_COMPLETO = 6 * 3600    # evento con todo completado: comprobarlo cada 6 h
REVISAR_MISION_PIRATAS = 20 * 60   # atacando por una mision: mirar su progreso cada 20 min
LECTURA_RECIENTE = 2 * 3600     # al arrancar, no releer si se leyo hace menos
CADA_COSMO = 6 * 3600
CADA_ROAMING = 6 * 3600
CADA_EVENTO_JUEGO = 6 * 3600    # Artefactos, Bingo Estelar: entrar a jugar
CADA_ESCOMBROS = 10 * 60        # mirar si hay escombros (solo con algun dron libre)
#  eventos que se juegan desde la Rutina: paso -> (evento, nombre, lo que hace)
EVENTOS_JUEGO = {"artefactos": ("artefactos", "Artefactos",
                                "«Buscar» con todo el encendido"),
                 "bingo": ("bingo_estelar", "Bingo Estelar", "sus misiones")}
DESTACAMENTO_REINTENTO = 3 * 3600   # 2ª visita si la 1ª no pudo y no hay contador         # Roaming Test: jugar los tickets
CADA_FLOTAS = 5 * 60            # flotas inactivas fuera: se miran cada 5 min
POR_TANDA_NORMALES = 6          # ataques por vuelta antes de volver a decidir


def dia_juego(ahora: float) -> str:
    """El dia del juego cambia a las 02:00 (hora de Espana)."""
    return time.strftime("%Y-%m-%d", time.localtime(ahora - 2 * 3600))


def tanda_destacamento(ahora: float) -> str | None:
    """'manana' o 'tarde' (3 intentos cada una); fuera, None.
    El juego va por hora UTC: la tarde empieza a las 16:00 UTC, que en España
    son las 17:00 en invierno y las 18:00 en verano. Mañana: 8:00-16:00 UTC
    (9-17 h en invierno); tarde: 16:00-24:00 UTC (hasta la 1 o las 2)."""
    h = time.gmtime(ahora).tm_hour
    if 8 <= h < 16:
        return "manana"
    if h >= 16:
        return "tarde"
    return None


def franja_activa(franjas, ahora: float) -> bool:
    """Si la hora local de `ahora` cae dentro de alguna franja.

    Cada franja es [hora_desde, hora_hasta) en horas; si fin < inicio, cruza
    la medianoche (p.ej. [22, 6])."""
    h = time.localtime(ahora)
    minutos = h.tm_hour * 60 + h.tm_min
    for franja in franjas or []:
        try:
            ini, fin = int(franja[0]) * 60, int(franja[1]) * 60
        except (TypeError, ValueError, IndexError):
            continue
        if ini == fin:
            continue
        if (ini <= minutos < fin) if ini < fin else (minutos >= ini or minutos < fin):
            return True
    return False


def en_franja_bloqueada(horario: dict, clave: str, ahora: float) -> bool:
    """Si la tarea `clave` no se debe hacer a esta hora (horario de la cuenta).

    horario: {"sigilo": [[2, 8]], "ballenas": [[0, 6], [23, 24]]...} en horas
    locales. Sin horario guardado, nunca se bloquea nada."""
    return bool(horario) and franja_activa((horario or {}).get(clave), ahora)


def decidir(est: dict, que: dict, mem=None, ahora: float | None = None,
            opciones: dict | None = None) -> list[Accion]:
    """Todas las acciones posibles ahora, de mayor a menor valor.

    est: el estado guardado de la Rutina (rutina_<cuenta>.json).
    que: pasos activados en Ajustes (gratis, recompensas, eventos, simulacion,
         sigilo, normales, destacamento, ballenas, cosmomante).
    mem: memoria_eventos.Memoria de la cuenta (o None si no hay OCR).
    opciones: ocr, ballenas_dia y horario ({"tarea": [[desde, hasta]]}, horas
    locales en las que esa tarea NO se hace)."""
    ahora = time.time() if ahora is None else ahora
    opciones = opciones or {}
    hoy = dia_juego(ahora)
    pausa = est.get("_pausa", {})
    horario = opciones.get("horario") or {}
    out: list[Accion] = []

    def add(p, k, motivo, **datos):
        if pausa.get(k, 0) > ahora:
            return
        if en_franja_bloqueada(horario, k, ahora):
            return                                  # fuera de su horario (Ajustes > Horario)
        out.append(Accion(p, k, motivo, datos))

    activos = mem.activos(ahora) if mem is not None else []

    # 1) saber que hay: al arrancar, cada 6 h y cuando cierra algun evento
    if mem is not None and opciones.get("ocr", True):
        ult = est.get("lectura_t", 0)
        cerro = any(e.get("fin") and ult < e["fin"] <= ahora for e in mem.eventos().values())
        sin_leer = any(mem.necesita_leer(e["clave"]) for e in activos)
        if not est.get("_leido_sesion") or ahora - ult >= CADA_LECTURA or cerro or sin_leer:
            if not (sin_leer and est.get("_leido_sesion") and ahora - ult < 600):
                add(100, "leer_eventos", "saber qué eventos hay y qué piden")

    # 2) recompensas de eventos: antes de que cierre uno, o cada 6 h
    if que.get("eventos"):
        ult = est.get("eventos_t", 0)
        cierra = [e for e in activos if e.get("fin") and 0 < e["fin"] - ahora < 3600]
        if cierra and ahora - ult > 1800:
            add(92, "eventos", f"«{cierra[0].get('nombre')}» cierra en menos de 1 h")
        elif ahora - ult >= CADA_EVENTOS:
            add(70, "eventos", "toca recoger las recompensas de los eventos")

    # 3) suministros gratis
    if que.get("gratis"):
        prox = est.get("gratis_prox", 0) if est.get("gratis_prox", 0) > est.get("gratis_t", 0) \
            else est.get("gratis_t", 0) + CADA_GRATIS
        if prox <= ahora:
            add(90, "gratis", "su temporizador ha acabado")

    # 4) lo diario: en cuanto se arranca, sin esperar a una hora fija
    #    simulacion: una revision por la mañana y otra por la tarde
    tanda_hoy = tanda_destacamento(ahora)
    nombre_tanda = {"manana": "mañana", "tarde": "tarde"}.get(tanda_hoy, "")
    if que.get("simulacion") and tanda_hoy:
        s = est.get("simulacion_tandas", {})
        if s.get("dia") != hoy:
            s = {}
        if not s.get(tanda_hoy):
            add(85, "simulacion", f"revisión de la {nombre_tanda}", tanda=tanda_hoy)
    if que.get("recompensas") and est.get("recompensas") != hoy:
        add(80, "recompensas", "aún no recogidas hoy")
    if que.get("destacamento"):
        tanda = tanda_destacamento(ahora)
        hechas = est.get("destacamento", {})
        if tanda and hechas.get("dia") != hoy:
            hechas = {}
        # como mucho 2 visitas por tanda: la primera lanza las 3 misiones; la
        # segunda, cuando ha pasado su contador, pulsa «Completo» (a 0)
        visitas = (hechas.get("visitas") or {}).get(tanda, 0) if tanda else 2
        fin = est.get("destacamento_fin") or 0
        if visitas == 0:
            add(84, "destacamento", f"revisión de la {nombre_tanda}", tanda=tanda)
        elif visitas == 1:
            if fin and ahora >= fin:
                add(83, "destacamento", "ha pasado el contador: pulsar «Completo»", tanda=tanda)
            elif not fin and not hechas.get(tanda) and                     ahora - hechas.get("ult", 0) >= DESTACAMENTO_REINTENTO:
                add(83, "destacamento", f"segunda revisión de la {nombre_tanda}", tanda=tanda)

    # 5) Cosmomante (evento semanal con su propia tarea)
    if que.get("cosmomante") and ahora - est.get("cosmomante_t", 0) >= CADA_COSMO:
        if mem is None or any(e["clave"] == "cosmomante" for e in activos) or not activos:
            add(65, "cosmomante", "tiradas gratis, metas y estrategia")

    # 5a) Roaming Test (evento Neural Roaming): jugar los tickets
    if que.get("roaming") and ahora - est.get("roaming_t", 0) >= CADA_ROAMING:
        if mem is None or any(e["clave"] == "neural_roaming" for e in activos) or not activos:
            add(64, "roaming", "jugar los tickets del Roaming Test")

    # 5c) eventos con juego propio (Artefactos, Bingo Estelar): cada 6 h
    for paso, (ev_k, ev_n, que_hace) in EVENTOS_JUEGO.items():
        if que.get(paso) and ahora - est.get(f"{paso}_t", 0) >= CADA_EVENTO_JUEGO:
            if mem is None or any(e["clave"] == ev_k for e in activos):
                add(63, paso, que_hace, evento=ev_k, nombre=ev_n)

    # 5d) escombros (y gemas) del sistema con los drones, aunque esta cuenta no
    #     haya matado nada: solo si queda algun dron libre (cada uno lleva su
    #     contador: ida + 5 min recogiendo + vuelta)
    if (que.get("escombros", True) or que.get("gemas")) and est.get("_leido_sesion") \
            and est.get("_drones_libres", 1) > 0 \
            and ahora - est.get("escombros_t", 0) >= CADA_ESCOMBROS:
        add(55, "escombros", f"mandar los drones a los escombros ({est.get('_drones_libres', '?')} libre(s))")

    # 5b) flotas paradas fuera de la estacion: se llaman de vuelta (cada 5 min)
    # pero NO mientras quedan busquedas de radar de sigilo, ni mientras se hace
    # la mision de fuerza pirata (salvo que no se encuentren piratas)
    pend_norm = []
    if que.get("normales") and mem is not None:
        pend_norm = [p for p in mem.pendientes("fuerza_pirata", ahora) + mem.pendientes("piratas", ahora)
                     if p.get("actual") is not None and p.get("meta")]
    ocupadas = est.get("_sigilo_quedan") or (pend_norm and ahora - est.get("_sin_piratas_t", 0) > 1800)
    if que.get("llamar_flotas", True) and est.get("flotas_ya"):
        # acaba de terminar (o cortarse) una tanda de piratas: las flotas se han
        # quedado fuera; se llaman antes que cualquier otra cosa (salvo ballenas)
        add(101, "llamar_flotas", "acaban de terminar los piratas: flotas a casa")
    elif que.get("llamar_flotas", True) and (que.get("sigilo") or que.get("normales") or que.get("ballenas")) \
            and ahora - est.get("flotas_t", 0) >= CADA_FLOTAS and est.get("_leido_sesion") \
            and not ocupadas:
        add(75, "llamar_flotas", "que no se queden flotas paradas molestando en el sistema")

    # 6) piratas de sigilo: siempre que se pueda, cada 30 min (radar +1/h)
    # mientras haya una tanda de ballenas en marcha (falta llegar al tope del
    # dia, o la otra cuenta esta encadenando ballenas) no se hace sigilo: cambia
    # el grupo de batalla y luego hay que volver a cargar el PVE (muy lento)
    tanda = est.get("_tanda_ballenas")
    if que.get("ballenas") and est.get("_ballenas_lider"):
        b = est.get("ballenas", {})
        hechas_b = b.get("n", 0) if b.get("dia") == hoy else 0
        # si el ultimo intento de ballena ha fallado (sin ballena o sin
        # respuesta de la otra cuenta), no se bloquea el sigilo mientras espera
        tanda = tanda or (hechas_b < int(opciones.get("ballenas_dia", 2) or 0)
                          and not est.get("ballenas_fallo"))
    if que.get("sigilo") and ahora - est.get("sigilo_t", 0) >= CADA_SIGILO and not tanda:
        add(60, "sigilo", "hay búsquedas de radar nuevas")

    # 7) ballenas de eter: la cuenta que invoca, hasta el tope del dia; la otra
    #    responde enseguida cuando se lo piden (sin ella no se ataca)
    if est.get("_ballenas_prueba"):
        add(104, "ballenas", "prueba de ballenas: invocar 1 y matarla entre las dos",
            prueba=True)
    if est.get("_gemas_pedidas"):
        add(102, "gemas", "recoger las gemas que hay en el sistema")
    if est.get("_ballenas_pedido"):
        add(104, "ballenas_apoyo", "la otra cuenta va a por ballenas y me necesita")
    if que.get("ballenas") and est.get("_ballenas_lider"):
        tope = int(opciones.get("ballenas_dia", 2) or 0)
        b = est.get("ballenas", {})
        hechas = b.get("n", 0) if b.get("dia") == hoy else 0
        if hechas < tope and est.get("ballenas_prox", 0) <= ahora:
            # las ballenas van antes que cualquier otra tarea
            add(103, "ballenas", f"llevo {hechas} de {tope} hoy: invocar, matar y recoger gemas",
                hechas=hechas, tope=tope)

    # 8) piratas normales: solo mientras un evento pida fuerza pirata
    if que.get("normales"):
        if mem is None or not activos or not any(e.get("misiones") is not None for e in activos):
            # sin memoria de misiones: como antes (la tarea mira la mision ella misma)
            add(40, "normales", "relleno entre tareas", sin_memoria=True)
        else:
            pend = (mem.pendientes("fuerza_pirata", ahora) + mem.pendientes("piratas", ahora)
                    + (mem.pendientes("recolectar", ahora) if que.get("escombros", True) else []))
            #   (los escombros salen de los piratas: si se recogen, tambien cuentan)
            # solo si se SABE que falta (progreso leido y por debajo de la meta);
            # si no se ha podido leer, primero se vuelve a mirar la mision
            pend = [p for p in pend if p.get("actual") is not None and p.get("meta")]
            if pend:
                p = pend[0]
                urg = 30 if p.get("fin") and p["fin"] - ahora < 86400 else 0
                falta = ""
                if p.get("meta") and p.get("actual") is not None:
                    falta = f" ({p['actual']:,}/{p['meta']:,})".replace(",", ".")
                add(40 + urg, "normales", f"misión de «{p['nombre']}»{falta}",
                    evento=p["evento"])

    # 9) releer el progreso de las misiones que hace el bot: cada hora si
    #    falta algo (empezando por el evento que cierra antes); si en un
    #    evento ya esta todo completado, solo se comprueba cada 6 h
    if mem is not None:
        from cerebro.memoria_eventos import LEER_UNA_VEZ
        pend = [p for p in mem.pendientes(None, ahora) if p["evento"] not in LEER_UNA_VEZ]
        if pend and ahora - est.get("progreso_t", 0) >= CADA_PROGRESO:
            p = pend[0]
            urg = 30 if p.get("fin") and p["fin"] - ahora < 86400 else 0
            add(50 + urg, "progreso", f"ver cuánto falta en «{p['nombre']}»", evento=p["evento"])
        else:
            con_pend = {p["evento"] for p in pend}
            hechos = [k for k in mem.con_misiones_del_bot(ahora)
                      if k not in con_pend and ahora - mem.leido_t(k) >= PROGRESO_COMPLETO]
            if hechos:
                add(45, "progreso", "todo completado: lo compruebo (cada 6 h)", evento=hechos[0])
    return sorted(out, reverse=True)


def proxima_espera(est: dict, que: dict, ahora: float | None = None) -> float:
    """Cuando volvera a haber algo que hacer (para dormir hasta entonces)."""
    ahora = time.time() if ahora is None else ahora
    cand = []
    if que.get("gratis"):
        cand.append(est.get("gratis_prox", 0) if est.get("gratis_prox", 0) > est.get("gratis_t", 0)
                    else est.get("gratis_t", 0) + CADA_GRATIS)
    if que.get("sigilo"):
        cand.append(est.get("sigilo_t", 0) + CADA_SIGILO)
    if que.get("eventos"):
        cand.append(est.get("eventos_t", 0) + CADA_EVENTOS)
    if que.get("ballenas") and est.get("_ballenas_lider"):
        cand.append(est.get("ballenas_prox", 0))
    if que.get("llamar_flotas", True) and (que.get("sigilo") or que.get("normales") or que.get("ballenas")):
        cand.append(est.get("flotas_t", 0) + CADA_FLOTAS)
    cand.append(est.get("lectura_t", 0) + CADA_LECTURA)
    if que.get("escombros", True) and est.get("_dron_vuelve"):
        cand.append(est["_dron_vuelve"])            # en cuanto vuelve un dron
    futuros = [c for c in cand if c > ahora]
    return min(futuros) if futuros else ahora + 120
