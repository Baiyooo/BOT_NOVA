import sys
sys.path.insert(0, __import__("os").path.abspath(__file__).rsplit("pruebas", 1)[0])
import cv2
from nucleo import adb as _adb

adb = _adb.buscar_adb()
print("adb:", adb)
for nombre, puerto in _adb.leer_instancias():
    dev = f"127.0.0.1:{puerto}"
    try:
        ctrl = _adb.AdbController(dev, adb)
        img = ctrl.capture()
        ruta = __import__("os").path.expanduser(rf"~\Documents\NovaBot\_revision\captura_{puerto}.png")
        cv2.imwrite(ruta, img)
        print(dev, nombre, img.shape, "->", ruta)
    except Exception as e:
        print(dev, "ERROR", e)
