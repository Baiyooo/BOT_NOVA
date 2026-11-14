"""La configuracion de ballenas de una cuenta, en UN solo sitio.

La leen la Rutina, la tarea «Solo ballenas», el dialogo de Ajustes y el
resumen de la tarjeta; asi no hay copias de los ajustes. Se guarda en las
preferencias ("ballenas": {puerto: {...}}):

    rol      "sola" (invoca, mata y recoge ella sola), "invoca" (con ayuda de
             otra cuenta), "apoya" (ayuda a otra cuenta) o "no"
    con      puerto de la cuenta pareja (solo invoca / apoya)
    robots   drones que manda a recoger gemas
    dia      ballenas al dia (tope)
    grupo    cargar el grupo de batalla 2 antes de empezar
    reparar  reparar las naves al acabar la tanda
    gemas    recoger las gemas
    escombros  recoger tambien los escombros que sueltan (mineral, aleacion,
             cristal; nunca Nucleos), con los drones que queden libres
    min_mineral / min_cristal / min_aleacion
             minimo en millones que debe superar cada escombro de ballena
             (por defecto 18 / 2 / 1); lo demas se deja

Los ajustes de antes ("rol", "con", "robots", "dia") siguen valiendo tal cual:
invoca = «con ayuda», apoya = «ayuda»; lo nuevo toma valores por defecto que
dejan el comportamiento de siempre.
"""
from __future__ import annotations

import os

from nucleo import config as _cfg
from nucleo.rutas import carpeta_diag

#  (valor guardado, texto del desplegable)
MODOS = (("sola", "Sola (esta cuenta invoca, mata y recoge)"),
         ("invoca", "Invoca con ayuda de otra cuenta"),
         ("apoya", "Ayuda a otra cuenta"),
         ("no", "Desactivado"))
NOMBRE_MODO = dict(MODOS)
MODO_DE_NOMBRE = {v: k for k, v in MODOS}
CON_PAREJA = ("invoca", "apoya")            # los modos que necesitan cuenta pareja
INVOCA = ("sola", "invoca")                 # los modos en que esta cuenta invoca


