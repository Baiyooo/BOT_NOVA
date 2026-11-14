"""Ventana de control de NovaBot (Nova Empire).

Una tarjeta por instancia de BlueStacks: cada una con su tarea, su limite y
su boton de empezar/parar, y el estado en vivo. Todo funciona en el PC, sin
conexion a ninguna IA. Se arranca con main.py (o doble clic en BOT.bat).
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk

from nucleo import adb
from interfaz import panel
from interfaz.actualizacion import _Actualizacion
from interfaz.ajustes import _Ajustes
from interfaz.eventos import _PanelEventos
from interfaz.instancias import _Instancias
from interfaz.preferencias import guardar_prefs, leer_prefs
from interfaz.puente_panel import _PuentePanel
from interfaz.registro import _Registro
from interfaz.espacio import CieloEstelar
from interfaz.tema import AMBAR, BLANCO, BORDE, FONDO, PANEL, PANEL2, ROJO, SUAVE, TEAL, TEXTO, TINTA, VERDE, VIOLETA
from interfaz.widgets import Ayuda, Desplazable, _plano


class App(_Instancias, _Ajustes, _PanelEventos, _Registro, _PuentePanel, _Actualizacion, tk.Tk):
    def _poner_icono(self):
        """Icono propio en la ventana y en la barra de tareas (no el de Python)."""
        import os
        import sys
        ico = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "recursos", "NovaBot.ico")
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("NovaBot.App")
            except Exception:                       # noqa: BLE001
                pass
        if os.path.exists(ico):
            try:
                self.iconbitmap(default=ico)
            except tk.TclError:
                pass

    def __init__(self):
        super().__init__()
        self.title("NovaBot")
        self._poner_icono()
        self.configure(bg=FONDO)
        self.resizable(True, True)

        self.cola: queue.Queue[tuple[str, str]] = queue.Queue()
        self.parada = threading.Event()
        import multiprocessing as mp
        self.mp = mp.get_context("spawn")
        self.cola_mp = self.mp.Queue()
        self.adb = adb.buscar_adb()
        self.colores = {}                            # instancia -> color del registro

        self._cabecera()
        self._barra_acciones()
        self.cuerpo = Desplazable(self, FONDO)
        self.cuerpo.pack(fill="both", expand=True)
        self.zona = self.cuerpo.dentro
        self.conectadas: set = set()
        self._centro()
        self._instancias()
        self.panel_est = panel.PanelEstadisticas(self.zona, self.tema)
        self.panel_est.pack(fill="x", pady=(10, 0))
        self._ajustes()
        self._registro()
        self._sondear()
        self._preparar_equipo()
        self.cuerpo.texto = self.txt
        self.after(200, self._refrescar)
        self._version = self._huella()
        self._cambio_visto = None
        self._relanzando = False
        self.after(4000, self._vigilar_version)
        reanudar = leer_prefs().get("reanudar")
        if reanudar:
            d = leer_prefs()
            d.pop("reanudar", None)
            guardar_prefs(d)
            self.after(1500, lambda: self._reanudar(reanudar))
        self.update_idletasks()
        self.minsize(max(640, self.winfo_reqwidth()), min(self.winfo_reqheight(), 640))
        alto = min(self.winfo_screenheight() - 80, max(self.winfo_reqheight(), 900))
        self.geometry(f"{max(760, self.winfo_reqwidth())}x{alto}")
        self.protocol("WM_DELETE_WINDOW", self._cerrar)

    # ------------------------------------------------------------- montaje --
    def _centro(self):
        self.tema = {"FONDO": FONDO, "PANEL": PANEL, "PANEL2": PANEL2, "BORDE": BORDE, "TEXTO": TEXTO,
                     "SUAVE": SUAVE, "AMBAR": AMBAR, "TEAL": TEAL, "ROJO": ROJO, "VERDE": VERDE,
                     "VIOLETA": VIOLETA, "TINTA": TINTA, "BLANCO": BLANCO}
        self.panel = panel.PanelControl(self.zona, self.tema)
        self.panel.pack(fill="x", pady=(0, 10))

    def _cabecera(self):
        try:
            from version import VERSION
        except Exception:                               # noqa: BLE001
            VERSION = "?"
        self.cielo = CieloEstelar(self, "Centro de mando · Nova Empire en BlueStacks",
                                  VERSION, bool(self.adb), self.adb, al_actualizar=self._actualizar_archivo)
        self.cielo.pack(fill="x")
        self.lbl_resumen = self.cielo.lbl_resumen
        self.lbl_adb = self.cielo.lbl_adb
    def _barra_acciones(self):
        c = tk.Frame(self, bg=FONDO, padx=20)
        c.pack(fill="x", pady=(12, 12))
        self.b_jugar = _plano(c, "▶  Empezar todas", self.empezar, bg=AMBAR, fg=TINTA,
                              negrita=True, padx=14, pady=8)
        self.b_jugar.pack(side="left")
        Ayuda(self.b_jugar, "Empieza las cuentas marcadas que estén paradas.")
        self.b_parar = _plano(c, "■  Parar todas", self.parar, bg=PANEL2, fg=TEXTO,
                              negrita=True, padx=14, pady=8)
        self.b_parar.pack(side="left", padx=(8, 0))
        self.b_parar.config(state="disabled")
        self.b_emerg = _plano(c, "⚠  Emergencia", self.emergencia, bg=ROJO, fg=BLANCO,
                              negrita=True, padx=12, pady=8)
        self.b_emerg.pack(side="left", padx=(8, 0))
        Ayuda(self.b_emerg, "Corta ya todas las tareas, sin esperar al paso en curso.")
        self.b_foto = _plano(c, "Captura", self.captura, padx=12, pady=8)
        self.b_foto.pack(side="right")
        Ayuda(self.b_foto, "Guarda una captura de cada cuenta marcada.")
        self.b_check = _plano(c, "Comprobar tablero", self.comprobar, padx=12, pady=8)
        self.b_check.pack(side="right", padx=(0, 8))
        Ayuda(self.b_check, "Comprueba que el bot ve el tablero del Roaming Test.")

    # ------------------------------------------------------------ eventos --
    #  Eventos con ajustes propios aunque aun no se hayan leido del juego
    EV_FIJOS = (("cosmomante", "Cosmomante"), ("neural_roaming", "Neural Roaming"))
    MARCA_MISION = {"bot": ("●", TEAL, "la hace el bot"), "manual": ("✋", SUAVE, "la haces tú"),
                    "espera": ("…", AMBAR, "pendiente")}

    def _cerrar(self):
        if any(f.en_marcha() for f in self.filas):
            from tkinter import messagebox
            if not messagebox.askyesno("NovaBot", "Hay cuentas en marcha. "
                                       "¿Pararlas y cerrar?"):
                return
        self.parada.set()
        for f in self.filas:
            if f.parada is not None:
                f.parada.set()
        self.after(150, self.destroy)


def _avisar_fallo(texto: str) -> None:
    """Con pythonw no hay consola: el error se guarda y se enseña en un aviso."""
    import os
    from nucleo.rutas import carpeta_datos
    ruta = os.path.join(carpeta_datos(), "error_gui.log")
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write(texto)
    except OSError:
        pass
    try:
        from tkinter import messagebox
        raiz = tk.Tk()
        raiz.withdraw()
        messagebox.showerror(
            "NovaBot",
            "La ventana no ha podido arrancar.\n\n"
            + texto.strip().split("\n")[-1]
            + f"\n\nDetalle completo en:\n{ruta}")
        raiz.destroy()
    except Exception:                               # noqa: BLE001
        pass
