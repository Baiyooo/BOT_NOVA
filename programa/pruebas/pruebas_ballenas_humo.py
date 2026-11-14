"""Prueba de humo de las ballenas: ejecuta el ciclo del que invoca y el del que
apoya con un BlueStacks falso (pantalla negra) y comprueba que no revientan
(por ejemplo el antiguo «'bool' object is not callable»). No toca el juego.

    python pruebas\\pruebas_ballenas_humo.py
"""
import os
import sys
import tempfile
import threading
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="novabot_prueba_")

import numpy as np  # noqa: E402

from tareas.ballenas.tarea import Ballenas  # noqa: E402
from tareas.ballenas.sync import Sync  # noqa: E402


class Falso:
    name = "127.0.0.1:5001"

    def capture(self):
        return np.zeros((900, 1600, 3), np.uint8)

    def tap(self, p):
        pass

    def drag(self, a, b):
        pass

    def back(self):
        pass


fallos = 0
for papel in ("invoca", "apoya"):
    parar = threading.Event()
    threading.Timer(8, parar.set).start()
    yo, otro = "5001", "5002"
    t = Ballenas(Falso(), log=lambda *a: None, stop=parar,
                 lider=yo if papel == "invoca" else otro, apoyo=otro if papel == "invoca" else yo,
                 preparar_grupo=False)
    try:
        (t.ciclo_lider if papel == "invoca" else t.ciclo_apoyo)()
        print(f"OK   {papel}: termina sin error ({t.status.get('estado')})")
    except Exception:                                    # noqa: BLE001
        fallos += 1
        print(f"FALLO {papel}:")
        traceback.print_exc()


# ---- solo ataca la ballena que ha invocado (nunca las de otros jugadores)
def prueba_objetivo(antes, despues, invocadas=1):
    parar = threading.Event()
    t = Ballenas(Falso(), log=lambda *a: None, stop=parar, lider="5001", apoyo="5002",
                 preparar_grupo=False, tope_dia=1)
    vistas = iter([antes] + [despues] * 5)
    atacadas = []
    t._preparar = lambda: None
    t.mi_sistema = lambda *a, **k: None
    t._modo = lambda quiero: True
    t._llamar_flotas = lambda: None
    t.ver_ballenas = lambda: list(next(vistas, despues))
    t.invocar = lambda n: invocadas
    t.sync.esperar = lambda cond, seg, parado: {"presente": t.sync.leer().get("ciclo")}
    t.atacar_ballena = lambda ciclo, i, pos, intento=0: atacadas.append(tuple(pos)) or False
    t._gemas_ciclo = lambda lider, muertas=None: 0
    t.ciclo_lider()
    return atacadas, t


import time as _t  # noqa: E402
_t_sleep, _t.sleep = _t.sleep, (lambda s: None)
a, t = prueba_objetivo([(100, 100), (300, 200)], [(100, 100), (300, 200), (700, 450)])
ok = a == [(700, 450)] * 3 and t.sync.leer().get("intento") == 2
print(("OK   " if ok else "FALLO ") + f"ataca solo la nueva y la reintenta: {a}")
fallos += 0 if ok else 1
a, t = prueba_objetivo([(100, 100)], [(100, 100)])
ok = a == []
print(("OK   " if ok else "FALLO ") + f"si no sale ninguna nueva no ataca las de otros: {a}")
fallos += 0 if ok else 1