def _entero(valor, defecto: int) -> int:
    """int() que no revienta con None, "" o texto: devuelve el defecto."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return defecto


def _decimal(valor, defecto: float) -> float:
    """float() que no revienta con None, "" o texto (acepta la coma decimal)."""
    try:
        v = float(str(valor).replace(",", ".")) if isinstance(valor, str) else float(valor)
    except (TypeError, ValueError):
        return defecto
    return v if v == v and v not in (float("inf"), float("-inf")) else defecto


def aplicar(cfg: dict, puerto, nuevo: dict) -> tuple[str, list[str]]:
    """Guarda en cfg (el dict {puerto: ajuste}) los ajustes `nuevo` de la
    cuenta `puerto` y deja coherentes las parejas, igual desde Ajustes que
    desde el panel remoto: libera la pareja anterior de esta cuenta, libera
    tambien la pareja antigua de la cuenta con la que se empareja (o la saca
    de «sola») y deja a esa cuenta con el papel contrario.
    Devuelve (cuenta pareja o "", avisos en texto de lo que se ha liberado)."""
    p = str(puerto)
    avisos: list[str] = []
    c = normalizar(nuevo)
    viejo = str((cfg.get(p) or {}).get("con") or "")
    cfg[p] = c
    con = c["con"]
    if viejo and viejo != con and (cfg.get(viejo) or {}).get("con") == p:
        cfg[viejo] = {**normalizar(cfg[viejo]), "rol": "no", "con": ""}      # pareja anterior libre
        avisos.append(f"la cuenta {viejo} queda sin pareja")
    if c["rol"] not in CON_PAREJA:
        return "", avisos
    otro = cfg.get(con) or {}
    previa = str(otro.get("con") or "")
    if previa and previa != p and (cfg.get(previa) or {}).get("con") == con:
        cfg[previa] = {**normalizar(cfg[previa]), "rol": "no", "con": ""}    # su pareja antigua
        avisos.append(f"la cuenta {previa} deja de ser pareja de {con}")
    if otro.get("rol") == "sola":
        avisos.append(f"la cuenta {con} deja de ir sola")
    cfg[con] = normalizar({**otro, "rol": "apoya" if c["rol"] == "invoca" else "invoca", "con": p})
    return con, avisos


def normalizar(cfg) -> dict:
    """La configuracion con todos sus campos (los que falten, por defecto)."""
    c = dict(cfg or {})
    rol = c.get("rol", "no")
    if rol not in NOMBRE_MODO:
        rol = "no"
    con = str(c.get("con") or "")
    if rol in CON_PAREJA and not con:
        rol = "no"                          # sin pareja guardada no hay ballenas
    dia = c.get("dia")
    return {"rol": rol, "con": con if rol in CON_PAREJA else "",
            "robots": max(0, _entero(c.get("robots"), 6)),
            "dia": max(0, _entero(dia, 2)),         # si falta, 2 (un 0 puesto a mano se respeta)
            "grupo": bool(c.get("grupo", True)),
            "reparar": bool(c.get("reparar", True)),
            "gemas": bool(c.get("gemas", True)),
            "escombros": bool(c.get("escombros", True)),
            # minimo (en millones) que debe superar un escombro de ballena para recogerlo
            "min_mineral": max(0.0, _decimal(c.get("min_mineral"), 18.0)),
            "min_cristal": max(0.0, _decimal(c.get("min_cristal"), 2.0)),
            "min_aleacion": max(0.0, _decimal(c.get("min_aleacion"), 1.0))}


def minimos_unidades(cfg) -> dict:
    """Los minimos de escombros de ballenas en unidades: {tipo: cantidad}."""
    c = normalizar(cfg)
    return {t: int(round(c[f"min_{t}"] * 1_000_000)) for t in ("mineral", "cristal", "aleacion")}


def ruta_estado(nombre_cuenta) -> str:
    """Archivo de estado de la Rutina de una cuenta (donde se cuentan las
    ballenas hechas hoy; lo comparten la Rutina y «Solo ballenas»)."""
    nombre = str(nombre_cuenta).replace(":", "_")
    return os.path.join(os.path.dirname(carpeta_diag()), f"rutina_{nombre}.json")


def hechas_hoy(nombre_cuenta) -> int:
    """Ballenas muertas hoy (el dia del juego cambia a las 02:00)."""
    import time
    from cerebro.planificador import dia_juego
    b = _cfg.leer_config(ruta_estado(nombre_cuenta)).get("ballenas", {})
    return int(b.get("n", 0)) if b.get("dia") == dia_juego(time.time()) else 0


def resumen(cfg, nombres: dict | None = None, hechas: int | None = None,
            robots_max: int | None = None) -> str:
    """Una linea legible: «Sola · 2 al día (llevo 0) · 6 drones · gemas: sí»."""
    c = normalizar(cfg)
    nombres = nombres or {}
    if c["rol"] == "no":
        return "Sin configurar: pulsa Ajustes"
    pareja = nombres.get(c["con"], c["con"])
    sn = lambda v: "sí" if v else "no"                        # noqa: E731
    esc = f"escombros: {sn(c['escombros'])}"
    if c["escombros"]:                                        # los minimos: mineral/cristal/aleacion
        esc += " (>" + "/".join(f"{c[k]:g}" for k in ("min_mineral", "min_cristal", "min_aleacion")) + " M)"
    recoge = [f"{c['robots']} drones", f"gemas: {sn(c['gemas'])}", esc]
    if c["rol"] == "sola":
        partes = ["Sola"]
    elif c["rol"] == "invoca":
        partes = [f"Con {pareja} (invoca)"]
    else:
        return " · ".join([f"Ayuda a {pareja}"] + recoge)
    dia = f"{c['dia']} al día"
    if hechas is not None:
        dia += f" (llevo {hechas})"
    return " · ".join(partes + [dia] + recoge)
