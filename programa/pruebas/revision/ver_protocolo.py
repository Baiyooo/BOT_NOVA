import sys, threading
sys.path.insert(0, __import__("os").path.abspath(__file__).rsplit("pruebas", 1)[0])
import cv2
from tareas.cosmomante import juego
from nucleo import adb

ctrl = adb.AdbController("127.0.0.1:5565", adb.buscar_adb())
t = juego.Cosmomante(ctrl, log=lambda n, m: print("LOG", m), stop=threading.Event(), diag=False)
img = t._abrir_protocolo_cosmo()
if img is not None:
    cv2.imwrite(__import__("os").path.expanduser(r"~\Documents\NovaBot\_revision\protocolo_cosmo.png"), img)
    print("guardado protocolo", img.shape)
else:
    print("no pude abrir protocolo")
t._cerrar_todo()
