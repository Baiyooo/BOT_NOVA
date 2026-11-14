"""Pruebas de la tarea «Recolección» (sin BlueStacks ni ADB):

    python pruebas\\pruebas_recoleccion.py

 - recoge SOLO gemas y/o escombros, lo que se marque; suministros, recompensas y el
   resto de la Rutina no los hace nunca;
 - filtra lo que propone el planificador;
 - las gemas se recogen cada 5 min si hay un dron libre, o cuando se piden a mano;
 - el desplegable de tareas la ofrece.
"""
import os
import sys
import tempfile
import time

os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cerebro import planificador as plan  # noqa: E402
from cerebro import rutina  # noqa: E402
from interfaz import catalogo, panel  # noqa: E402

fallos = 0


def ok(nombre, cond, extra=""):
    global fallos
    print(("OK   " if cond else "FALLO ") + nombre + (f" {extra}" if extra else ""))
    fallos += 0 if cond else 1


class Falso:
    name = "127.0.0.1:5001"


TODO = ("gratis", "eventos", "recompensas", "destacamento", "simulacion", "sigilo", "normales", "ballenas",
        "cosmomante", "roaming", "artefactos", "bingo", "llamar_flotas")

# ---- solo gemas y escombros, lo marcado
r = rutina.SoloRecoleccion(Falso(), que={"gemas": True, "escombros": True, "gratis": True, "eventos": True,
                                         "recompensas": True, "sigilo": True, "ballenas": True})
ok(f"solo gemas y escombros: {sorted(r._elegidas)}", r._elegidas == {"gemas", "escombros"})
ok("suministros, recompensas, piratas, ballenas...: nada", not any(r.que[k] for k in TODO))
ok("las gemas van aparte (no por el planificador)", r.que["gemas"] is False and r.recoger_gemas is True)
ok("no lee eventos (no hace falta)", r._leido_sesion is True)
solo_esc = rutina.SoloRecoleccion(Falso(), que={"escombros": True, "gemas": False})
ok("solo escombros: sin gemas", solo_esc._elegidas == {"escombros"} and solo_esc.recoger_gemas is False)
solo_gem = rutina.SoloRecoleccion(Falso(), que={"gemas": True, "escombros": False})
ok("solo gemas: sin escombros", solo_gem._elegidas == {"gemas"} and solo_gem.que["escombros"] is False)
ninguna = rutina.SoloRecoleccion(Falso(), que={})
ok("sin nada marcado no hace nada", ninguna._elegidas == set() and not any(ninguna.que.values()))
ok("nombre de la tarea", rutina.SoloRecoleccion.NOMBRE == "Recolección")

# ---- filtra lo que propone el planificador
propuestas = [plan.Accion(100, "leer_eventos", "x", {}), plan.Accion(90, "gratis", "x", {}),
              plan.Accion(80, "recompensas", "x", {}), plan.Accion(70, "eventos", "x", {}),
              plan.Accion(60, "sigilo", "x", {}), plan.Accion(55, "escombros", "x", {}),
              plan.Accion(103, "ballenas", "x", {}), plan.Accion(102, "gemas", "x", {})]
original = rutina.Rutina._decidir
rutina.Rutina._decidir = lambda self, est: list(propuestas)
try:
    claves = [a.clave for a in r._decidir({})]
    claves_esc = [a.clave for a in solo_esc._decidir({})]
finally:
    rutina.Rutina._decidir = original
ok(f"filtra el planificador: {claves}", claves == ["escombros", "gemas"])
ok(f"solo escombros: {claves_esc}", claves_esc == ["escombros"])

# ---- gemas cada 5 min con algun dron libre, o por orden manual
ok("gemas: la primera vez (con drones libres) toca", r._gemas_pedidas({"gemas_t": 0}) is True)
ok("gemas: hace poco que se recogieron, no toca", r._gemas_pedidas({"gemas_t": time.time()}) is False)
ok("gemas: desmarcadas, nunca", solo_esc._gemas_pedidas({"gemas_t": 0}) is False)

# ---- «siguiente»: solo lo suyo, nunca la lectura de eventos (horas)
ahora = time.time()
est = {"gemas_t": ahora, "escombros_t": ahora, "lectura_t": ahora}
sig = r._proxima_espera(est) - ahora
ok(f"siguiente con gemas y escombros: {sig:.0f} s (<= 5 min)", 0 < sig <= 5 * 60 + 1)
sig_g = solo_gem._proxima_espera({"gemas_t": ahora, "lectura_t": ahora}) - ahora
ok(f"solo gemas: {sig_g:.0f} s", 0 < sig_g <= 5 * 60 + 1)
sig_e = solo_esc._proxima_espera({"escombros_t": ahora, "lectura_t": ahora}) - ahora
ok(f"solo escombros: {sig_e:.0f} s (<= 10 min)", 0 < sig_e <= 10 * 60 + 1)
sig_n = ninguna._proxima_espera({"lectura_t": ahora}) - ahora
ok(f"sin nada marcado: {sig_n:.0f} s (no horas)", 0 < sig_n <= 121)
ok("la Rutina automatica sigue como siempre (cuenta la lectura de eventos)",
   rutina.Rutina(Falso(), que={"sigilo": False, "gratis": False, "eventos": False})._proxima_espera(
       {"lectura_t": ahora}) - ahora > 3600)

