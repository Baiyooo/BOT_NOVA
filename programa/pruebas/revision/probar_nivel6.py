import sys
sys.path.insert(0, __import__("os").path.abspath(__file__).rsplit("pruebas", 1)[0])
import cv2
from tareas.cosmomante import juego

panel = cv2.imread(__import__("os").path.expandvars(r"%LOCALAPPDATA%\NovaBot\cosmomante_log\127.0.0.1_5575_20261031_010651_panel0.png"))
tablero = cv2.imread(__import__("os").path.expandvars(r"%LOCALAPPDATA%\NovaBot\cosmomante_log\127.0.0.1_5565_20261031_002451_baliza_desconocida.png"))

class C:
    name = "x"

t = juego.Cosmomante.__new__(juego.Cosmomante)
t.ctrl = C()
t.status = {"nivel": None}
estado = t.estado_nivel(panel)
rec = t.recursos(tablero)
print("estado:", estado)
print("recursos:", rec)
print("prob:", t.probabilidad_nivel6(estado, rec, simulaciones=200))
print("plan nivel:", t._plan_nivel({i: ("puntos", False) for i in range(50)}, 10, 3))
print("bonus hasta 30:", t._bonus(0, True, 30), "hasta 50:", t._bonus(0, True, 50))

# normales_con_metas: elegir la meta mas alta alcanzable
def probar(usados, disp):
    t = juego.Cosmomante.__new__(juego.Cosmomante)
    t.META = 100
    t.DADOS_META = {30: 3, 50: 5}
    t.parado = lambda: False
    t.log = lambda *a: None
    t.cap = lambda *a, **k: None
    t.disponibles = lambda img: disp
    t._aprendido = lambda: (None, {"recompensa_suma": True})
    t._tirar_hasta = lambda meta, ref: (ref.__setitem__("usados", meta) or True)
    t._cerrar_todo = lambda: None
    t._abrir = lambda: True
    t._guardar_aprendido = lambda d: None
    llamadas = []
    t.recoger_metas = lambda: llamadas.append("recoger") or 1
    t.status = {"nivel": None}
    t._guardar_pos = lambda *a: None
    n = t.normales_con_metas(usados)
    print(f"usados={usados} disp={disp} -> objetivo tirado={n} llamadas={llamadas}")

probar(30, 29)
probar(0, 29)
probar(0, 100)
