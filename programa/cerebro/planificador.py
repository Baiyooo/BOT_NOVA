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
   50+ volver a leer el progreso de las misiones del bot (cada 30 min)
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
           "cosmomante": "Cosmomante", "llamar_flotas": "Llamar flotas paradas",
           "gemas": "Recoger gemas"}

CADA_LECTURA = 6 * 3600
CADA_EVENTOS = 6 * 3600
CADA_SIGILO = 30 * 60
CADA_GRATIS = 30 * 60
CADA_PROGRESO = 30 * 60
CADA_COSMO = 6 * 3600
CADA_FLOTAS = 5 * 60            # flotas inactivas fuera: se miran cada 5 min
POR_TANDA_NORMALES = 6          # ataques por vuelta antes de volver a decidir


def dia_juego(ahora: float) -> str:
    """El dia del juego cambia a las 02:00 (hora de Espana)."""
    return time.strftime("%Y-%m-%d", time.localtime(ahora - 2 * 3600))


def tanda_destacamento(ahora: float) -> str | None:
    """'manana' de 9:00 a 17:00, 'tarde' de 17:01 a 1:00; fuera, None."""
    h = time.localtime(ahora).tm_hour
    if 9 <= h < 17:
        return "manana"
    if h >= 17 or h < 1:
        return "tarde"
    return None


def decidir(est: dict, que: dict, mem=None, ahora: float | None = None,
            opciones: dict | None = None) -> list[Accion]:
    """Todas las acciones posibles ahora, de mayor a menor valor.

    est: el estado guardado de la Rutina (rutina_<cuenta>.json).
    que: pasos activados en Ajustes (gratis, recompensas, eventos, simulacion,
         sigilo, normales, destacamento, ballenas, cosmomante).
    mem: memoria_eventos.Memoria de la cuenta (o None si no hay OCR)."""
    ahora = time.time() if ahora is None else ahora
    opciones = opciones or {}
    hoy = dia_juego(ahora)
    pausa = est.get("_pausa", {})
    out: list[Accion] = []

    def add(p, k, motivo, **datos):
        if pausa.get(k, 0) > ahora:
            return
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
    if que.get("simulacion") and est.get("simulacion") != hoy:
        add(85, "simulacion", "aún no hecha hoy")
    if que.get("recompensas") and est.get("recompensas") != hoy:
        add(80, "recompensas", "aún no recogidas hoy")
    if que.get("destacamento"):
        tanda = tanda_destacamento(ahora)
        hechas = est.get("destacamento", {})
        if tanda and hechas.get("dia") != hoy:
            hechas = {}
        if tanda and not hechas.get(tanda):
            add(84, "destacamento", f"tanda de la {'mañana' if tanda == 'manana' else 'tarde'}",
                tanda=tanda)

    # 5) Cosmomante (evento semanal con su propia tarea)
    if que.get("cosmomante") and ahora - est.get("cosmomante_t", 0) >= CADA_COSMO:
        if mem is None or any(e["clave"] == "cosmomante" for e in activos) or not activos:
            add(65, "cosmomante", "tiradas gratis, metas y estrategia")

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
        tanda = tanda or hechas_b < int(opciones.get("ballenas_dia", 2) or 0)
    if que.get("sigilo") and ahora - est.get("sigilo_t", 0) >= CADA_SIGILO and not tanda:
        add(60, "sigilo", "hay búsquedas de radar nuevas")

    # 7) ballenas de eter: la cuenta que invoca, hasta el tope del dia; la otra
    #    responde enseguida cuando se lo piden (sin ella no se ataca)
    if est.get("_ballenas_prueba"):
        add(104, "ballenas", "prueba de ballenas: invocar 1 y matarla entre las dos",
            prueba=True)
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
            pend = mem.pendientes("fuerza_pirata", ahora) + mem.pendientes("piratas", ahora)
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

    # 9) releer el progreso de las misiones que hace el bot (cada 30 min),
    #    empezando por el evento que cierra antes: asi se sabe que falta
    if mem is not None and ahora - est.get("progreso_t", 0) >= CADA_PROGRESO:
        pend = mem.pendientes(None, ahora)
        if pend:
            p = pend[0]
            urg = 30 if p.get("fin") and p["fin"] - ahora < 86400 else 0
            add(50 + urg, "progreso", f"ver cuánto falta en «{p['nombre']}»", evento=p["evento"])
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
    futuros = [c for c in cand if c > ahora]
    return min(futuros) if futuros else ahora + 120
