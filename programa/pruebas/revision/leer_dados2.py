import sys
sys.path.insert(0, __import__("os").path.abspath(__file__).rsplit("pruebas", 1)[0])
import cv2
from vision import cifras
img = cv2.imread(__import__("os").path.expandvars(r"%LOCALAPPDATA%\NovaBot\cosmomante_log\127.0.0.1_5565_20261031_002451_baliza_desconocida.png"))
for y0, y1 in ((840, 890), (845, 885), (850, 880), (830, 890)):
    print("y", y0, y1)
    for nombre, x in (("remoto", 87), ("azul", 214), ("dorado", 335), ("x2", 462)):
        print("  ", nombre, cifras.leer_cifras(img, (x - 40, y0, x + 40, y1)))
