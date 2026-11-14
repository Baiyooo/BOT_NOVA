"""Localizar rotulos y botones del juego por su silueta (plantillas a varias
escalas, con cache de la escala que funciona en cada resolucion).
"""
from __future__ import annotations

import cv2
import numpy as np

from vision.recursos import silueta
from vision.mascaras import mascara_ambar, mascara_ambar_claro, mascara_blanco, mascara_claro, mascara_gris, mascara_rojo, mascara_texto, mascara_verde


# ---------------------------------------------------------------------------
# Las siluetas de los rotulos (antes aqui en base64) estan en
# recursos/rotulos/<nombre>.png; las muestras de cifras, en recursos/cifras.
# ---------------------------------------------------------------------------
SIGILO_ANCHO_REF = 1386       # ancho de la captura de la que se midio todo


#  nombre -> (silueta, color del texto, ancho de la captura de origen)
#  Unas se sacaron de grabaciones de 1386 de ancho y otras de 1896; con ese
#  dato se calcula la escala de partida y se prueba alrededor.
ROTULOS = {
    "sigilo": (silueta("sigilo"), mascara_texto, 1386),
    "atacar": (silueta("atacar"), mascara_blanco, 1386),
    "atras": (silueta("atras"), mascara_ambar, 1386),
    "radar": (silueta("radar"), mascara_ambar, 1386),
    "mira": (silueta("mira"), mascara_claro, 1896),
    "mas": (silueta("mas"), mascara_claro, 1896),
    "menu_pirata": (silueta("menu_pirata"),
                    mascara_claro, 1896),
    "seleccionar": (silueta("seleccionar"),
                    mascara_claro, 1386),
    "ok": (silueta("ok"), mascara_ambar, 1386),
    "salto": (silueta("salto"), mascara_ambar, 1386),
    "continuar": (silueta("continuar"), mascara_rojo, 1600),
    "alerta": (silueta("alerta"), mascara_blanco, 1600),
    "grupo": (silueta("grupo"), mascara_blanco, 1600),
    "movimiento": (silueta("movimiento"),
                   mascara_blanco, 1600),
    "seleccionar_adb": (silueta("seleccionar_adb"),
                        mascara_claro, 1600),
    "salto_adb": (silueta("salto_adb"), mascara_ambar, 1600),
    "ok_adb": (silueta("ok_adb"), mascara_ambar, 1600),
    "marcador": (silueta("marcador"), mascara_blanco, 1600),
    "gratis": (silueta("gratis"), mascara_blanco, 1200),
    "diario": (silueta("diario"), mascara_blanco, 1200),
    "recompensa": (silueta("recompensa"), mascara_blanco, 1200),
    "recoger_nar": (silueta("recoger_nar"), mascara_ambar, 1200),
    "login": (silueta("login"), mascara_ambar, 1200),
    "recoger_ver": (silueta("recoger_ver"), mascara_verde, 1200),
    "diario_adb": (silueta("diario_adb"), mascara_blanco, 1600),
    "recompensa_adb": (silueta("recompensa_adb"), mascara_blanco, 1600),
    "estacion": (silueta("estacion"), mascara_blanco, 1600),
    "flota_pirata": (silueta("flota_pirata"), mascara_texto, 1600),
    "elige": (silueta("elige"), mascara_blanco, 1600),
    "sistema": (silueta("sistema"), mascara_blanco, 1600),
    "flota_mov": (silueta("flota_mov"), mascara_blanco, 1600),
    "llamar": (silueta("llamar"), mascara_blanco, 1600),
    "eventos": (silueta("eventos"), mascara_blanco, 1600),
    "free": (silueta("free"), mascara_verde, 1600),
    "inicio": (silueta("inicio"), mascara_ambar, 1600),
    "cosmo_lista": (silueta("cosmo_lista"), mascara_blanco, 1600),
    "gratis_adb": (silueta("gratis_adb"), mascara_blanco, 1600),
    "mas_lado": (silueta("mas_lado"), mascara_blanco, 1600),
    "simulacion": (silueta("simulacion"), mascara_blanco, 1600),
    "sim_auto": (silueta("sim_auto"), mascara_texto, 1600),
    "recoger_ev": (silueta("recoger_ev"), mascara_verde, 1600),
    "recompensa_ev": (silueta("recompensa_ev"), mascara_verde, 1600),
    "puntos": (silueta("puntos"), mascara_gris, 1600),
    "pirata_rojo": (silueta("pirata_rojo"), mascara_rojo, 1600),
    "recoger_todo": (silueta("recoger_todo"), mascara_ambar, 1600),
    "promotion": (silueta("promotion"), mascara_claro, 1600),
    "crecimiento": (silueta("crecimiento"), mascara_claro, 1600),
    "pase_nova": (silueta("pase_nova"), mascara_claro, 1600),
    "roaming_test": (silueta("roaming_test"), mascara_ambar_claro, 1600),
    "base_btn": (silueta("base_btn"), mascara_claro, 1600),
    "protocolo": (silueta("protocolo"), mascara_claro, 1600),
    "cosmo_pestana": (silueta("cosmo_pestana"), mascara_claro, 1600),
    "mision_cosmo": (silueta("mision_cosmo"), mascara_claro, 1600),
    "flotas_piratas": (silueta("flotas_piratas"), mascara_claro, 1600),
}
# "Recoger" naranja (Recompensas de crecimiento): la primera palabra de "Recoger todo"
_rt = ROTULOS["recoger_todo"][0]
_corte = int(np.nonzero(_rt[:, :120].sum(axis=0))[0].max()) + 1
ROTULOS["recoger_amb"] = (_rt[:, :_corte].copy(), mascara_ambar, 1600)


