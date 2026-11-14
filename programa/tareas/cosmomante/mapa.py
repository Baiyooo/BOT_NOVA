"""Lectura del panel de Ascender de Cosmomante y plan de tiradas.

Funciones puras (sin ADB) para poder probarlas con capturas reales:
  clasificar(crop)            -> 'nave' | 'octa' | 'x2' | 'iman_dorado' | 'iman_azul' | 'puntos' | 'otro'
  filas_panel(img)            -> filas completas visibles de una captura 1600x900
  unir(frames)                -> {indice_casilla: (clase, recogido)} uniendo varias capturas
  plan(mapa, pos, ...)        -> mejor jugada (dado remoto 1-6, imanes, x2) o None
"""
import cv2
import numpy as np

from vision.recursos import archivos, imagen

COLX = (270, 625, 980)
N_CASILLAS = 50
_PLANT = None


def _plantillas():
    global _PLANT
    if _PLANT is None:
        _PLANT = []
        for archivo in archivos("cosmomante", "iconos"):     # sin plantillas: todo "otro"
            nombre = archivo.split("_", 1)[1].rsplit(".", 1)[0]
            im = imagen("cosmomante", "iconos", archivo)
            _PLANT.append((nombre, cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32)))
    return _PLANT


def clasificar(crop, umbral=0.80):
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
    mejor, nombre = umbral, "otro"
    for n, t in _plantillas():
        if g.shape != t.shape:
            continue
        s = float(cv2.matchTemplate(g, t, cv2.TM_CCOEFF_NORMED)[0, 0])
        if s > mejor:
            mejor, nombre = s, n
    return nombre


