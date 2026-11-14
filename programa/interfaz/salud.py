"""Pestana Salud: cuanto usa el bot del equipo, como va el detector (procesador
o grafica) y el lector de texto, y la conexion ADB de cada cuenta.

El modelo del detector no se carga en la ventana: cada cuenta publica su
estado en detector_estado.json (nucleo: %LOCALAPPDATA%\\NovaBot) y aqui solo
se lee."""
from __future__ import annotations

import importlib.util
import os
import threading
import time

import tkinter as tk

from nucleo import config
from nucleo import salud as equipo
from nucleo.rutas import carpeta_datos
from interfaz.tema import (AMBAR, BORDE, ESP_L, ESP_M, ESP_S, ESP_XS, FONDO, NIVEL_COLOR, NIVEL_ICONO, PANEL,
                           PANEL2, ROJO, SUAVE, TAM_M, TAM_S, TAM_XL, TAM_XS, TEAL, TEXTO, VERDE, fuente, titular)
from interfaz.widgets import Ayuda, _plano


def ruta_detector() -> str:
    return os.path.join(carpeta_datos(), "detector_estado.json")


def leer_detector(segundos: int = 90) -> dict:
    """Lo ultimo que publico una cuenta sobre el detector ({} si no hay)."""
    try:
        d = config.leer_config(ruta_detector())
        if not isinstance(d, dict) or time.time() - float(d.get("t", 0)) > segundos:
            return {}
        return d
    except Exception:                                        # noqa: BLE001
        return {}


def lector_listo() -> bool:
    """Si RapidOCR esta instalado (no lo carga)."""
    try:
        return importlib.util.find_spec("rapidocr_onnxruntime") is not None
    except Exception:                                        # noqa: BLE001
        return False


