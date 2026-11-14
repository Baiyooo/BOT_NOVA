"""Punto de entrada de NovaBot.

    python main.py                 abre la ventana (es lo que hace BOT.bat)
    python main.py --menu          menu en modo texto (BOT.bat texto)
    python main.py --activar-adb   activa el ADB de BlueStacks (BOT.bat, la primera vez)
    python main.py --help          resto de opciones del Roaming Test por linea de comandos

Como esta organizado el programa:
    nucleo/    lo que no sabe nada del juego: ADB, datos, rutas, errores, actualizador
    vision/    ver la pantalla: plantillas, mascaras de color, texto, cifras
    tareas/    actuar en el juego: una tarea por modulo o paquete
    cerebro/   decidir: la Rutina y lo que se sabe de los eventos
    interfaz/  mostrar: la ventana, el panel y el menu de texto
    recursos/  imagenes de referencia (PNG) e icono
    pruebas/   pruebas y scripts de revision
"""
import multiprocessing
import os
import sys
import traceback


def _fallo_sin_ventana(texto):
    """Si ni siquiera se puede cargar la ventana, se deja el error en un archivo."""
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".novabot")
    ruta = os.path.join(base, "NovaBot", "error_gui.log")
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write(texto)
    except OSError:
        pass


def ventana():
    try:
        from interfaz.ventana import App
        App().mainloop()
    except Exception:                               # noqa: BLE001
        texto = traceback.format_exc()
        try:
            from interfaz.ventana import _avisar_fallo
            _avisar_fallo(texto)
        except Exception:                           # noqa: BLE001
            _fallo_sin_ventana(texto)
        raise SystemExit(1) from None


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if len(sys.argv) > 1:
        from interfaz import menu_texto
        menu_texto.main()
    else:
        ventana()