# ---- el que apoya repite el ataque cuando el que invoca reintenta la ballena
def prueba_apoyo_reintento():
    parar = threading.Event()
    threading.Timer(8, parar.set).start()
    t = Ballenas(Falso(), log=lambda *a: None, stop=parar, lider="5002", apoyo="5001",
                 preparar_grupo=False)
    t._preparar = lambda: None
    t.mi_sistema = lambda *a, **k: None
    t._modo = lambda quiero: True
    t._llamar_flotas = lambda: None
    vistas = iter([[(100, 100)]] + [[(100, 100), (700, 450)]] * 10)
    t.ver_ballenas = lambda: list(next(vistas, [(100, 100), (700, 450)]))
    cic = "120000"
    lid = Sync("5002", "5001")
    lid.escribir(ciclo=cic, fase="atacar", ballenas=[[700, 450]], objetivo=0, intento=0)
    ataques = []

    def atacar(ciclo, i, pos, intento=0):
        ataques.append((i, intento))
        if len(ataques) == 2:            # el que invoca reintenta la ballena 1
            lid.escribir(objetivo=0, intento=1)
        if len(ataques) >= 3:
            parar.set()
        return False

    t.atacar_ballena = atacar
    t._gemas_ciclo = lambda lider, muertas=None: 0
    t.ciclo_apoyo()
    return ataques


a = prueba_apoyo_reintento()
ok = a == [(0, 0), (0, 0), (0, 1)]
print(("OK   " if ok else "FALLO ") + f"el que apoya sigue los reintentos del que invoca: {a}")
fallos += 0 if ok else 1

# ---- modo SOLA: sin otra cuenta (no espera sync, ataca solo la nueva, recoge con todos los drones)
def sola(**kw):
    t = Ballenas(Falso(), log=lambda *a: None, stop=threading.Event(), lider="5001", apoyo="",
                 preparar_grupo=False, sola=True, tope_dia=1, **kw)

    def sin_sync(*a, **k):
        raise AssertionError("en modo sola no se espera a la otra cuenta")
    t.sync.esperar = sin_sync
    t.mi_sistema = lambda *a, **k: None
    t._modo = lambda quiero: True
    t._llamar_flotas = lambda: None
    t._reparar_final = lambda: None          # (con sleep a cero, reparar de verdad se queda en un bucle)
    return t


def prueba_sola_ciclo():
    t = sola()
    vistas = iter([[(100, 100), (300, 200)]] + [[(100, 100), (300, 200), (700, 450)]] * 5)
    atacadas = []
    t.ver_ballenas = lambda: list(next(vistas, [(100, 100), (300, 200), (700, 450)]))
    t.invocar = lambda n: 1
    t.atacar_ballena = lambda ciclo, i, pos, intento=0: atacadas.append(tuple(pos)) or False
    t._gemas_ciclo = lambda lider, muertas=None: 0
    t.ciclo_lider()
    return atacadas


a = prueba_sola_ciclo()
ok = a == [(700, 450)] * 3
print(("OK   " if ok else "FALLO ") + f"sola: no espera sync y ataca solo la nueva: {a}")
fallos += 0 if ok else 1


def prueba_sola_ataque():
    """El ataque sale sin esperar el «listo» de nadie, y un «enviado» viejo no cuenta."""
    t = sola()
    t.sync.escribir(enviado="X:0:0")
    aliado = t._otro_ya_ataco("X", 0, 0)
    aliados = []
    t.abrir_ballena = lambda pos, desde_zoom=False, aliado_nuestro=False: aliados.append(aliado_nuestro) or 5_000_000
    t.saltar_cerca = lambda *a, **k: True
    t._ocr = lambda etq, zona=None: (np.zeros((900, 1600, 3), np.uint8), [])
    t._busca = lambda items, *f, **k: {"centro": (1300, 400)}
    t._dialogo_una_flota = lambda boton: True
    return aliado, t.atacar_ballena("120000", 0, (700, 450)), aliados


aliado, lanzado, aliados = prueba_sola_ataque()
ok = aliado is False and lanzado is True and aliados == [False, False]
print(("OK   " if ok else "FALLO ") + f"sola: ataca sin esperar a nadie y la «Flota aliada» no es nuestra: {lanzado} {aliados}")
fallos += 0 if ok else 1


