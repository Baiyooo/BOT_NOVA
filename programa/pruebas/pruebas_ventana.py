"""Prueba de la ventana de verdad: crea Tk, la construye con cuentas falsas,
la pinta con estados falsos y la destruye. No toca ADB ni el juego ni los
datos reales (usa una carpeta temporal en LOCALAPPDATA).

    python pruebas\\pruebas_ventana.py
"""
import os
import sys
import tempfile
import time

os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo import adb  # noqa: E402

adb.leer_instancias = lambda: [(f"Cuenta {i}", 5555 + 10 * i) for i in range(1, 5)]
adb.buscar_adb = lambda: ""                      # sin ADB: ni sondeo ni nada de red
from interfaz import preferencias, tema, toasts, ventana  # noqa: E402

ventana.App._preparar_equipo = lambda self: None     # no instala ni busca paquetes
ventana.App._vigilar_version = lambda self: None


def sin_fallos(app):
    """Deja correr unos ciclos de Tk y revisa que ninguna llamada fallo."""
    for _ in range(5):
        app.update()
        app.update_idletasks()


app = ventana.App()
sin_fallos(app)
assert len(app.filas) == 4
assert list(app.pestanas.paginas) == ["instancias", "eventos", "estadisticas", "registro", "salud", "ajustes"]

# estado falso en una tarjeta: Ahora / Siguiente, contadores, estado con icono
f = app.filas[0]
f.estado = {"estado": "atacando", "plan": [
    {"k": "sigilo", "n": "Piratas de sigilo", "e": "ahora", "m": "radar listo"},
    {"k": "ballenas", "n": "Ballenas de éter", "e": "pendiente", "m": "quedan 2 hoy"},
    {"k": "gemas", "n": "Recoger gemas", "e": "pendiente", "m": "hay gemas"}],
    "rutina_hecho": 1, "rutina_total": 2, "sig_c": 0}
f._t0 = time.time() - 3725
f.hilo = type("H", (), {"is_alive": lambda s: True})()
f.pintar(f.estado)
f.pintar_hoy({"sigilo": 3, "normales": 2, "errores": 1}, {"ballenas": 1, "gemas": 4, "senuelos": 3})
assert f.lbl_ahora.cget("text").startswith("▶ Ahora: Piratas de sigilo · radar listo"), f.lbl_ahora.cget("text")
assert "Ballenas de éter · quedan 2 hoy" in f.lbl_sig.cget("text") and "(y 1 más)" in f.lbl_sig.cget("text")
assert "señuelos 3/10" in f.lbl_hoy.cget("text") and "4 gemas" in f.lbl_hoy.cget("text")
assert f.lbl_estado.cget("text").startswith("⚠"), f.lbl_estado.cget("text")      # icono + texto, no solo color
assert f.lbl_tiempo.cget("text") == "⏱ 1:02:05", f.lbl_tiempo.cget("text")
f.alternar_detalle()
f.anadir_accion("Prueba", lambda t: None)
sin_fallos(app)
app._vigilar_avisos()
assert app._estado_general[0] == "error" and "1 error" in app._estado_general[1]      # sin ADB = error
app.adb = "adb"
app._vigilar_avisos()
assert app._estado_general[0] == "aviso", app._estado_general
f.estado = {"estado": "sin tablero"}
app._vigilar_avisos()
assert app._estado_general[0] == "error", app._estado_general
f.hilo = None

# pestanas: se puede pasar por todas y se recuerda la ultima
for k in list(app.pestanas.paginas):
    app.pestanas.mostrar(k)
    sin_fallos(app)
assert preferencias.leer_prefs().get("pestana") == "ajustes"

