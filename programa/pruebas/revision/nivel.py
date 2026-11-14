import sys
sys.path.insert(0, __import__("os").path.abspath(__file__).rsplit("pruebas", 1)[0])
import cv2
from vision import cifras

ruta = __import__("os").path.expandvars(r"%LOCALAPPDATA%\NovaBot\cosmomante_log\127.0.0.1_5575_20261031_010651_panel0.png")
img = cv2.imread(ruta)
print("shape", img.shape)
# cajas candidatas alrededor del numero de nivel (panel derecho)
cajas = [
    (1240, 455, 1380, 515),
    (1200, 450, 1420, 520),
    (1230, 470, 1390, 510),
    (1250, 465, 1360, 510),
    (1180, 440, 1450, 530),
]
for c in cajas:
    print(c, "->", cifras.leer_cifras(img, c, v_min=140))
# caja del 140/200 para comprobar que la escala de lectura va bien
print("140/200 ->", cifras.leer_cifras(img, (1200, 515, 1400, 555), v_min=140))