def prueba_sola_gemas(caso):
    """caso: «2d» (se ven a la primera), «zoom» (hay que alejar el mapa) o
    «3d» (en 2D no sale ninguna: respaldo por las etiquetas 3D)."""
    t = sola(robots=6)
    t._muerte = (700, 450)
    modos, zooms, pedidos = [], [], []
    t._modo = lambda q: modos.append(q) or True
    t.ctrl.zoom = lambda acercar=True, centro=None, fuerza=1.0, **k: zooms.append(acercar) or True
    t._zoom_3d = lambda: modos.append("zoom3d") or True
    t._zoom_a_muerte = lambda: modos.append("2d")
    t._ocr = lambda etq, zona=None: (np.zeros((900, 1600, 3), np.uint8),
                                     [{"texto": "Gema organica", "centro": (100, 100)}] * 4)
    t.recoger_por_etiquetas = lambda cupo: pedidos.append(("3d", cupo)) or cupo

    radios = []

    def cerca2d(img, radio=True):
        radios.append(radio)
        visto = (caso == "2d" or (caso == "zoom" and zooms[-1:] == [False])
                 or (caso == "zona" and len(arrastres) == 1))
        return [(10, 10)] * 5 if visto else []
    t._gemas_cerca2d = cerca2d
    t.recoger_gemas = lambda cupo, radio=True: pedidos.append(("2d", cupo, radio)) or cupo
    arrastres, recentrados = [], []
    t.ctrl.drag = lambda a, b: arrastres.append((a, b))
    t.mi_sistema = lambda forzar=False: recentrados.append(forzar)
    if caso == "click":
        t.ctrl.style = "click"                    # sin arrastre posible
    t._gemas_ciclo(lider=True, muertas=1)
    return pedidos, zooms, modos, arrastres, (radios, recentrados)


(p2, z2, _m, a2, (r2, c2)), (pz, zz, _m, _a, (_r, cz)), (p3, z3, m3, a3, (_r, c3)), (pa, _z, _m, ar, (_r, ca)), \
    (_pc, _z, _m, ac, (_r, _c)) = (prueba_sola_gemas("2d"), prueba_sola_gemas("zoom"), prueba_sola_gemas("3d"),
                                   prueba_sola_gemas("zona"), prueba_sola_gemas("click"))
ok = (p2 == [("2d", 5, False)] and z2 == [] and set(r2) == {False}    # todo el mapa (sin radio), todos los drones
      and a2 == [] and c2 == [False, False]                           # (mi_sistema normal al empezar y al acabar)
      and pz == [("2d", 5, False)] and zz == [False, True] and True in cz   # alejar, detectar, y recentrar con mi_sistema
      and pa == [("2d", 5, False)] and len(ar) == 1 and True in ca    # zona con arrastre: recentra, no deshace a ciegas
      and ac == []                                                    # estilo «click»: nunca arrastra
      and p3 == [("3d", 6)] and z3 == [False, True] and "zoom3d" in m3 and m3[-1] == "3d"   # respaldo 3D y acaba en 3D
      and len(a3) == 4)                                               # sin gemas en ningun sitio: recorre las 4 zonas
print(("OK   " if ok else "FALLO ") + f"gemas por todo el mapa: 2D {p2}, con zoom {pz} {zz}, por zonas {pa} {ar}, respaldo 3D {p3}")
fallos += 0 if ok else 1


