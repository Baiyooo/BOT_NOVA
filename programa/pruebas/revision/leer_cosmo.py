import sys
sys.path.insert(0, __import__("os").path.abspath(__file__).rsplit("pruebas", 1)[0])
import cv2
from tareas.cosmomante import juego
from vision import cifras

tablero = cv2.imread(__import__("os").path.expandvars(r"%LOCALAPPDATA%\NovaBot\cosmomante_log\127.0.0.1_5565_20261031_002451_baliza_desconocida.png"))
panel = cv2.imread(__import__("os").path.expandvars(r"%LOCALAPPDATA%\NovaBot\cosmomante_log\127.0.0.1_5575_20261031_010651_panel0.png"))

print("tablero", tablero.shape, "panel", panel.shape)
# numeros bajo los iconos de dados/objetos (1600x900)
for nombre, x in (("remoto", 87), ("azul", 214), ("dorado", 335), ("x2", 462)):
    caja = (x - 38, 810, x + 38, 868)
    print(nombre, caja, cifras.leer_cifras(tablero, caja))

# nivel y progreso en el panel
for etiqueta, caja in (
        ("nivel", (1240, 455, 1380, 515)),
        ("puntos", (1200, 515, 1400, 560)),
        ("celdas", (1200, 600, 1400, 645)),
        ("puntos2", (1180, 520, 1420, 570)),
        ("celdas2", (1180, 600, 1420, 655))):
    print(etiqueta, caja, cifras.leer_cifras(panel, caja))

# probar el metodo de estado y recursos
class CtrlFalso:
    name = "x"
t = juego.Cosmomante.__new__(juego.Cosmomante)
t.ctrl = CtrlFalso()
t.status = {"nivel": None}
print("nivel_actual:", juego.Cosmomante.nivel_actual(t, panel))
