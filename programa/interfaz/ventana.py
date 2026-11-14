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
from interfaz.catalogo import NOMBRE_TAREA as TAREA_FILA_INV
from interfaz.eventos import _PanelEventos
from interfaz.graficas import Graficas
from interfaz.instancias import _Instancias
from interfaz.preferencias import guardar_prefs, leer_prefs
from interfaz.puente_panel import _PuentePanel
from interfaz.registro import _Registro
from interfaz.salud import Salud
from interfaz.espacio import CieloEstelar, factor_escala
from interfaz import toasts
from interfaz.tema import (ALTO_MIN, AMBAR, ANCHO_MIN, BLANCO, BORDE, ESP_L, ESP_M, ESP_S, FONDO, PANEL, PANEL2, ROJO,
                           SUAVE, TAM_M, TAM_S, TEAL, TEMA, TEXTO, TINTA, fuente, titular)
from interfaz.widgets import Ayuda, Desplazable, Pestanas, _plano

try:
    from version import VERSION
except Exception:                                       # noqa: BLE001
    VERSION = "?"


def _dpi_consciente():
    """Windows: que la ventana se dibuje nitida con escalado 125 % / 150 %
    (si no, Windows la estira y sale borrosa). Tk ajusta solo sus tamanos."""
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:                                   # noqa: BLE001
        pass


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

    #  pestanas: (clave, icono, titulo)
    PESTANAS = (("instancias", "▣", "Instancias"), ("eventos", "★", "Eventos"),
                ("estadisticas", "▤", "Estadísticas"), ("registro", "☰", "Registro"),
                ("salud", "♥", "Salud"), ("ajustes", "⚙", "Ajustes"))

    def __init__(self):
        _dpi_consciente()                            # antes de crear la ventana: nitida con 125 % / 150 %
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
        self._errores_t: dict[str, list[float]] = {}  # para el aviso de error repetido
        self._errores_repetidos = 0
        self._sondeado = False
        self._estado_general = ("ok", "Todo bien")
        self.conectadas: set = set()
        self.tema = TEMA
        toasts.instalar(self)

        self._cabecera()
        self._barra_acciones()
        self._pestanas()
        self._ajustes()
        self._instancias(self.zona)
        self._eventos(self.zona_eventos)
        self.panel = panel.PanelControl(self.zona_estadisticas, self.tema)
        self.panel.pack(fill="x", pady=(0, ESP_L))
        self.panel_est = panel.PanelEstadisticas(self.zona_estadisticas, self.tema)
        self.panel_est.abierto.set(True)
        self.panel_est._pintar_boton()
        self.panel_est.pack(fill="x")
        self.graficas = Graficas(self.zona_estadisticas, self.tema)
        self.graficas.pack(fill="x", pady=(ESP_L, 0))
        self._registro(self.pag_registro)
        self._pagina_salud()
        self._pagina_ajustes()
        self._sondear()
        self._preparar_equipo()
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
        self._geometria_inicial()
        self.protocol("WM_DELETE_WINDOW", self._cerrar)
        self.bind("<Configure>", self._al_cambiar_tamano)
        self.after(1500, self._aviso_version_nueva)

    # ------------------------------------------------------------- montaje --
    def _cabecera(self):
        self.cielo = CieloEstelar(self, "Centro de mando · Nova Empire en BlueStacks",
                                  VERSION, bool(self.adb), self.adb, al_actualizar=self._actualizar_archivo)
        self.cielo.pack(fill="x")
        self.lbl_resumen = self.cielo.lbl_resumen
        self.lbl_adb = self.cielo.lbl_adb

    def _barra_acciones(self):
        c = tk.Frame(self, bg=FONDO, padx=ESP_L)
        c.pack(fill="x", pady=(ESP_M, ESP_M))
        self.b_jugar = _plano(c, "▶  Empezar todas", self.empezar, bg=AMBAR, fg=TINTA,
                              negrita=True, padx=ESP_L, pady=ESP_M - 2)
        self.b_jugar.pack(side="left")
        Ayuda(self.b_jugar, "Empieza las cuentas marcadas que estén paradas.")
        self.b_parar = _plano(c, "■  Parar todas", self.parar, bg=PANEL2, fg=TEXTO,
                              negrita=True, padx=ESP_L, pady=ESP_M - 2)
        self.b_parar.pack(side="left", padx=(ESP_M, 0))
        self.b_parar.config(state="disabled")
        self.b_emerg = _plano(c, "⚠  Emergencia", self.emergencia, bg=ROJO, fg=BLANCO,
                              negrita=True, padx=ESP_L, pady=ESP_M - 2)
        self.b_emerg.pack(side="left", padx=(ESP_M, 0))
        Ayuda(self.b_emerg, "Corta ya todas las tareas, sin esperar al paso en curso.")
        self.b_foto = _plano(c, "▣ Captura", self.captura, padx=ESP_L, pady=ESP_M - 2)
        self.b_foto.pack(side="right")
        Ayuda(self.b_foto, "Guarda una captura de cada cuenta marcada.")
        self.b_check = _plano(c, "Comprobar tablero", self.comprobar, padx=ESP_L, pady=ESP_M - 2)
        self.b_check.pack(side="right", padx=(0, ESP_M))
        Ayuda(self.b_check, "Comprueba que el bot ve el tablero del Roaming Test.")
        #  sitio para botones o menus que anadan otros bloques («Más acciones»...)
        self.barra_extra = tk.Frame(c, bg=FONDO)
        self.barra_extra.pack(side="right", padx=(0, ESP_M))

    def _pestanas(self):
        """Barra lateral con las pestanas y una pagina para cada una."""
        self.pestanas = Pestanas(self, al_cambiar=self._al_cambiar_pestana)
        self.pestanas.pack(fill="both", expand=True)
        pag = {k: self.pestanas.anadir(k, i, t) for k, i, t in self.PESTANAS}
        # Instancias, Eventos y Estadisticas: zonas que se bajan con la rueda
        zonas = {}
        for k in ("instancias", "eventos", "estadisticas"):
            d = Desplazable(pag[k], FONDO)
            d.pack(fill="both", expand=True)
            zonas[k] = d
        self.cuerpo = zonas["instancias"]
        self.zona = zonas["instancias"].dentro
        self.zona_eventos = zonas["eventos"].dentro
        self.zona_estadisticas = zonas["estadisticas"].dentro
        self.pag_registro = pag["registro"]            # el registro se baja solo
        self.pag_salud = pag["salud"]
        self.pag_ajustes = pag["ajustes"]
        self.zona_salud = self.pag_salud               # lo rellena otro bloque
        self.pestanas.mostrar(leer_prefs().get("pestana", "instancias"))
        self._pest_lista = True

    def _al_cambiar_pestana(self, clave: str):
        """Recuerda la ultima pestana abierta."""
        if getattr(self, "_pest_lista", False):
            d = leer_prefs()
            if d.get("pestana") != clave:
                d["pestana"] = clave
                guardar_prefs(d)

    def _pagina_salud(self):
        """Pestana Salud: equipo, detector y conexión de cada cuenta."""
        self.salud = Salud(self.zona_salud, self.tema, self)
        self.salud.pack(fill="both", expand=True)

    def _pagina_ajustes(self):
        """Pestana Ajustes: acceso a los ajustes de cada cuenta (los de siempre)."""
        for w in list(self.pag_ajustes.winfo_children() or []):
            w.destroy()
        tk.Label(self.pag_ajustes, text="◆  AJUSTES POR CUENTA", bg=FONDO, fg=TEAL, font=titular(TAM_M)
                 ).pack(anchor="w", padx=ESP_L, pady=(ESP_M, ESP_S))
        tk.Label(self.pag_ajustes, text="Cada cuenta tiene los suyos: Rutina, Piratas, Ballenas, Cosmomante…",
                 bg=FONDO, fg=SUAVE, font=fuente(TAM_S)).pack(anchor="w", padx=ESP_L, pady=(0, ESP_M))
        nombres = self._nombres()
        for f in self.filas:
            fila = tk.Frame(self.pag_ajustes, bg=PANEL, padx=ESP_L, pady=ESP_M,
                            highlightthickness=1, highlightbackground=BORDE)
            fila.pack(fill="x", padx=ESP_L, pady=ESP_S)
            tk.Label(fila, text="●", bg=PANEL, fg=f.color, font=fuente(TAM_M)).pack(side="left")
            tk.Label(fila, text=nombres.get(str(f.puerto), f.nombre), bg=PANEL, fg=TEXTO,
                     font=titular(TAM_M)).pack(side="left", padx=(ESP_M, 0))
            b = _plano(fila, "⚙ Abrir ajustes", lambda f=f: self._ajustes_cuenta(f), padx=ESP_L, pady=ESP_S)
            b.pack(side="right")
            resumen = self._resumen_ajustes(f)
            if resumen:
                tk.Label(fila, text=resumen, bg=PANEL, fg=SUAVE, font=fuente(TAM_S), anchor="w"
                         ).pack(side="left", padx=(ESP_M, 0))

    def _resumen_ajustes(self, f) -> str:
        """Una línea con lo que tiene puesto una cuenta (tarea, ballenas y horario)."""
        p = str(f.puerto)
        partes = []
        try:
            tarea = (leer_prefs().get("tareas") or {}).get(p) or f.tarea()
            partes.append(TAREA_FILA_INV.get(tarea, tarea))
        except Exception:                                    # noqa: BLE001
            pass
        try:
            from cerebro import config_ballenas as cb
            cfg = (leer_prefs().get("ballenas") or {}).get(p)
            if isinstance(cfg, dict) and cb.normalizar(cfg)["rol"] != "no":
                partes.append(cb.resumen(cfg, self._nombres()))
        except Exception:                                    # noqa: BLE001
            pass
        try:
            from interfaz.horario import TAREAS_HORARIO
            horario = self.ajustes_de(p).get("horario") or {}
            nombres_t = dict(TAREAS_HORARIO)
            franjas = "; ".join(nombres_t.get(k, k) + " " + ", ".join(f"{a}-{b}" for a, b in v)
                                for k, v in horario.items() if v)
            if franjas:
                partes.append("sin " + franjas)
        except Exception:                                    # noqa: BLE001
            pass
        return "  ·  ".join(x for x in partes if x)

    def refrescar_instancias(self):
        super().refrescar_instancias()
        self._pagina_ajustes()

    # ------------------------------------------------------ tamano y posicion --
    def _geometria_inicial(self):
        """Tamano y posicion de la vez anterior (si caben en la pantalla)."""
        self.update_idletasks()
        k = factor_escala(self)
        min_w, min_h = round(ANCHO_MIN * k), round(ALTO_MIN * k)
        self.minsize(min_w, min_h)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        g = leer_prefs().get("ventana")
        if isinstance(g, dict) and all(isinstance(g.get(c), int) for c in ("w", "h", "x", "y")):
            w, h = max(min_w, min(g["w"], sw)), max(min_h, min(g["h"], sh))
            x = max(0, min(g["x"], sw - 80))              # que no quede fuera de la pantalla
            y = max(0, min(g["y"], sh - 80))
            self.geometry(f"{w}x{h}+{x}+{y}")
            if g.get("max"):
                try:
                    self.state("zoomed")
                except tk.TclError:
                    pass
        else:
            w = max(min_w, min(round(980 * k), sw - 40))
            h = max(min_h, min(round(900 * k), sh - 80))
            self.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")

    def _al_cambiar_tamano(self, e):
        if e.widget is self:
            if getattr(self, "_guardar_geo", None):
                self.after_cancel(self._guardar_geo)
            self._guardar_geo = self.after(800, self._guardar_geometria)

    def _guardar_geometria(self):
        """Guarda tamano y posicion en ventana.json (%LOCALAPPDATA%\\NovaBot)."""
        self._guardar_geo = None
        try:
            maximizada = self.state() == "zoomed"
            if maximizada:                    # se guarda el tamano normal, no el maximizado
                previo = leer_prefs().get("ventana") or {}
                datos = {**{c: previo.get(c) for c in ("w", "h", "x", "y")}, "max": True}
                if not all(isinstance(datos[c], int) for c in ("w", "h", "x", "y")):
                    return
            elif self.state() == "normal":
                datos = {"w": self.winfo_width(), "h": self.winfo_height(),
                         "x": self.winfo_x(), "y": self.winfo_y(), "max": False}
            else:
                return
            d = leer_prefs()
            if d.get("ventana") != datos:
                d["ventana"] = datos
                guardar_prefs(d)
        except tk.TclError:
            pass

    def _aviso_version_nueva(self):
        """Si la version es distinta de la que se vio la ultima vez: aviso de
        «version nueva instalada»."""
        d = leer_prefs()
        vista = d.get("version_vista")
        if vista != VERSION:
            d["version_vista"] = VERSION
            guardar_prefs(d)
            if vista:
                toasts.avisar(f"Versión nueva instalada: NovaBot {VERSION} (antes {vista}).", "ok")

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
        self._guardar_geometria()
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