# ---- escombros de la ballena: tras las gemas, con los drones que queden libres
def prueba_escombros(con_escombros):
    import tareas.restos as restos
    t = sola(con_escombros=con_escombros)
    vistas = iter([[(100, 100)]] + [[(100, 100), (700, 450)]] * 5)
    t.ver_ballenas = lambda: list(next(vistas, [(100, 100), (700, 450)]))
    t.invocar = lambda n: 1
    t.atacar_ballena = lambda ciclo, i, pos, intento=0: True
    t.esperar_muerte = lambda pos, maximo=480: True
    orden, modos = [], []
    t._modo = lambda q: modos.append(q) or True               # matar en 3D, recoger en 2D
    t._gemas_ciclo = lambda lider, muertas=None: orden.append("gemas") or 0
    pedidos = []

    class Falso2:
        def __init__(self, *a, **k):
            pass

        iconos_vistos = 1

        def que_recoger(self, escombros=True, gemas=False):
            pedidos.append(("prefijos", escombros, gemas))
            return self

        def con_minimos(self, minimos):
            pedidos.append(("minimos", dict(minimos)))
            return self

        def recoger_iconos(self, cupo, cerca=None, fija=False):
            orden.append("escombros")
            pedidos.append(("cupo", cupo))
            pedidos.append(("modo", modos[-1]))
            pedidos.append(("cerca", cerca((800, 450), np.zeros((900, 1600, 3))),    # junto al centro
                            cerca((60, 60), np.zeros((900, 1600, 3))), fija))         # lejos
            return 2
    orig = (restos.RecogerRestos, restos.drones_libres)
    restos.RecogerRestos, restos.drones_libres = Falso2, (lambda c, total: 2)
    try:
        t.ciclo_lider()
    finally:
        restos.RecogerRestos, restos.drones_libres = orig
    return orden, pedidos, modos


o, p, md = prueba_escombros(True)
ok = (o == ["gemas", "escombros"] and ("cupo", 2) in p and ("prefijos", True, False) in p
      and ("modo", "2d") in p and md == ["3d", "3d", "2d", "3d"]      # mata en 3D, recoge en 2D, vuelve a 3D
      and ("cerca", True, False, True) in p                           # solo iconos junto a la muerte
      and ("minimos", {"mineral": 18_000_000, "cristal": 2_000_000, "aleacion": 1_000_000}) in p)
print(("OK   " if ok else "FALLO ") + f"escombros tras las gemas, en 2D y con los drones libres (sin Nucleos): {o} {p} {md}")
fallos += 0 if ok else 1
o, p, md = prueba_escombros(False)
ok = o == ["gemas"] and not p and md == ["3d"]
print(("OK   " if ok else "FALLO ") + f"con la casilla de escombros desactivada no se recogen: {o}")
fallos += 0 if ok else 1


# ---- invocar desde la vista del sistema: Almacen > Objeto comun > Señuelo > Usar, sin pasar por la base
def prueba_invocar_sin_base():
    t = sola()
    llamadas = []

    def base(*a, **k):
        raise AssertionError("no se debe ir a la base para invocar")
    t.ir_a_base = base
    t.volver_a_base = base
    t._almacen_por_vecinos = lambda: llamadas.append("barra") or True
    t._toca = lambda frases, etq, **k: llamadas.append(etq) or {"centro": (1, 1)}
    t._espera_texto = lambda frases, seg, etq, zona=None: (None, [], {"texto": "Ballena invocada correctamente, cantidad actual 1/10"})
    t._atras_juego = lambda veces=1: llamadas.append(f"atras{veces}") or True
    t._ocr = lambda etq, zona=None: (np.zeros((900, 1600, 3), np.uint8), [])
    t._busca = lambda items, *f, **k: {"centro": (1300, 400)}      # «Señuelo de éter» seleccionado
    t._pantalla_tienda = lambda items, w, h: False
    t._senuelos_que_hay = lambda items, w, h: None
    t._tocar_usar = lambda: llamadas.append("usar") or {"centro": (1, 1)}
    return t.invocar(1), llamadas


n, ll = prueba_invocar_sin_base()
ok = n == 1 and ll[0] == "barra" and ll[-1] == "atras2" and "usar" in ll
print(("OK   " if ok else "FALLO ") + f"invoca desde el sistema, sin ir a la base: {n} {ll}")
fallos += 0 if ok else 1