def bordes(img):
    """y del borde inferior de cada fila de casillas visible. Las filas
    "Recogido" no marcan su borde, asi que se deduce la fase de la cuadricula
    (cada fila ocupa 130 px) a partir de los bordes que si se ven."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(float)
    col = g[:, 105:130].mean(axis=1)
    cand = []
    for y in range(120, 815):
        if 80 <= col[y] <= 100 and col[y - 3] < 60:
            cand.append(y)                       # borde inferior
        elif 70 <= col[y] <= 82 and col[y - 3] < 45 and col[y + 6] > 30:
            cand.append(y + 111)                 # borde superior
    if not cand:
        return []
    fases = sorted(c % 130 for c in cand)
    fase = fases[len(fases) // 2]
    return [y for y in range(fase, 830, 130) if y >= 120]


def _recogido(img, cy, cx):
    lab = img[cy - 45:cy - 12, cx - 175:cx - 60]
    b, g, r = [lab[..., i].astype(int) for i in range(3)]
    return int(((g > 180) & (b > 160) & (r < 90)).sum()) > 150


def filas_panel(img):
    """[(borde_y, [(clase, recogido) x3])] solo filas completas."""
    res = []
    for b in bordes(img):
        cy = b - 55
        if cy - 45 < 135 or cy + 45 > 790:
            continue
        cel = []
        for cx in COLX:
            cel.append((clasificar(img[cy - 38:cy + 12, cx - 38:cx + 38]), _recogido(img, cy, cx)))
        res.append((b, cel))
    return res


def desplazamiento(prev, nxt):
    """Cuanto subio el contenido entre dos capturas (None si no se puede)."""
    banda = cv2.cvtColor(nxt[150:340, 100:1152], cv2.COLOR_BGR2GRAY)
    g = cv2.cvtColor(prev[118:808, 100:1152], cv2.COLOR_BGR2GRAY)
    r = cv2.matchTemplate(g, banda, cv2.TM_CCOEFF_NORMED)
    _, mx, _, loc = cv2.minMaxLoc(r)
    if mx < 0.8:
        return None
    return (loc[1] + 118) - 150


def unir(frames, tipos=None):
    """Une capturas sucesivas de un nivel (la primera, arriba del todo).
    Devuelve (mapa, completo): mapa {indice: (clase, recogido)}."""
    mapa = {}
    base = 0
    primero = None
    ok = True
    for i, img in enumerate(frames):
        if i:
            d = desplazamiento(frames[i - 1], img)
            if d is None:
                ok = False
                break
            base += d
        for b, cel in filas_panel(img):
            if primero is None:
                primero = b            # borde de la fila 0 en la primera captura
            fila = round((b + base - primero) / 130.0)
            for col, c in enumerate(cel):
                idx = fila * 3 + col
                if 0 <= idx < N_CASILLAS:
                    mapa[idx] = c
                    if tipos is not None and (idx not in tipos or tipos[idx] == "otro"):
                        tipos[idx] = tipo_esquina(img, b - 55, COLX[col])[0]
    return mapa, ok and len(mapa) >= N_CASILLAS - 1


# ---------------------------------------------------------------- plan ----
PESO = {"nave": 100, "octa": 70, "x2": 30, "iman_dorado": 30, "iman_azul": 20,
        "puntos": 1, "otro": 2}


def valor_casilla(mapa, q, usadas=()):
    q %= N_CASILLAS
    c = mapa.get(q)
    if c is None or c[1] or q in usadas or q == 0:
        return 0
    return PESO.get(c[0], 2)


def plan(mapa, pos, remotos, dorados, x2, umbral_remoto=40):
    """Mejor jugada desde la casilla 'pos' (0..49).
    Devuelve dict {dado, dorado, x2, valor} o None si no merece gastar nada.
    Reglas: el dado remoto solo si el premio >= umbral; el imán dorado solo si
    suma >= 40 mas que sin él; el x2 solo si lo recogido >= 100."""
    if remotos <= 0:
        return None
    mejor = None
    for d in range(1, 7):
        q = pos + d
        base = valor_casilla(mapa, q)
        ventana = sum(valor_casilla(mapa, q + k) for k in range(-2, 3))
        usar_dorado = dorados > 0 and ventana - base >= 40
        v = ventana if usar_dorado else base
        usar_x2 = x2 > 0 and v >= 100
        v2 = v * (2 if usar_x2 else 1)
        if mejor is None or v2 > mejor["valor"]:
            mejor = {"dado": d, "dorado": usar_dorado, "x2": usar_x2, "valor": v2}
    if mejor is None or mejor["valor"] < umbral_remoto:
        return None
    return mejor


# ------------------------------------------- tipo de casilla (cubo/carta/gema) --
# Cada casilla del tablero lleva un icono (cubo, carta o gema). El panel de
# Ascender lo repite en la esquina de cada celda, asi que sabemos el tipo de las
# 50 casillas. En el tablero la camara siempre esta centrada en la baliza: el icono
# de la casilla bajo la baliza y los de sus vecinas dicen donde esta.
_CASILLA = None
_KTH = None


def _th(img):
    global _KTH
    if _KTH is None:
        _KTH = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.morphologyEx(g, cv2.MORPH_TOPHAT, _KTH).astype(np.float32)


def _plantillas_casilla():
    global _CASILLA
    if _CASILLA is None:
        _CASILLA = {"esquina": {}, "tablero": {}}
        try:
            for grupo in ("esquina", "tablero"):
                for archivo in archivos("cosmomante", "casilla_" + grupo):
                    n = archivo.split("_", 1)[1].rsplit(".", 1)[0]
                    im = imagen("cosmomante", "casilla_" + grupo, archivo, gris=True)
                    _CASILLA[grupo][n] = im.astype(np.float32)
        except Exception:                                   # noqa: BLE001
            pass
    return _CASILLA


def _mejor_tipo(t, x, y, plant, margen, minimo):
    """(tipo, puntuacion) del icono centrado en (x, y) de la imagen top-hat t."""
    mejor, nombre = 0.0, "otro"
    for n, tp in plant.items():
        h, w = tp.shape
        y0, x0 = y - h // 2 - margen, x - w // 2 - margen
        if y0 < 0 or x0 < 0:
            continue
        reg = t[y0:y + h // 2 + margen + h % 2, x0:x + w // 2 + margen + w % 2]
        if reg.shape[0] < h or reg.shape[1] < w:
            continue
        sc = float(cv2.matchTemplate(reg, tp, cv2.TM_CCOEFF_NORMED).max())
        if sc > mejor:
            mejor, nombre = sc, n
    return (nombre if mejor >= minimo else "otro"), round(mejor, 2)


def tipo_esquina(img, cy, cx):
    """Tipo ('cubo'|'carta'|'gema'|'otro') de la celda del panel con centro (cx, cy)."""
    plant = _plantillas_casilla()["esquina"]
    if not plant:
        return "otro", 0.0
    t = _th(img[max(cy - 80, 0):cy + 40, cx + 90:cx + 200])
    return _mejor_tipo(t, 143 - 90 + 0, 80 - 33, plant, 9, 0.40)


def a1600(img):
    if img.shape[1] == 1600:
        return img
    return cv2.resize(img, (1600, int(round(img.shape[0] * 1600.0 / img.shape[1]))))


# posicion en pantalla (1600x900) del icono bajo la baliza y de las 4 diagonales
CENTRO = (800, 438)
VECINAS = ((102, -62), (102, 60), (-102, 60), (-102, -62))


def ver_alrededor(img):
    """{'centro': (tipo, puntuacion), 'vecinas': [tipo|None x4]} del tablero.
    Las casillas recogidas se ven como gemas azules.

    El umbral de las vecinas es mas bajo que el del centro: los iconos de las
    diagonales se ven mas pequenos y con menos contraste (medido en capturas
    reales: 0.31-0.37 para un cubo/carta correcto, 0.77 para una gema). Con
    0.45 se perdian casi todas y la baliza quedaba sin localizar."""
    img = a1600(img)
    plant = _plantillas_casilla()["tablero"]
    if not plant:
        return None
    t = _th(img)
    cx, cy = CENTRO
    centro = _mejor_tipo(t, cx, cy, plant, 12, 0.35)
    vec = []
    for dx, dy in VECINAS:
        tipo, sc = _mejor_tipo(t, cx + dx, cy + dy, plant, 14, 0.32)
        vec.append(tipo if tipo != "otro" else None)
    return {"centro": centro, "vecinas": vec}


def _clase_vecina(mapa, tipos, j):
    if j % N_CASILLAS == 0:
        return "inicio"
    j %= N_CASILLAS
    if mapa.get(j, (None, False))[1]:
        return "gema"                     # recogida: se ve como gema azul
    return tipos.get(j, "otro")


def localizar_baliza(mapa, tipos, obs):
    """Casillas posibles de la baliza segun lo que se ve: debe estar en una casilla
    recogida cuyo tipo coincida con el icono bajo ella y cuyas vecinas por el
    camino (anterior y siguiente) aparezcan entre las diagonales vistas."""
    if not obs or obs["centro"][0] == "otro":
        return []
    vistas = [v for v in obs["vecinas"] if v]
    puntos = {}
    for i in range(1, N_CASILLAS):
        if not mapa.get(i, (None, False))[1]:
            continue
        if tipos.get(i) != obs["centro"][0]:
            continue
        libres = list(vistas)
        p = 0
        for e in (_clase_vecina(mapa, tipos, i - 1), _clase_vecina(mapa, tipos, i + 1)):
            if e in libres:
                libres.remove(e)
                p += 1
        puntos[i] = p
    if not puntos:
        return []
    mejor = max(puntos.values())
    return [i for i, p in puntos.items() if p == mejor]
