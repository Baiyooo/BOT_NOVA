import sys, threading
sys.path.insert(0, __import__("os").path.abspath(__file__).rsplit("pruebas", 1)[0])
from tareas.cosmomante import juego
from nucleo import adb

ctrl = adb.AdbController("127.0.0.1:5565", adb.buscar_adb())
t = juego.Cosmomante(ctrl, log=lambda n, m: print("LOG", n, m), stop=threading.Event(), diag=False)
print("Abriendo Cosmomante (solo lectura)...")
if not t._abrir():
    print("No he podido abrir Cosmomante.")
    raise SystemExit(1)
print("Abierto. Leyendo estado...")
estado = t.leer_estado_nivel()
print("estado:", estado)
img = t.cap("tablero")
rec = t.recursos(img)
print("recursos:", rec)
try:
    print("usados esta semana:", t.progreso_semana())
except Exception as e:
    print("no pude leer usados:", e)
print("probabilidad nivel 6:", t.probabilidad_nivel6(estado, rec, simulaciones=300))
print("Fin: no se ha tirado ningun dado.")
