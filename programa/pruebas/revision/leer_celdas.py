import sys
sys.path.insert(0, __import__("os").path.abspath(__file__).rsplit("pruebas", 1)[0])
import cv2
from vision import cifras
img = cv2.imread(__import__("os").path.expandvars(r"%LOCALAPPDATA%\NovaBot\cosmomante_log\127.0.0.1_5575_20261031_010651_panel0.png"))
for y0, y1 in ((600, 645), (610, 650), (615, 655), (620, 660), (600, 660), (590, 650)):
    print("y", y0, y1, cifras.leer_cifras(img, (1180, y0, 1420, y1)))
for x0, x1 in ((1200, 1400), (1180, 1420), (1220, 1380), (1150, 1450)):
    print("x", x0, x1, cifras.leer_cifras(img, (x0, 610, x1, 655)))