def prueba_invocar_cuidado(caso):
    """Seguridad al invocar: sin «Objeto común» no se toca SLOT2; si el seleccionado ya no
    es el Señuelo o sale la Tienda no se usa nada; solo se usan los que hay."""
    t = sola()
    toques, usos = [], []
    t.ctrl.tap = lambda p: toques.append(p)
    t._almacen_por_vecinos = lambda: True
    t._atras_juego = lambda veces=1: True
    t._ocr = lambda etq, zona=None: (np.zeros((900, 1600, 3), np.uint8), [])
    t._busca = lambda items, *f, **k: {"centro": (1300, 400)}
    t._pantalla_tienda = lambda items, w, h: caso == "tienda"
    t._senuelos_que_hay = lambda items, w, h: 1 if caso == "uno" else None
    t._espera_texto = lambda frases, seg, etq, zona=None: (None, [], {"texto": "invocada correctamente cantidad actual 1/10"})
    t._toca = lambda frases, etq, **k: (None if etq == "objeto_comun" and caso == "sin_objeto"
                                        else (usos.append(1) if etq == "usar" else None) or {"centro": (1, 1)})
    t._tocar_usar = lambda: usos.append(1) or {"centro": (1, 1)}
    if caso == "no_senuelo":
        t._busca = lambda items, *f, **k: None
    return t.invocar(3), usos, toques


r = {c: prueba_invocar_cuidado(c) for c in ("sin_objeto", "tienda", "no_senuelo", "uno")}
ok = (r["sin_objeto"][0] == 0 and r["sin_objeto"][2] == []            # ni SLOT2 a ciegas
      and r["tienda"][0] == 0 and not r["tienda"][1]
      and r["no_senuelo"][0] == 0 and not r["no_senuelo"][1]
      and r["uno"][0] == 1 and len(r["uno"][1]) == 1)
print(("OK   " if ok else "FALLO ") + f"invocar con cuidado (sin Objeto común / Tienda / otro objeto / solo 1): {[(k, v[0]) for k, v in r.items()]}")
fallos += 0 if ok else 1


# ---- tandas de hasta 3 ballenas: invocar todas, matarlas, y SOLO entonces recoger todo
def prueba_tandas():
    t = sola()
    t.tope_dia = 5
    eventos, invocadas = [], []
    nuevas = [(100, 100), (300, 200), (700, 450)]
    estado = {"vistas": 0}

    def ver():
        estado["vistas"] += 1
        return [] if estado["vistas"] == 1 else list(nuevas[:invocadas[-1]])
    t.ver_ballenas = ver
    t.invocar = lambda n: invocadas.append(n) or n
    t.atacar_ballena = lambda ciclo, i, pos, intento=0: eventos.append("ataca") or True
    t.esperar_muerte = lambda pos, maximo=480: eventos.append("muere") or True
    t._gemas_ciclo = lambda lider, muertas=None: eventos.append("gemas") or 0
    t._llamar_flotas = lambda: eventos.append("flotas")
    puntos = []

    def escombros():
        eventos.append("escombros")
        puntos.append(list(t._muertes))
        return 0
    t.recoger_escombros_muerte = escombros
    m1 = t.ciclo_lider()
    ev1 = list(eventos)
    eventos.clear()
    t.hechas_hoy = m1
    estado["vistas"] = 0
    m2 = t.ciclo_lider()
    return m1, m2, invocadas, ev1, list(eventos), puntos


m1, m2, inv, ev1, ev2, pts = prueba_tandas()
ok = (inv == [3, 2] and (m1, m2) == (3, 2)
      and ev1 == ["ataca", "muere"] * 3 + ["flotas", "gemas", "escombros"]   # flotas a casa, gemas (todo el mapa), escombros
      and ev2 == ["ataca", "muere"] * 2 + ["flotas", "gemas", "escombros"]
      and pts[0] == [(100, 100), (300, 200), (700, 450)] and len(pts[1]) == 2)
print(("OK   " if ok else "FALLO ") + f"tope 5: tandas de {inv}, recogida solo tras matar; puntos de muerte: {[len(p) for p in pts]}")
fallos += 0 if ok else 1