_PLANTILLAS: dict = {}


def _plantilla(silueta, ancho, alto):
    clave = (id(silueta), ancho, alto)
    t = _PLANTILLAS.get(clave)
    if t is None:
        t = cv2.resize(silueta, (ancho, alto), interpolation=cv2.INTER_NEAREST).astype(np.float32)
        if len(_PLANTILLAS) > 4000:
            _PLANTILLAS.clear()
        _PLANTILLAS[clave] = t
    return t


def _encaja_lento(m, silueta, esc):
    alto, ancho = int(silueta.shape[0] * esc), int(silueta.shape[1] * esc)
    if alto < 8 or ancho < 12 or alto >= m.shape[0] or ancho >= m.shape[1]:
        return 0.0, (0, 0)
    t = _plantilla(silueta, ancho, alto)
    if t.sum() < 10:
        return 0.0, (0, 0)
    _, mx, _, loc = cv2.minMaxLoc(cv2.matchTemplate(m, t, cv2.TM_CCOEFF_NORMED))
    return float(mx), (int(loc[0] + ancho // 2), int(loc[1] + alto // 2))


class _Mascara(np.ndarray):
    """Mascara con su copia a media resolucion ya calculada (para buscar
    primero en pequeno y luego afinar solo donde hay candidatos)."""
    mitad = None


def _con_mitad(m):
    m = m.view(_Mascara)
    m.mitad = cv2.resize(m, (m.shape[1] // 2, m.shape[0] // 2), interpolation=cv2.INTER_AREA)
    return m


def _encaja(m, silueta, esc):
    """Mismo resultado que buscar en toda la pantalla, pero mucho mas rapido:
    se busca a media resolucion, se toman los 3 mejores sitios y en cada uno
    se mide a resolucion completa en una ventanita alrededor."""
    mitad = getattr(m, "mitad", None)
    alto, ancho = int(silueta.shape[0] * esc), int(silueta.shape[1] * esc)
    if mitad is None or alto < 18 or ancho < 26:
        return _encaja_lento(np.asarray(m), silueta, esc)
    if alto >= m.shape[0] or ancho >= m.shape[1]:
        return 0.0, (0, 0)
    t = _plantilla(silueta, ancho, alto)
    if t.sum() < 10:
        return 0.0, (0, 0)
    t2 = cv2.resize(t, (ancho // 2, alto // 2), interpolation=cv2.INTER_AREA)
    r = cv2.matchTemplate(mitad, t2, cv2.TM_CCOEFF_NORMED)
    # zonas lisas (todo 0 o todo 1) dan valores falsos (division por cero):
    # se descartan mirando la variacion de la pantalla bajo la plantilla
    th, tw = t2.shape
    k = (tw, th)
    med = cv2.boxFilter(mitad, -1, k, anchor=(0, 0), normalize=True, borderType=cv2.BORDER_CONSTANT)
    med2 = cv2.boxFilter(mitad * mitad, -1, k, anchor=(0, 0), normalize=True,
                         borderType=cv2.BORDER_CONSTANT)
    var = (med2 - med * med)[:r.shape[0], :r.shape[1]]
    r[~np.isfinite(r) | (r > 1.01) | (var < 0.01)] = -1
    full = np.asarray(m)
    mejor, centro = 0.0, (0, 0)
    marg = 6
    for _ in range(3):
        _, mx, _, (x, y) = cv2.minMaxLoc(r)
        if mx <= 0.15:
            break
        r[max(0, y - alto // 4):y + alto // 4 + 1, max(0, x - ancho // 4):x + ancho // 4 + 1] = -1
        x0, y0 = max(0, 2 * x - marg), max(0, 2 * y - marg)
        x1 = min(full.shape[1], 2 * x + ancho + marg)
        y1 = min(full.shape[0], 2 * y + alto + marg)
        zona = full[y0:y1, x0:x1]
        if zona.shape[0] < alto or zona.shape[1] < ancho:
            continue
        _, v, _, loc = cv2.minMaxLoc(cv2.matchTemplate(zona, t, cv2.TM_CCOEFF_NORMED))
        if v > mejor:
            mejor, centro = float(v), (int(x0 + loc[0] + ancho // 2), int(y0 + loc[1] + alto // 2))
    return mejor, centro


#  la ultima captura y sus mascaras: muchas busquedas seguidas miran la misma
_ULTIMA = {"firma": None, "mascaras": {}}


def _mascara(img, color):
    firma = (img.__array_interface__["data"][0], img.shape, int(img[::61, ::53].sum()))
    if _ULTIMA["firma"] != firma:
        _ULTIMA["firma"], _ULTIMA["mascaras"] = firma, {}
    m = _ULTIMA["mascaras"].get(color)
    if m is None:
        m = _con_mitad(color(img).astype(np.float32))
        _ULTIMA["mascaras"][color] = m
    return m


# Variantes de un mismo rotulo: la plantilla de la grabacion de la ventana y la
# sacada por ADB. Se usa la que mejor encaje. El factor pasa la escala de la
# variante a la de la plantilla principal (las distancias relativas, como la
# casilla de "Seleccionar todo", estan medidas a la escala de la principal).
VARIANTES = {
    "seleccionar": [("seleccionar_adb", 1.19)],
    "salto": [("salto_adb", 1.21)],
    "ok": [("ok_adb", 1.22)],
    "diario": [("diario_adb", 1.333)],
    "recompensa": [("recompensa_adb", 1.333)],
}


def localizar(img: np.ndarray, nombre: str):
    mejor = _localizar_uno(img, nombre)
    for otro, factor in VARIANTES.get(nombre, []):
        p, c, e = _localizar_uno(img, otro)
        if p > mejor[0]:
            mejor = (p, c, e * factor)
    return mejor


def _localizar_uno(img: np.ndarray, nombre: str):
    """Localiza un rotulo o icono del juego por su silueta.

    Dos pasadas: una gruesa por un abanico amplio de escalas y otra fina
    alrededor de la mejor. La escala no se deduce del tamano de la imagen,
    porque las plantillas salen de grabaciones de la ventana (con bordes de
    BlueStacks) y el bot ve la pantalla de Android por ADB.
    Devuelve (parecido 0-1, centro, escala)."""
    silueta, color, _ = ROTULOS[nombre]
    m = _mascara(img, color)
    # La escala de cada rotulo no cambia mientras no cambie la resolucion:
    # una vez encontrado con seguridad, se busca solo alrededor de esa escala
    # (7 tamanos en vez de ~30). Mucho mas rapido.
    clave = (nombre, img.shape[1], img.shape[0])
    if clave in _ESCALAS:
        e0 = _ESCALAS[clave]
        mejor, esc_mejor = (0.0, (0, 0)), e0
        for esc in np.arange(e0 - 0.045, e0 + 0.046, 0.015):
            r = _encaja(m, silueta, esc)
            if r[0] > mejor[0]:
                mejor, esc_mejor = r, esc
        return mejor[0], mejor[1], float(esc_mejor)
    # Escala medida por ADB a 1600 de ancho; para otra resolucion se ajusta
    # en proporcion y se prueba alrededor (9 tamanos en vez de ~30).
    if nombre in ESCALA_1600:
        e0 = ESCALA_1600[nombre] * img.shape[1] / 1600.0
        mejor, esc_mejor = (0.0, (0, 0)), e0
        for esc in np.arange(e0 - 0.06, e0 + 0.061, 0.015):
            r = _encaja(m, silueta, esc)
            if r[0] > mejor[0]:
                mejor, esc_mejor = r, esc
        if mejor[0] >= 0.84:
            _ESCALAS[clave] = float(esc_mejor)
        if mejor[0] >= 0.60 or img.shape[1] == 1600:
            return mejor[0], mejor[1], float(esc_mejor)
    mejor, esc_mejor = (0.0, (0, 0)), 1.0
    for esc in np.arange(0.55, 2.0, 0.08):
        r = _encaja(m, silueta, esc)
        if r[0] > mejor[0]:
            mejor, esc_mejor = r, esc
    gruesa = esc_mejor
    for esc in np.arange(gruesa - 0.07, gruesa + 0.075, 0.015):
        r = _encaja(m, silueta, esc)
        if r[0] > mejor[0]:
            mejor, esc_mejor = r, esc
    if mejor[0] >= 0.84:
        _ESCALAS[clave] = float(esc_mejor)
    return mejor[0], mejor[1], float(esc_mejor)


_ESCALAS: dict = {}

# escala de cada plantilla en una captura ADB de 1600x900 (medida)
ESCALA_1600 = {
    "sigilo": 1.195, "atacar": 1.195, "atras": 1.21, "radar": 1.21,
    "seleccionar": 1.195, "salto": 1.21, "ok": 1.225, "mira": 1.54, "mas": 1.46,
    "continuar": 1.005, "alerta": 1.005, "grupo": 1.005, "elige": 1.005,
    "movimiento": 1.005, "marcador": 1.005, "seleccionar_adb": 1.005,
    "salto_adb": 1.005, "ok_adb": 1.03,
    # sacadas de una grabacion de 1200 de ancho: 1600/1200
    "gratis": 1.333, "diario": 1.333, "recompensa": 1.333, "recoger_nar": 1.333,
    "login": 1.333, "recoger_ver": 1.333, "estacion": 1.005,
    "diario_adb": 1.005, "recompensa_adb": 1.005, "flota_pirata": 1.005,
    "sistema": 1.0, "mas_lado": 1.0, "simulacion": 1.0, "sim_auto": 1.0, "flota_mov": 1.0, "llamar": 1.0,
    "eventos": 1.0, "free": 1.0, "gratis_adb": 1.0, "inicio": 1.0, "cosmo_lista": 1.0,
    "recoger_ev": 1.0, "recompensa_ev": 1.0, "puntos": 1.0, "pirata_rojo": 1.0,
    "recoger_todo": 1.0, "promotion": 1.0, "crecimiento": 1.0, "pase_nova": 1.0,
    "roaming_test": 1.0, "base_btn": 1.0, "protocolo": 1.0, "cosmo_pestana": 1.0,
    "mision_cosmo": 1.0, "flotas_piratas": 1.0,
}


# tamanos en que sale cada rotulo segun la ventana (respecto a la plantilla)
TAMANOS = {"recoger_todo": (1.0, 1.41), "recoger_amb": (0.9, 1.0, 1.12)}


def localizar_todos(img: np.ndarray, nombre: str, umbral: float, maximo: int = 12):
    """Todas las apariciones de un rotulo (p. ej. varios "Recoger" en una
    lista), de arriba abajo. Solo para plantillas con escala medida por ADB."""
    tam = TAMANOS.get(nombre, (1.0,))
    if len(tam) > 1:
        todos = []
        for t in tam:
            for p, c in _localizar_todos(img, nombre, umbral, maximo, t):
                if all(abs(c[0] - c2[0]) > 20 or abs(c[1] - c2[1]) > 12 for _, c2 in todos):
                    todos.append((p, c))
        return sorted(todos, key=lambda h: (h[1][1], h[1][0]))
    return _localizar_todos(img, nombre, umbral, maximo, 1.0)


def _localizar_todos(img, nombre, umbral, maximo, factor):
    silueta, color, _ = ROTULOS[nombre]
    m = np.asarray(_mascara(img, color))
    esc = ESCALA_1600.get(nombre, 1.0) * factor * img.shape[1] / 1600.0
    alto, ancho = int(silueta.shape[0] * esc), int(silueta.shape[1] * esc)
    if alto < 6 or ancho < 10 or alto >= m.shape[0] or ancho >= m.shape[1]:
        return []
    t = _plantilla(silueta, ancho, alto)
    r = cv2.matchTemplate(m, t, cv2.TM_CCOEFF_NORMED)
    med = cv2.boxFilter(m, -1, (ancho, alto), anchor=(0, 0), normalize=True,
                        borderType=cv2.BORDER_CONSTANT)
    med2 = cv2.boxFilter(m * m, -1, (ancho, alto), anchor=(0, 0), normalize=True,
                         borderType=cv2.BORDER_CONSTANT)
    var = (med2 - med * med)[:r.shape[0], :r.shape[1]]
    r[~np.isfinite(r) | (r > 1.01) | (var < 0.01)] = -1
    hallados = []
    for _ in range(maximo):
        _, mx, _, (x, y) = cv2.minMaxLoc(r)
        if mx < umbral:
            break
        hallados.append((float(mx), (int(x + ancho // 2), int(y + alto // 2))))
        r[max(0, y - alto):y + alto + 1, max(0, x - ancho):x + ancho + 1] = -1
    return sorted(hallados, key=lambda h: (h[1][1], h[1][0]))


def buscar_rotulo(img: np.ndarray, nombre: str) -> tuple[float, tuple[int, int]]:
    p, c, _ = localizar(img, nombre)
    return p, c
