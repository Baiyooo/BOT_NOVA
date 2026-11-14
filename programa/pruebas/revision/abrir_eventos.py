import sys
sys.path.insert(0, __import__("os").path.abspath(__file__).rsplit("pruebas", 1)[0])
import cv2
import time
from vision import plantillas
from nucleo import adb

dev = "127.0.0.1:5585"
ctrl = adb.AdbController(dev, adb.buscar_adb())
img = ctrl.capture()
p, c, e = plantillas.localizar(img, "eventos")
print("eventos:", p, c, e)
if p < 0.80:
    print("no veo Eventos; guardo captura y salgo")
    cv2.imwrite(__import__("os").path.expanduser(r"~\Documents\NovaBot\_revision\eventos_antes.png"), img)
    raise SystemExit(1)
ctrl.tap((c[0], c[1] - int(img.shape[0] * 0.06)))
time.sleep(3.0)
lista = ctrl.capture()
cv2.imwrite(__import__("os").path.expanduser(r"~\Documents\NovaBot\_revision\eventos_lista.png"), lista)
print("lista guardada", lista.shape)