class Salud(tk.Frame):
    """Tarjetas de estado del equipo y de la conexion de cada cuenta."""

    def __init__(self, master, tema, app):
        super().__init__(master, bg=tema["FONDO"], padx=ESP_L, pady=ESP_S)
        self.t = tema
        self.app = app
        self._filas_adb: dict[str, tuple[tk.Label, tk.Label]] = {}
        self._cuentas_vistas: list[str] = []
        self._cada = 0

        cab = tk.Frame(self, bg=FONDO)
        cab.pack(fill="x", pady=(0, ESP_S))
        tk.Label(cab, text="♥  SALUD DEL EQUIPO", bg=FONDO, fg=TEAL,
                 font=titular(TAM_M)).pack(side="left")
        b = _plano(cab, "↻ Actualizar", self.actualizar, pady=ESP_XS)
        b.config(font=fuente(TAM_S))
        b.pack(side="right")
        Ayuda(b, "Vuelve a mirar CPU, memoria, detector y conexiones.")

        #  tarjetas de cifras
        rejilla = tk.Frame(self, bg=FONDO)
        rejilla.pack(fill="x")
        self.cifras = {}
        for i, (clave, titulo) in enumerate((("cpu", "CPU del bot"), ("mem", "Memoria del bot"),
                                             ("det", "Detector"), ("ocr", "Lector de texto"))):
            caja = tk.Frame(rejilla, bg=PANEL, padx=ESP_M, pady=ESP_S, highlightthickness=1,
                            highlightbackground=BORDE)
            caja.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else ESP_S, 0))
            rejilla.grid_columnconfigure(i, weight=1, uniform="salud")
            v = tk.Label(caja, text="—", bg=PANEL, fg=TEXTO, font=titular(TAM_XL), anchor="w")
            v.pack(anchor="w")
            tk.Label(caja, text=titulo, bg=PANEL, fg=SUAVE, font=fuente(TAM_XS)).pack(anchor="w")
            s = tk.Label(caja, text="", bg=PANEL, fg=SUAVE, font=fuente(TAM_XS), anchor="w",
                         justify="left", wraplength=230)
            s.pack(anchor="w")
            self.cifras[clave] = (v, s)

        #  detector: procesador o grafica, con su interruptor
        det = tk.Frame(self, bg=PANEL, padx=ESP_L, pady=ESP_M, highlightthickness=1,
                       highlightbackground=BORDE)
        det.pack(fill="x", pady=(ESP_M, 0))
        tk.Label(det, text="Detector de objetos", bg=PANEL, fg=TEXTO,
                 font=titular(TAM_S)).pack(anchor="w")
        self.lbl_det = tk.Label(det, text="", bg=PANEL, fg=SUAVE, font=fuente(TAM_S), anchor="w",
                                justify="left", wraplength=760)
        self.lbl_det.pack(anchor="w", pady=(ESP_XS, ESP_S))
        try:
            from vision import gpu_compartida
            activo = gpu_compartida.usar_gpu()
        except Exception:                                    # noqa: BLE001
            activo = True
        self.var_gpu = tk.BooleanVar(value=activo)
        self.chk_gpu = tk.Checkbutton(det, text="Usar la gráfica cuando compense", variable=self.var_gpu,
                                      command=self._cambiar_gpu, bg=PANEL, activebackground=PANEL,
                                      fg=TEXTO, activeforeground=TEXTO, selectcolor=PANEL2, bd=0,
                                      highlightthickness=0, font=fuente(TAM_S), anchor="w")
        self.chk_gpu.pack(anchor="w")
        Ayuda(self.chk_gpu, "Apagado, el detector va siempre con el procesador. El cambio es inmediato "
                            "y vale para todas las cuentas.")

        #  conexion de cada cuenta
        self.caja_adb = tk.Frame(self, bg=PANEL, padx=ESP_L, pady=ESP_M, highlightthickness=1,
                                 highlightbackground=BORDE)
        self.caja_adb.pack(fill="x", pady=(ESP_M, 0))
        tk.Label(self.caja_adb, text="Conexión ADB de cada cuenta", bg=PANEL, fg=TEXTO,
                 font=titular(TAM_S)).pack(anchor="w")
        self.lista_adb = tk.Frame(self.caja_adb, bg=PANEL)
        self.lista_adb.pack(fill="x", pady=(ESP_XS, 0))
        self.actualizar()

    # ------------------------------------------------------------ acciones --
    def _cambiar_gpu(self):
        valor = bool(self.var_gpu.get())
        try:
            from vision import percepcion
            percepcion.poner_usar_gpu(valor)
        except Exception as e:                               # noqa: BLE001
            self.app.escribir("", f"ERROR: no puedo cambiar el uso de la gráfica: {e}")
            return
        self.app.escribir("", "Gráfica " + ("activada" if valor else "desactivada")
                          + " para el detector (vale para todas las cuentas).")
        self.actualizar()

    def reconectar(self, puerto):
        """«adb connect» a una cuenta y volver a mirar quien esta conectada."""
        dev = f"127.0.0.1:{puerto}"
        adb = getattr(self.app, "adb", "")
        if not adb:
            self.app.escribir("", "No encuentro adb: comprueba BlueStacks en Ajustes.")
            return
        threading.Thread(target=self._reconectar, args=(dev, adb), daemon=True).start()

    def _reconectar(self, dev, adb):
        import subprocess
        import sys
        fl = 0x08000000 if sys.platform == "win32" else 0
        try:
            subprocess.run([adb, "connect", dev], capture_output=True, text=True, timeout=12,
                           creationflags=fl)
            out = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=12,
                                 creationflags=fl).stdout
            conectadas = {ln.split()[0] for ln in out.splitlines()[1:] if "\tdevice" in ln}
            self.app.conectadas = conectadas
            self.app.cola.put(("", f"ADB {dev}: "
                                   + ("conectada." if dev in conectadas else "sigue sin conectar.")))
        except Exception as e:                               # noqa: BLE001
            self.app.cola.put((dev, f"ERROR: no puedo reconectar con ADB: {e}"))

    # ---------------------------------------------------------- actualizar --
    def actualizar(self, forzar=False):
        """Lee CPU/memoria, el estado que publican las cuentas y el ADB."""
        u = equipo.uso()
        v, s = self.cifras["cpu"]
        v.config(text="—" if u["cpu_pct"] is None else f"{u['cpu_pct']:.0f} %")
        s.config(text=f"{u['procesos']} proceso{'s' if u['procesos'] != 1 else ''} del bot"
                      + (f" · equipo al {u['equipo_pct']:.0f} % de memoria"
                         if u["equipo_pct"] is not None else ""))
        v, s = self.cifras["mem"]
        v.config(text="—" if u["memoria_mb"] is None else f"{u['memoria_mb']:.0f} MB")
        s.config(text="ventana y cuentas en marcha")
        #  detector: lo que publico la ultima cuenta que lo uso
        d = leer_detector()
        v, s = self.cifras["det"]
        if d:
            gpu = d.get("dispositivo") == "GPU"
            ms = d.get("ms_por_imagen")
            v.config(text=("GPU" if gpu else "CPU") + (f" · {ms:.0f} ms" if ms else ""),
                     fg=TEAL if gpu else TEXTO)
            s.config(text=d.get("motivo", "")[:120] or ("grafica" if gpu else "procesador"))
            self.lbl_det.config(text=(f"{'Gráfica' if gpu else 'Procesador'}"
                                      + (f" · {ms:.0f} ms por imagen" if ms else "")
                                      + (f" · {d['motivo']}" if d.get("motivo") else "")
                                      + f" · publicado hace {int(time.time() - float(d.get('t', 0)))} s"),
                                fg=TEXTO if gpu else SUAVE)
        else:
            v.config(text="—", fg=SUAVE)
            s.config(text="sin datos: empieza una cuenta")
            self.lbl_det.config(text="Aún no hay datos del detector (los publica cada cuenta "
                                     "cuando está en marcha).", fg=SUAVE)
        if bool(d.get("usar_gpu", self.var_gpu.get())) != self.var_gpu.get():
            self.var_gpu.set(bool(d.get("usar_gpu")))
        #  lector de texto
        v, s = self.cifras["ocr"]
        listo = lector_listo()
        v.config(text="Listo" if listo else "Falta", fg=VERDE if listo else AMBAR)
        s.config(text="RapidOCR instalado" if listo else "abre BOT.bat para instalarlo")
        #  ADB de cada cuenta
        self._pintar_adb()

    def _pintar_adb(self):
        filas = list(getattr(self.app, "filas", []))
        puertos = [str(f.puerto) for f in filas]
        if puertos != self._cuentas_vistas:
            for w in list(self.lista_adb.winfo_children()):
                w.destroy()
            self._filas_adb = {}
            self._cuentas_vistas = puertos
            for f in filas:
                dev = f"127.0.0.1:{f.puerto}"
                fila = tk.Frame(self.lista_adb, bg=PANEL)
                fila.pack(fill="x", pady=ESP_XS)
                tk.Label(fila, text="●", bg=PANEL, fg=f.color, font=fuente(TAM_M)).pack(side="left")
                tk.Label(fila, text=self._nombre(f), bg=PANEL, fg=TEXTO, font=fuente(TAM_S),
                         width=22, anchor="w").pack(side="left")
                estado = tk.Label(fila, text="…", bg=PANEL, fg=SUAVE, font=fuente(TAM_S), anchor="w")
                estado.pack(side="left")
                b = _plano(fila, "↻ Reconectar", lambda p=f.puerto: self.reconectar(p), pady=ESP_XS)
                b.config(font=fuente(TAM_XS + 1))
                b.pack(side="right")
                self._filas_adb[dev] = (estado, b)
        for f in filas:
            dev = f"127.0.0.1:{f.puerto}"
            par = self._filas_adb.get(dev)
            if not par:
                continue
            conectada = dev in getattr(self.app, "conectadas", set())
            sondeado = getattr(self.app, "_sondeado", False)
            estado = (f.en_marcha() and (f.estado or {}).get("estado") == "sin conexión")
            if conectada and not estado:
                par[0].config(text=f"{NIVEL_ICONO['ok']} Conectada", fg=NIVEL_COLOR["ok"])
            elif not sondeado:
                par[0].config(text="○ Sin comprobar todavía", fg=SUAVE)
            else:
                par[0].config(text=f"{NIVEL_ICONO['error']} Sin conexión", fg=ROJO)

    def _nombre(self, f) -> str:
        try:
            return self.app._nombres().get(str(f.puerto), f.nombre)
        except Exception:                                    # noqa: BLE001
            return f.nombre
