import sys
sys.path.insert(0, __import__("os").path.abspath(__file__).rsplit("pruebas", 1)[0])
import cv2
import time
from nucleo import adb

ctrl = adb.AdbController("127.0.0.1:5585", adb.buscar_adb())
img = ctrl.capture()
cv2.imwrite(__import__("os").path.expanduser(r"~\Documents\NovaBot\_revision\estado_actual.png"), img)
# abrir "Eliminar piratas" (fila 3 de la lista)
ctrl.tap((800, 555))
time.sleep(4.0)
evento = ctrl.capture()
cv2.imwrite(__import__("os").path.expanduser(r"~\Documents\NovaBot\_revision\evento_piratas.png"), evento)
print("guardado", evento.shape)