# ---- arranca de inmediato: el planificador propone los escombros nada mas empezar, y la tarea avisa
ahora_ = time.time()
prim = [a.clave for a in plan.decidir({"_leido_sesion": True, "_drones_libres": 3}, {"escombros": True}, None,
                                      ahora=ahora_, opciones={})]
ok(f"arranca de inmediato: escombros propuestos al empezar {prim}", "escombros" in prim)
mensajes = []
original_run = rutina.Rutina.run
rutina.Rutina.run = lambda self, ciclos=0: mensajes.append("RUTINA")
try:
    r._log = lambda *a: mensajes.append(str(a[-1]))
    r.run()
    ninguna._log = lambda *a: mensajes.append(str(a[-1]))
    ninguna.run()
finally:
    rutina.Rutina.run = original_run
ok("al empezar dice que va al visor del sistema, con la vista, y pasa a la Rutina",
   any("visor del sistema" in m and "2D" in m and "gemas y escombros" in m for m in mensajes)
   and "RUTINA" in mensajes)
ok("sin nada marcado avisa y no arranca", any("no hay nada marcado" in m for m in mensajes)
   and mensajes.count("RUTINA") == 1)

# ---- lote de 6 gemas en ~30 s y vuelta a empezar cuando regresan los drones
ok("lote de 6 gemas en 30 s", rutina.SoloRecoleccion.LOTE == 6 and rutina.SoloRecoleccion.LIMITE_LOTE == 30)
ahora = time.time()
original_oc = rutina.drones_ocupados
r.b_robots = 7
try:
    rutina.drones_ocupados = lambda cuenta: [ahora + 200, ahora + 210, ahora + 220, ahora + 230, ahora + 240, ahora + 250]
    sig = r._gemas_toca({"gemas_t": ahora - 60, "gemas_n": 6}) - ahora
    ok(f"tras mandar 6, espera a que vuelvan (~{sig:.0f} s, no 5 min fijos)", 235 < sig < 245)
    ok("antes de que vuelvan no toca", r._gemas_pedidas({"gemas_t": ahora - 60, "gemas_n": 6}) is False)
    rutina.drones_ocupados = lambda cuenta: []
    ok("con los drones de vuelta, toca otro lote", r._gemas_pedidas({"gemas_t": ahora - 60, "gemas_n": 6}) is True)
    ok("no repite antes de 30 s", r._gemas_pedidas({"gemas_t": ahora - 5, "gemas_n": 6}) is False)
    sig0 = r._gemas_toca({"gemas_t": ahora, "gemas_n": 0}) - ahora
    ok(f"si no habia gemas, vuelve a mirar en 5 min ({sig0:.0f} s)", 295 < sig0 <= 300)
finally:
    rutina.drones_ocupados = original_oc

# ---- gemas con aro azul (las recoge un compañero): no se tocan
import numpy as np  # noqa: E402
from tareas.ballenas import deteccion  # noqa: E402

lienzo = np.zeros((900, 1600, 3), np.uint8)
lienzo[400:420, 300:320] = (255, 120, 0)                  # azul vivo (BGR)
ok("aro azul alrededor: es de un compañero", deteccion._azul_cerca(lienzo, (310, 410)) is True)
ok("sin azul: libre", deteccion._azul_cerca(lienzo, (900, 500)) is False)

# ---- los ajustes de la cuenta: solo dos casillas
ok(f"casillas de Recolección: {[k for k, _t, _a in panel.PASOS_RECOLECCION]}",
   [k for k, _t, _a in panel.PASOS_RECOLECCION] == ["gemas", "escombros"]
   and set(panel.RECOLECCION_DEFECTO) == {"gemas", "escombros"})

# ---- el desplegable de tareas la ofrece
ok("desplegable: grupo «Recolección»", any(g == "Recolección" for g, _ in catalogo.TAREA_GRUPOS))
ok("desplegable: tarea -> clave", catalogo.TAREA_FILA.get("Recolección (a elegir)") == "recoleccion")
ok("sin limite de tiempo", catalogo.UNIDAD.get("recoleccion") is None and "recoleccion" in catalogo.AYUDA_TAREA)
ok("la ayuda dice gemas y escombros", "gemas" in catalogo.AYUDA_TAREA["recoleccion"].lower()
   and "escombros" in catalogo.AYUDA_TAREA["recoleccion"].lower()
   and "suministros" not in catalogo.AYUDA_TAREA["recoleccion"].lower())

print(f"\nFALLOS: {fallos}")
sys.exit(1 if fallos else 0)