# ---- ballenas nuestras que quedan vivas: se recuerdan y la siguiente tanda las ataca primero
def prueba_pendientes():
    t = sola()
    t.tope_dia = 2
    t.sync.escribir(pendientes=[])
    atacadas, invocadas, logs = [], [], []
    t.log = logs.append
    estado = {"n": 0}

    def ver():
        estado["n"] += 1
        return [] if estado["n"] == 1 else [(100, 100), (300, 200)]
    t.ver_ballenas = ver
    t.invocar = lambda n: invocadas.append(n) or n
    t.atacar_ballena = lambda ciclo, i, pos, intento=0: atacadas.append(tuple(pos)) or True
    t.esperar_muerte = lambda pos, maximo=480: tuple(pos) == (100, 100)       # solo muere la primera
    t._gemas_ciclo = lambda lider, muertas=None: 0
    t.recoger_escombros_muerte = lambda: 0
    m1 = t.ciclo_lider()
    guardadas = t.sync.leer().get("pendientes")
    # siguiente tanda: la superviviente sigue ahi (de otro jugador seria indistinguible) y no se gasta otro señuelo
    t2 = sola()
    t2.tope_dia, t2.hechas_hoy = 2, m1
    t2.ver_ballenas = lambda: [(300, 200)]
    t2.invocar = lambda n: invocadas.append(n) or n
    t2.atacar_ballena = lambda ciclo, i, pos, intento=0: atacadas.append(tuple(pos)) or True
    t2.esperar_muerte = lambda pos, maximo=480: True
    t2._gemas_ciclo = lambda lider, muertas=None: 0
    t2.recoger_escombros_muerte = lambda: 0
    m2 = t2.ciclo_lider()
    return m1, m2, guardadas, atacadas, invocadas, t2.sync.leer().get("pendientes")


m1, m2, guard, atq, inv, fin = prueba_pendientes()
ok = (m1 == 1 and m2 == 1 and inv == [2]                      # la 2.ª tanda no invoca: ataca la suya primero
      and atq == [(100, 100), (300, 200), (300, 200)]
      and guard and len(guard) == 1 and guard[0]["pos"] == [300, 200] and guard[0]["t"] > 0 and fin == [])
print(("OK   " if ok else "FALLO ") + f"ballena viva guardada y atacada primero (cuenta para el tope solo al morir): {m1},{m2} {inv} {atq}")
fallos += 0 if ok else 1


# ---- «0 invocada(s)»: el log dice por que
def prueba_cero_invocadas():
    t = sola()
    logs = []
    t.log = logs.append
    t.sync.escribir(pendientes=[])
    t.tope_dia = 3
    t.ver_ballenas = lambda: []

    def invocar(n):
        t.motivo_invocar = "no hay Señuelos de éter en Objeto común (¿se han acabado?)"
        return 0
    t.invocar = invocar
    t.ciclo_lider()
    return logs


logs = prueba_cero_invocadas()
ok = any("0 invocada(s) (no hay Señuelos" in m for m in logs)
print(("OK   " if ok else "FALLO ") + "«0 invocada(s)» con el motivo en el log")
fallos += 0 if ok else 1


# ---- las flotas vuelven a la estacion siempre (y no rompe si falla o no hay flotas fuera)
def prueba_flotas():
    import tareas.flotas as flotas
    llamadas = []

    class Falsa:
        def __init__(self, *a, **k):
            pass

        def run(self, n=1):
            llamadas.append("run")
    class Rota(Falsa):
        def run(self, n=1):
            raise RuntimeError("sin flotas")
    orig = flotas.LlamarFlotas
    t = Ballenas(Falso(), log=lambda *a: None, stop=threading.Event(), lider="5001", apoyo="", sola=True)
    t.mi_sistema = lambda *a, **k: None
    try:
        flotas.LlamarFlotas = Falsa
        t._llamar_flotas()
        flotas.LlamarFlotas = Rota
        t._llamar_flotas()                                    # no debe romper
        t.stop.set()
        flotas.LlamarFlotas = Falsa
        t._llamar_flotas()                                    # parado: no llama
    finally:
        flotas.LlamarFlotas = orig
    return llamadas


ll = prueba_flotas()
ok = ll == ["run"]
print(("OK   " if ok else "FALLO ") + f"llamar flotas tras la tanda (no rompe si falla, no si se para): {ll}")
fallos += 0 if ok else 1