# avisos emergentes: salen, se apilan y se cierran solos; el repetido no se duplica
assert toasts.avisar("Cuenta 1: sin conexión con BlueStacks.", "error", segundos=0.2)
assert not toasts.avisar("Cuenta 1: sin conexión con BlueStacks.", "error")
assert toasts.avisar("Tarea acabada", "ok", segundos=0.2)
sin_fallos(app)
assert len(toasts._vivos) >= 2           # (el «sin tablero» de arriba tambien avisó)
antes = len(toasts._vivos)
time.sleep(0.4)
sin_fallos(app)
assert len(toasts._vivos) == antes - 2, (antes, len(toasts._vivos))      # los dos cortos se cerraron solos
for w in list(toasts._vivos):                                           # clic: se cierra
    toasts._cerrar(w)
assert not toasts._vivos

# error repetido: tres ERROR seguidos de una cuenta = aviso
for _ in range(3):
    app.escribir("127.0.0.1:5565", "ERROR: prueba")
assert app._errores_repetidos == 1

# tamano y posicion se guardan y se recuperan
app.geometry("1200x760+30+40")
sin_fallos(app)
app._guardar_geometria()
g = preferencias.leer_prefs()["ventana"]
assert (g["w"], g["h"]) == (1200, 760) and not g["max"], g
app.geometry("1300x800+60+60")
sin_fallos(app)
app._geometria_inicial()                       # vuelve a lo guardado
sin_fallos(app)
assert (app.winfo_width(), app.winfo_height()) == (1200, 760), (app.winfo_width(), app.winfo_height())
assert app.minsize()[0] >= tema.ANCHO_MIN
app2 = app

# registro: filtros por cuenta, tipo y texto, con colores por tipo
app.escribir("127.0.0.1:5575", "paso normal de la cuenta dos")
app.escribir("127.0.0.1:5565", "ERROR: algo se rompió")
texto = lambda: app.txt.get("1.0", "end-1c")            # noqa: E731
assert "paso normal" in texto() and "ERROR: algo se rompió" in texto()
app.f_cuenta.set("Cuenta 2")
assert "paso normal" in texto() and "ERROR: algo se rompió" not in texto(), texto()
assert app.txt.tag_cget("error", "foreground") == tema.ROJO
app.f_cuenta.set("Todas")
app.f_tipo.set("Error")
assert "ERROR: algo se rompió" in texto() and "paso normal" not in texto(), texto()
app.f_tipo.set("Todo")
app.f_buscar.set("paso")
assert "paso normal" in texto() and "ERROR" not in texto(), texto()
app.f_buscar.set("")
assert "paso normal" in texto() and "ERROR: algo se rompió" in texto()
assert len(app._log_panel) > 0

# graficas: se leen las estadisticas y se dibuja por dia y por cuenta
from nucleo import estadisticas  # noqa: E402
estadisticas.sumar("127.0.0.1:5555", "sigilo", 3)
estadisticas.sumar("127.0.0.1:5555", "ballenas", 2)
estadisticas.sumar("127.0.0.1:5555", "gemas", 5)
estadisticas.sumar("127.0.0.1:5565", "sigilo", 1)
app.graficas.actualizar({"5555": "Cuenta 1", "5565": "Cuenta 2"}, forzar=True)
sin_fallos(app)
assert len(app.graficas.cv_dia.find_all()) > 0 and len(app.graficas.cv_cuenta.find_all()) > 0
assert "Piratas" in app.graficas.lbl_resumen.cget("text"), app.graficas.lbl_resumen.cget("text")
app.graficas.metrica.set("segundos")
app.graficas.rango.set("7 días")
sin_fallos(app)
assert "Horas en marcha" in app.graficas.lbl_resumen.cget("text")

# funciones por cuenta: órdenes de gemas y releer eventos (archivos de siempre)
import json  # noqa: E402
from nucleo.rutas import carpeta_datos  # noqa: E402
from tareas.ballenas.sync import _carpeta_sync  # noqa: E402


def leer_json(ruta):
    with open(ruta, encoding="utf-8") as fh:
        return json.load(fh)


