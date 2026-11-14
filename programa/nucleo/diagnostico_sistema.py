"""Diagnostico del equipo para NovaBot: comprueba requisitos y escribe un informe.

    python -m nucleo.diagnostico_sistema     (desde la carpeta programa; lo hace el bot al abrirse; o BOT.bat diagnostico)

Revisa: Python y sus librerias (con versiones), tkinter, BlueStacks, ADB,
instancias detectadas, carpeta de datos y ultimos errores. Escribe el informe
en %LOCALAPPDATA%\\NovaBot\\diagnostico.txt para poder enviarlo si algo falla.
"""
import importlib
import os
import platform
import sys
import time

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # la carpeta programa
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)


def _linea(ok, texto, detalle=""):
    return f"[{'OK' if ok else 'FALLO'}] {texto}" + (f"  {detalle}" if detalle else "")


def revisar():
    L, fallos = [], 0

    def anota(ok, texto, detalle=""):
        nonlocal fallos
        fallos += 0 if ok else 1
        L.append(_linea(ok, texto, detalle))

    L.append(f"NovaBot · diagnostico · {time.strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        from version import VERSION
        L.append(f"Version: {VERSION}")
    except Exception:                                            # noqa: BLE001
        L.append("Version: desconocida")
    L.append(f"Sistema: {platform.platform()}  ·  Python {sys.version.split()[0]} ({platform.architecture()[0]})")
    anota(sys.version_info >= (3, 10), "Python 3.10 o superior", sys.version.split()[0])
    for mod, pip in (("cv2", "opencv-python"), ("numpy", "numpy")):
        try:
            m = importlib.import_module(mod)
            anota(True, f"Libreria {pip}", getattr(m, "__version__", ""))
        except Exception as e:                                   # noqa: BLE001
            anota(False, f"Libreria {pip}", f"{e}  -> abre BOT.bat")
    ok_ocr = False
    for mod in ("rapidocr", "rapidocr_onnxruntime"):
        try:
            importlib.import_module(mod)
            ok_ocr = True
            break
        except Exception:                                        # noqa: BLE001
            continue
    anota(ok_ocr, "Lector de texto (RapidOCR, para leer eventos y misiones)",
          "" if ok_ocr else "-> abre BOT.bat")
    try:
        importlib.import_module("tkinter")
        anota(True, "tkinter (la ventana)")
    except Exception:                                            # noqa: BLE001
        anota(False, "tkinter (la ventana)", "reinstala Python marcando 'tcl/tk and IDLE'")
    # archivos del programa
    piezas = ("main.py", "version.py",
              "nucleo/adb.py", "nucleo/config.py", "nucleo/diagnostico.py", "nucleo/estadisticas.py",
              "vision/plantillas.py", "vision/pantallas.py", "vision/ocr.py", "vision/recursos.py",
              "tareas/base.py", "tareas/piratas/sigilo.py", "tareas/recompensas.py", "tareas/eventos.py",
              "tareas/ballenas/tarea.py", "tareas/cosmomante/juego.py", "tareas/roaming.py",
              "cerebro/rutina.py", "cerebro/planificador.py",
              "interfaz/ventana.py", "interfaz/panel.py",
              "recursos/rotulos/sigilo.png", "recursos/cifras/muestras.json", "recursos/NovaBot.ico")
    faltan = [f for f in piezas if not os.path.exists(os.path.join(AQUI, *f.split("/")))]
    anota(not faltan, "Archivos del programa", ("faltan: " + ", ".join(faltan)) if faltan else "completos")
    # BlueStacks, ADB e instancias
    try:
        from nucleo import adb as _adb
        adb = _adb.buscar_adb()
        anota(bool(adb), "ADB de BlueStacks", adb or "no encontrado: instala BlueStacks 5 y abre BOT.bat")
        inst = _adb.leer_instancias()
        anota(bool(inst), "Instancias de BlueStacks", ", ".join(f"{n}:{p}" for n, p in inst) or
              "ninguna: abre BlueStacks Multi-Instance Manager")
        if adb and inst:
            import subprocess
            fl = 0x08000000 if sys.platform == "win32" else 0
            try:
                out = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=10,
                                     creationflags=fl).stdout
                conect = [ln.split()[0] for ln in out.splitlines()[1:] if "\tdevice" in ln]
                anota(True, "Instancias conectadas por ADB ahora", ", ".join(conect) or "ninguna (abre BlueStacks)")
            except Exception as e:                               # noqa: BLE001
                anota(False, "adb devices", str(e))
    except Exception as e:                                       # noqa: BLE001
        anota(False, "Deteccion de BlueStacks", str(e))
    # datos
    from nucleo.rutas import carpeta_datos
    base = carpeta_datos()
    try:
        os.makedirs(base, exist_ok=True)
        prueba = os.path.join(base, ".escritura")
        with open(prueba, "w") as fh:
            fh.write("x")
        os.remove(prueba)
        anota(True, "Carpeta de datos escribible", base)
    except OSError as e:
        anota(False, "Carpeta de datos escribible", f"{base}: {e}")
    try:
        from nucleo import diagnostico
        ult = diagnostico.ultimos(5)
        L.append(f"Ultimos errores registrados: {len(ult)}")
        for e in ult:
            L.append(f"   {e.get('hora')}  {e.get('cuenta')}  {e.get('tarea')}: {e.get('error', '')[:120]}")
    except Exception:                                            # noqa: BLE001
        pass
    L.append("")
    L.append("TODO CORRECTO" if not fallos else f"{fallos} problema(s): corrige los [FALLO] de arriba.")
    return "\n".join(L), fallos, base


if __name__ == "__main__":
    texto, fallos, base = revisar()
    print(texto)
    try:
        with open(os.path.join(base, "diagnostico.txt"), "w", encoding="utf-8") as fh:
            fh.write(texto + "\n")
        print(f"\nInforme guardado en {os.path.join(base, 'diagnostico.txt')}")
    except OSError:
        pass
    sys.exit(1 if fallos else 0)