# ---- cifras de los escombros (puro) y minimos por tipo
from tareas import restos as _restos  # noqa: E402

casos = {"18.500.000": 18_500_000, "18,500,000": 18_500_000, "18'500'000": 18_500_000, "1.375": 1375,
         "250": 250, "18,5M": 18_500_000, "3.2 M": 3_200_000, "950K": 950_000, "1,2m": 1_200_000,
         "1.375,5K": 1_375_500, "2G": None, "5B": None, "3,2": None, "": None, "abc": None, "12.34.5": None,
         None: None, "18,5 M\n": 18_500_000}
malos = {k: _restos.parse_cantidad(k) for k, v in casos.items() if _restos.parse_cantidad(k) != v}
ok = not malos
print(("OK   " if ok else "FALLO ") + f"parse_cantidad (miles, M/K, decimales con coma, ilegibles): {malos or 'todo bien'}")
fallos += 0 if ok else 1


def prueba_minimos(tipo, cantidad, minimos=True):
    import tareas.descartes as descartes
    t = _restos.RecogerRestos(Falso(), log=lambda *a: None, stop=threading.Event())
    if minimos:
        t.con_minimos({"mineral": 18_000_000, "cristal": 2_000_000, "aleacion": 1_000_000})
    toques = []
    t.ctrl.tap = lambda p: toques.append(p)
    items = [{"texto": tipo, "centro": (300, 300)}, {"texto": "Cantidad", "centro": (320, 350)},
             {"texto": "Recoger", "centro": (1300, 300)}]
    if cantidad:
        items.append({"texto": cantidad, "centro": (330, 390)})
    t._ocr = lambda etq: (np.zeros((900, 1600, 3), np.uint8), items)
    t.menu_abierto = lambda img: True
    cerrados = []
    t.cerrar_menu = lambda img: cerrados.append(1)
    orig = descartes.hay_movimiento
    descartes.hay_movimiento = lambda *a, **k: False
    try:
        r = t._probar_menu((500, 500))
    finally:
        descartes.hay_movimiento = orig
    return r, len(toques), len(cerrados)


res = {
    "mineral 3,2M": prueba_minimos("Mineral", "3,2M"), "mineral 18,5M": prueba_minimos("Mineral", "18,5M"),
    "mineral 18M exacto": prueba_minimos("Mineral", "18.000.000"),
    "cristal 2.100.000": prueba_minimos("Cristal", "2.100.000"), "cristal 1.999.999": prueba_minimos("Cristal", "1.999.999"),
    "aleacion 1.375": prueba_minimos("Aleacion", "1.375"), "aleacion 1,2M": prueba_minimos("Aleacion", "1,2M"),
    "ilegible": prueba_minimos("Mineral", ""), "sin minimos (piratas)": prueba_minimos("Mineral", "250", minimos=False),
}
ok = (res["mineral 3,2M"] == ("poco", 1, 1) and res["mineral 18,5M"][0] == "recogido" and res["mineral 18,5M"][1] == 2
      and res["mineral 18M exacto"][0] == "poco"                      # hay que SUPERARLO
      and res["cristal 2.100.000"][0] == "recogido" and res["cristal 1.999.999"][0] == "poco"
      and res["aleacion 1.375"][0] == "poco" and res["aleacion 1,2M"][0] == "recogido"
      and res["ilegible"] == ("poco", 1, 1)                           # ilegible: no recoge, cierra el menu
      and res["sin minimos (piratas)"][0] == "recogido")              # sin minimos no cambia nada
print(("OK   " if ok else "FALLO ") + f"minimos de escombros (por debajo/ilegible no; por encima si): {res}")
fallos += 0 if ok else 1