f0 = app.filas[0]
app._recoger_gemas(f0)
orden = leer_json(os.path.join(_carpeta_sync(), "gemas.json"))
assert orden["cuentas"] == [str(f0.puerto)] and orden["t"] > 0
app._releer_eventos(f0)
releer = leer_json(os.path.join(carpeta_datos(), "releer_eventos.json"))
assert releer["cuentas"] == [str(f0.puerto)] and releer["t"] > 0

# horario por cuenta: se guarda, sale en los ajustes y viaja al planificador
app._guardar_horario(f0.puerto, {"sigilo": [[2, 8]]})
assert app.ajustes_de(f0.puerto)["horario"]["sigilo"] == [[2, 8]]
assert app._opciones_de(f0)["horario"]["sigilo"] == [[2, 8]]
from interfaz.horario import ventana_horario  # noqa: E402
guardado = {}
w = ventana_horario(app, tema.TEMA, "Cuenta 1", {"sigilo": [[2, 8]]}, guardado.update)
sin_fallos(app)
assert w.winfo_children() and guardado == {}          # se abre y aun no ha guardado
w.destroy()

# exportar ajustes: el archivo lleva opciones, rutina, horario y ballenas
datos = app._datos_exportar(f0.puerto)
assert datos["programa"] == "NovaBot" and "opciones" in datos and "rutina" in datos
assert datos["horario"]["sigilo"] == [[2, 8]]

# probar 1 ballena: pide confirmación y escribe la orden (sin arrancar nada)
from tkinter import messagebox  # noqa: E402
messagebox.askyesno, messagebox.showinfo = (lambda *a, **k: True), (lambda *a, **k: None)
app._cfg_ballenas = lambda: {str(f0.puerto): {"rol": "sola", "dia": 2}}
f0.hilo = type("H", (), {"is_alive": lambda s: True})()      # como si estuviera en marcha
app._probar_ballena(f0)
prueba = leer_json(os.path.join(_carpeta_sync(), "prueba.json"))
assert prueba["turnos"] == [{"lider": str(f0.puerto), "apoyo": ""}], prueba
f0.hilo = None

# salud: se construye, se refresca y el interruptor de la grafica se guarda
salud = app.salud
sin_fallos(app)
salud.actualizar(forzar=True)
sin_fallos(app)
assert set(salud.cifras) == {"cpu", "mem", "det", "ocr"}
assert salud.cifras["ocr"][0].cget("text") in ("Listo", "Falta")
assert len(salud._filas_adb) == len(app.filas)
salud.var_gpu.set(False)
salud._cambiar_gpu()
from nucleo import config as config_  # noqa: E402
from vision import gpu_compartida  # noqa: E402
assert config_.leer_config(os.path.join(carpeta_datos(), "gpu.json"))["usar_gpu"] is False
assert gpu_compartida.usar_gpu() is False
salud.var_gpu.set(True)
salud._cambiar_gpu()
assert gpu_compartida.usar_gpu() is True
# estado publicado por una cuenta: se lee y se pinta sin cargar el modelo
config_.guardar(os.path.join(carpeta_datos(), "detector_estado.json"),
                {"dispositivo": "GPU", "ms_por_imagen": 21.0, "motivo": "prueba",
                 "usar_gpu": True, "t": time.time(), "cuenta": "127.0.0.1:5565"})
salud.actualizar(forzar=True)
assert "GPU" in salud.cifras["det"][0].cget("text")
sin_fallos(app)
# reconectar sin adb: avisa y no revienta
app.adb = ""
salud.reconectar(f0.puerto)
sin_fallos(app)
app.adb = None

# 4 tarjetas caben en 1080p sin desplazar (a 100 % de escala)
alto_tarjetas = sum(t.winfo_reqheight() for t in app2.filas)
print("alto de 4 tarjetas:", alto_tarjetas, "px; cabecera:", app2.cielo.winfo_reqheight())
app2.destroy()
print("ventana real ok")
