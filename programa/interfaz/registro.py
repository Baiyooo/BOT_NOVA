"""Registro de mensajes de la ventana."""
from __future__ import annotations

import time
import tkinter as tk

from interfaz import panel
from nucleo import rutas
from interfaz.preferencias import guardar_prefs, leer_prefs
from interfaz.tema import BORDE, FONDO, PANEL, PANEL2, ROJO, SUAVE, TEAL, TEXTO, titular
from interfaz.widgets import Ayuda


class _Registro:
    """Registro de mensajes de la ventana."""

    def _registro(self):
        c = tk.Frame(self.zona, bg=FONDO, padx=20)
        c.pack(fill="both", expand=True, pady=(12, 16))
        cab = tk.Frame(c, bg=FONDO)
        cab.pack(fill="x", pady=(0, 6))
        tk.Label(cab, text="◆  REGISTRO", bg=FONDO, fg=TEAL,
                 font=titular(10)).pack(side="left")
        self.tam_letra = int(leer_prefs().get("letra_registro", 13))
        for texto, cmd, ayuda in (("A+", lambda: self._letra(+1), "Letra más grande."),
                                  ("A−", lambda: self._letra(-1), "Letra más pequeña."),
                                  ("Limpiar", self._limpiar, "Borra el registro de la ventana."),
                                  ("Abrir diagnóstico", self._abrir_diag,
                                   "Carpeta con el registro y las capturas de cada cuenta.")):
            b_ = tk.Button(cab, text=texto, command=cmd, bg=FONDO, fg=TEAL,
                           activebackground=FONDO, activeforeground=TEAL, bd=0,
                           relief="flat", cursor="hand2", padx=0, pady=0,
                           font=("Segoe UI", 10, "bold") if texto.startswith("A") else ("Segoe UI", 9))
            b_.pack(side="right", padx=(12, 0))
            Ayuda(b_, ayuda)
        marco = tk.Frame(c, bg=BORDE, bd=0)
        marco.pack(fill="both", expand=True)
        self.txt = tk.Text(marco, bg=PANEL, fg=TEXTO, bd=0, padx=10, pady=8,
                           width=80, height=14, font=("Consolas", self.tam_letra), wrap="word",
                           state="disabled", insertbackground=TEXTO, spacing1=1)
        sb = tk.Scrollbar(marco, command=self.txt.yview, bg=PANEL2, bd=0,
                          troughcolor=PANEL, width=10)
        self.txt.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        self.txt.tag_config("hora", foreground=SUAVE)
        self.txt.tag_config("inst", foreground=TEAL)
        self.txt.tag_config("error", foreground=ROJO)
        for dev, color in self.colores.items():
            self.txt_tag(dev, color)
        self.escribir("", "Elige una tarea para cada cuenta y pulsa ▶ Empezar.")

    def _letra(self, paso):
        self.tam_letra = max(9, min(20, self.tam_letra + paso))
        self.txt.config(font=("Consolas", self.tam_letra))
        d = leer_prefs()
        d["letra_registro"] = self.tam_letra
        guardar_prefs(d)

    def txt_tag(self, dev, color):
        self.txt.tag_config("i" + dev, foreground=color)

    def _limpiar(self):
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.config(state="disabled")

    def _abrir_diag(self):
        import os
        ruta = rutas.carpeta_diag()
        os.makedirs(ruta, exist_ok=True)
        try:
            os.startfile(ruta)                      # noqa: S606 (solo Windows)
        except Exception:                           # noqa: BLE001
            self.escribir("", f"Diagnóstico en: {ruta}")

    # ------------------------------------------------------------- acciones --
    def escribir(self, inst: str, msg: str):
        if not hasattr(self, "_log_panel"):
            import collections
            self._log_panel = collections.deque(maxlen=200)
        nombre_i = next((f.nombre.split(" - ")[0] for f in getattr(self, "filas", [])
                         if f"127.0.0.1:{f.puerto}" == inst), inst) if inst else ""
        self._log_panel.append([time.strftime("%H:%M:%S"), nombre_i, msg])
        self.txt.config(state="normal")
        self.txt.insert("end", time.strftime("%H:%M:%S  "), "hora")
        if inst:
            nombre = next((f.nombre.split(" - ")[0] for f in getattr(self, "filas", [])
                           if f"127.0.0.1:{f.puerto}" == inst), inst)
            self.txt.insert("end", f"{nombre[:14]:<14} ", "i" + inst if inst in self.colores else "inst")
        self.txt.insert("end", msg + "\n", "error" if msg.startswith("ERROR") else ())
        # que no crezca sin fin
        if int(self.txt.index("end-1c").split(".")[0]) > 3000:
            self.txt.delete("1.0", "500.0")
        self.txt.see("end")
        self.txt.config(state="disabled")

    def _ver_registro(self, f):
        import os
        nombre = f"127.0.0.1_{f.puerto}"
        panel.ventana_registro(self, self.tema, self._nombres().get(str(f.puerto), f.nombre),
                               os.path.join(rutas.carpeta_diag(), nombre, "registro.txt"))
