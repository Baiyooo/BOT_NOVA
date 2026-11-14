import sys
sys.path.insert(0, __import__("os").path.abspath(__file__).rsplit("pruebas", 1)[0])
import numpy as np
import cv2
from tareas.cosmomante import base as MB
from tareas.cosmomante import juego as M
from tareas.cosmomante import mapa as cm

PANEL = __import__("os").path.expandvars(r"%LOCALAPPDATA%\NovaBot\cosmomante_log\127.0.0.1_5575_20261031_010651_panel0.png")


class Ctrl:
    name = "fake:1"
    drag_ms = 180

    def capture(self):
        return np.zeros((900, 1600, 3), np.uint8)

    def tap(self, p):
        pass

    def drag(self, a, b):
        pass

    def back(self):
        pass


def nuevo():
    t = M.Cosmomante(Ctrl(), log=lambda *a: None, diag=False)
    t.cap = lambda etiqueta="": np.zeros((900, 1600, 3), np.uint8)
    t._tap = lambda img, xy: None
    t._quitar_avisos = lambda *a, **k: True
    t._registrar = lambda *a, **k: None
    t._guardar_pos = lambda *a, **k: None
    t._cerrar_panel = lambda *a, **k: None
    t.puede_ascender = lambda img: True
    t._en_tablero = lambda img: True
    t._dialogo_abierto = lambda img: False
    t.log = lambda *a, **k: None
    return t


# 1) lectura del nivel en una captura real
img = cv2.imread(PANEL)
print("nivel leido:", M.Cosmomante.nivel_actual(None, img))

# 2) ascenso desde nivel 1 hasta 6 (cada nivel se lee antes y despues)
t = nuevo()
niveles = iter([1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6])
t.nivel_actual = lambda img: next(niveles, 6)
cm.filas_panel = lambda img: True
print("subidos:", t.ascender(), "nivel final:", t.status["nivel"],
      "ascensos:", t.status["ascensos"])

# 3) si ya esta en 6 no pulsa
t2 = nuevo()
t2.nivel_actual = lambda img: 6
print("ya en 6, subidos:", t2.ascender(), "nivel:", t2.status["nivel"])

# 4) orden del run unificado: jugar -> normales -> ascender -> reclamar metas
t3 = nuevo()
t3.MULTIPLICADORES = True
t3.ASCENDER = True
t3.NORMALES = True
t3._abrir = lambda: True
t3.progreso_semana = lambda: 10
t3._pos_pendiente = False
t3._perder_pos = lambda: None
t3._tirar = lambda *a, **k: True
orden = []


def jugar():
    orden.append("jugar")
    return 1


def normales(usados):
    orden.append(("normales", usados))
    return 2


def ascender():
    orden.append("ascender")
    t3.status["nivel"] = 6
    return 5


def recoger():
    orden.append("recoger")
    return 3


t3.jugar = jugar
t3.normales_con_metas = normales
t3.ascender = ascender
t3.recoger_metas = recoger
t3._cerrar_todo = lambda: orden.append("cerrar")
M.localizar = MB.localizar = lambda img, nombre: (0.0, (0, 0), 1.0)
t3.run()
print("orden:", orden)
print("status:", {k: t3.status.get(k) for k in ("nivel", "ascensos", "recogidas", "estado")})

# 5) con la meta de 100 ya cumplida: no tira dados, pero SI reclama la meta
t6 = nuevo()
t6.MULTIPLICADORES = False
t6.ASCENDER = False
t6.NORMALES = True
t6._abrir = lambda: True
t6.progreso_semana = lambda: 100
t6._perder_pos = lambda: None
t6._tirar = lambda *a, **k: True
reclamos = []
t6.recoger_metas = lambda: (reclamos.append(1) or 4)
t6._cerrar_todo = lambda: None
t6.run()
print("meta 100 ya hecha -> reclamos:", reclamos, "recogidas:", t6.status["recogidas"])