# ---- puntos de muerte guardados: compensar el desplazamiento de la camara, olvidar los vacios
def prueba_puntos_guardados():
    import cv2
    rng = np.random.default_rng(7)
    base = cv2.GaussianBlur(rng.integers(0, 255, (900, 1600, 3), dtype=np.uint8), (0, 0), 3)
    movida = np.roll(base, (20, 40), axis=(0, 1))          # la camara se ha movido: +40 en x, +20 en y
    t = sola()
    t.sync.escribir(muertes=[])
    t._registrar_muerte((700, 450), base)                  # con huella
    t.sync.escribir(muertes=t.sync.leer()["muertes"] + [{"pos": [300, 300], "t": _t.time()}])   # sin huella
    t.ctrl.capture = lambda: base
    sin_mover = t.puntos_muerte_recientes()
    t.ctrl.capture = lambda: movida
    movidos = t.puntos_muerte_recientes()
    return sin_mover, movidos


sm, mv = prueba_puntos_guardados()
ok = (len(sm) == 1 and abs(sm[0][0] - 700) <= 6 and abs(sm[0][1] - 450) <= 6          # sin mover: el mismo punto
      and len(mv) == 1 and abs(mv[0][0] - 740) <= 8 and abs(mv[0][1] - 470) <= 8)     # movida: compensado; el que no tiene huella se descarta
print(("OK   " if ok else "FALLO ") + f"puntos de muerte guardados compensados: {sm} -> {mv}")
fallos += 0 if ok else 1


def prueba_olvidar_poco():
    import tareas.restos as restos
    t = sola()
    t.sync.escribir(muertes=[])
    t._registrar_muerte((700, 450), None)

    class Falso3:
        iconos_vistos, sitios_poco, sitios_utiles = 1, 1, 0

        def __init__(self, *a, **k):
            pass

        def que_recoger(self, *a, **k):
            return self

        def con_minimos(self, m):
            return self

        def recoger_iconos(self, cupo, cerca=None, fija=False):
            return 0
    orig = (restos.RecogerRestos, restos.drones_libres)
    restos.RecogerRestos, restos.drones_libres = Falso3, (lambda c, total: 2)
    try:
        t._zoom_a_muerte = lambda: None
        t.recoger_escombros_muerte([(700, 450)])
    finally:
        restos.RecogerRestos, restos.drones_libres = orig
    return t.sync.leer().get("muertes")


ok = prueba_olvidar_poco() == []
print(("OK   " if ok else "FALLO ") + "se olvida el punto si solo se vieron montones bajo el minimo")
fallos += 0 if ok else 1


def prueba_poco_no_es_fallo():
    """«poco» no cuenta como fallo: tras 3 montones bajo el minimo aun se prueba el siguiente."""
    import tareas.restos as restos
    t = _restos.RecogerRestos(Falso(), log=lambda *a: None, stop=threading.Event())
    t.cap = lambda etq: np.zeros((900, 1600, 3), np.uint8)
    secuencia = iter(["poco", "poco", "poco", "recogido"])
    t._probar_menu = lambda p, evitar=(): next(secuencia, None)
    orig = restos.iconos_restos
    restos.iconos_restos = lambda img: [(800, 450)]
    try:
        return t.recoger_iconos(1, fija=True)
    finally:
        restos.iconos_restos = orig


ok = prueba_poco_no_es_fallo() == 1
print(("OK   " if ok else "FALLO ") + "«poco» no cuenta como fallo al recorrer los montones de un sitio")
fallos += 0 if ok else 1

# cantidad_menu escala con el alto de la captura y el log de «poco» es legible
it = [{"texto": "Cantidad", "centro": (600, 600)}, {"texto": "18,5M", "centro": (610, 700)}]
ok = _restos.cantidad_menu(it, 1800) == "18,5M" and _restos.cantidad_menu(it, 900) == "" \
    and _restos._legible(1375) == "1.375" and _restos._legible(3_200_000) == "3,2 M" and _restos._legible(18_000_000) == "18 M"
print(("OK   " if ok else "FALLO ") + "cantidad_menu a otra resolucion y cifras legibles en el log")
fallos += 0 if ok else 1
_t.sleep = _t_sleep
print(f"\nFALLOS: {fallos}")
sys.exit(1 if fallos else 0)
