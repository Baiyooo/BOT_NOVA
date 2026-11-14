"""Registro de mensajes de la ventana (pestana Registro): filtros por cuenta y
por tipo, busqueda de texto, colores por tipo, copiar y abrir las capturas."""
from __future__ import annotations

import collections
import time
import tkinter as tk

from interfaz import panel
from nucleo import rutas
from interfaz.preferencias import guardar_prefs, leer_prefs
from interfaz.tema import (AMBAR, BORDE, ESP_L, ESP_M, ESP_S, FONDO, PANEL, PANEL2, ROJO, SUAVE, TAM_M, TAM_S,
                           TEAL, TEXTO, fuente, mono, titular)
from interfaz.widgets import Ayuda

#  tipos de mensaje del registro (color y nombre, nunca solo color)
TIPOS = (("todo", "Todo"), ("info", "Info"), ("aviso", "Aviso"), ("error", "Error"))
COLOR_TIPO = {"info": TEXTO, "aviso": AMBAR, "error": ROJO}


def nivel_msg(msg: str) -> str:
    """Tipo de un mensaje segun su texto (info, aviso o error)."""
    m = msg.lower()
    if msg.startswith("ERROR") or "✖" in msg or "error" in m or "fallo" in m or "falla" in m:
        return "error"
    if ("⚠" in msg or "aviso" in m or "sin conexión" in m or "no puedo" in m
            or "no veo" in m or "no he encontrado" in m):
        return "aviso"
    return "info"


class _Registro:
    """Registro de mensajes de la ventana."""

    def _registro(self, pagina=None):
        pagina = pagina if pagina is not None else self.zona
        c = tk.Frame(pagina, bg=FONDO, padx=ESP_L, pady=ESP_M)
        c.pack(fill="both", expand=True)
        self.caja_registro = c
        self._lineas = collections.deque(maxlen=3000)       # (hora, inst, nombre, msg, nivel)
        cab = tk.Frame(c, bg=FONDO)
        cab.pack(fill="x", pady=(0, ESP_M))
        tk.Label(cab, text="◆  REGISTRO", bg=FONDO, fg=TEAL,
                 font=titular(TAM_M)).pack(side="left")
        self.tam_letra = int(leer_prefs().get("letra_registro", 13))
        for texto, cmd, ayuda in (("A+", lambda: self._letra(+1), "Letra más grande."),
                                  ("A−", lambda: self._letra(-1), "Letra más pequeña."),
                                  ("Limpiar", self._limpiar, "Borra el registro de la ventana."),
                                  ("⧉ Copiar", self._copiar, "Copia al portapapeles lo que se ve."),
                                  ("▣ Capturas", self._abrir_capturas,
                                   "Carpeta con las capturas guardadas de cada cuenta."),
                                  ("Abrir diagnóstico", self._abrir_diag,
                                   "Carpeta con el registro y las capturas de cada cuenta.")):
            b_ = tk.Button(cab, text=texto, command=cmd, bg=FONDO, fg=TEAL,
                           activebackground=FONDO, activeforeground=TEAL, bd=0,
                           relief="flat", cursor="hand2", padx=0, pady=0,
                           font=fuente(TAM_M, True) if texto.startswith("A") else fuente(TAM_S))
            b_.pack(side="right", padx=(ESP_L, 0))
            Ayuda(b_, ayuda)

        #  barra de filtros: cuenta, tipo y texto a buscar
        filt = tk.Frame(c, bg=FONDO)
        filt.pack(fill="x", pady=(0, ESP_M))
        tk.Label(filt, text="Cuenta", bg=FONDO, fg=SUAVE, font=fuente(TAM_S)).pack(side="left")
        self.f_cuenta = tk.StringVar(value=str(leer_prefs().get("filtro_registro_cuenta") or "Todas"))
        self.om_cuenta = tk.OptionMenu(filt, self.f_cuenta, "Todas")
        self._estilo_menu(self.om_cuenta)
        self.om_cuenta.config(bg=PANEL2, fg=TEXTO, activebackground=BORDE, activeforeground=TEXTO,
                              bd=0, highlightthickness=0, relief="flat", cursor="hand2",
                              font=fuente(TAM_S), padx=ESP_S, pady=1)
        self.om_cuenta.pack(side="left", padx=(ESP_S, ESP_L))
        Ayuda(self.om_cuenta, "Enseñar solo los mensajes de una cuenta (o de todas).")
        tk.Label(filt, text="Tipo", bg=FONDO, fg=SUAVE, font=fuente(TAM_S)).pack(side="left")
        self.f_tipo = tk.StringVar(value=str(leer_prefs().get("filtro_registro_tipo") or "Todo"))
        self.om_tipo = tk.OptionMenu(filt, self.f_tipo, *(t for _, t in TIPOS))
        self._estilo_menu(self.om_tipo)
        self.om_tipo.config(bg=PANEL2, fg=TEXTO, activebackground=BORDE, activeforeground=TEXTO,
                            bd=0, highlightthickness=0, relief="flat", cursor="hand2",
                            font=fuente(TAM_S), padx=ESP_S, pady=1)
        self.om_tipo.pack(side="left", padx=(ESP_S, ESP_L))
        Ayuda(self.om_tipo, "Enseñar solo avisos, solo errores… (cada línea con su color).")
        tk.Label(filt, text="Buscar", bg=FONDO, fg=SUAVE, font=fuente(TAM_S)).pack(side="left")
        self.f_buscar = tk.StringVar(value=str(leer_prefs().get("filtro_registro_texto") or ""))
        self.e_buscar = tk.Entry(filt, textvariable=self.f_buscar, bg=PANEL2, fg=TEXTO, bd=0,
                                 insertbackground=TEXTO, highlightthickness=0, font=fuente(TAM_S),
                                 width=24)
        self.e_buscar.pack(side="left", padx=(ESP_S, 0), ipady=ESP_S)
        Ayuda(self.e_buscar, "Enseñar solo las líneas que contengan este texto.")
        self._n_filtro = tk.Label(filt, text="", bg=FONDO, fg=SUAVE, font=fuente(TAM_S))
        self._n_filtro.pack(side="right")
        for v in (self.f_cuenta, self.f_tipo, self.f_buscar):
            v.trace_add("write", lambda *a: self._repintar(guardar=True))
        self._refrescar_filtro_cuentas()
        marco = tk.Frame(c, bg=BORDE, bd=0)
        marco.pack(fill="both", expand=True)
        self.txt = tk.Text(marco, bg=PANEL, fg=TEXTO, bd=0, padx=ESP_M + 2, pady=ESP_M,
                           width=80, height=14, font=mono(self.tam_letra), wrap="word",
                           state="disabled", insertbackground=TEXTO, spacing1=1)
        sb = tk.Scrollbar(marco, command=self.txt.yview, bg=PANEL2, bd=0,
                          troughcolor=PANEL, width=10)
        self.txt.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        self.txt.tag_config("hora", foreground=SUAVE)
        self.txt.tag_config("inst", foreground=TEAL)
        for tipo, color in COLOR_TIPO.items():
            self.txt.tag_config(tipo, foreground=color)
        for dev, color in self.colores.items():
            self.txt_tag(dev, color)
        self.escribir("", "Elige una tarea para cada cuenta y pulsa ▶ Empezar.")

    def _estilo_menu(self, om):
        """Colores del tema en el desplegable de un OptionMenu."""
        m = om["menu"]
        m.config(bg=PANEL2, fg=TEXTO, activebackground=AMBAR, activeforeground=TEXTO,
                 bd=0, font=fuente(TAM_S))

    def _refrescar_filtro_cuentas(self):
        """Rellena el filtro de cuenta con las cuentas que hay ahora."""
        nombres = [self._nombres().get(str(f.puerto), f.nombre) for f in getattr(self, "filas", [])]
        if getattr(self, "_cuentas_filtro", None) == nombres:
            return
        self._cuentas_filtro = nombres
        m = self.om_cuenta["menu"]
        m.delete(0, "end")
        for n in ["Todas", *nombres]:
            m.add_command(label=n, command=lambda v=n: self.f_cuenta.set(v))
        if self.f_cuenta.get() not in ["Todas", *nombres]:
            self.f_cuenta.set("Todas")

    def _pasa(self, inst: str, nombre: str, msg: str, nivel: str) -> bool:
        """Si un mensaje pasa los filtros de cuenta, tipo y texto."""
        cuenta = self.f_cuenta.get()
        if cuenta != "Todas" and nombre != cuenta:
            return False
        tipo = self.f_tipo.get()
        clave = {t: k for k, t in TIPOS}.get(tipo, "todo")
        if clave != "todo" and nivel != clave:
            return False
        texto = self.f_buscar.get().strip().lower()
        return not texto or texto in msg.lower() or texto in nombre.lower()

    def _repintar(self, guardar=False):
        """Vuelve a escribir el registro solo con lo que pasa los filtros."""
        if not hasattr(self, "txt"):
            return
        if guardar:
            d = leer_prefs()
            d["filtro_registro_cuenta"] = self.f_cuenta.get()
            d["filtro_registro_tipo"] = self.f_tipo.get()
            d["filtro_registro_texto"] = self.f_buscar.get()
            guardar_prefs(d)
        self._refrescar_filtro_cuentas()
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        n = 0
        for hora, inst, nombre, msg, nivel in list(self._lineas):
            if not self._pasa(inst, nombre, msg, nivel):
                continue
            self._insertar(hora, inst, nombre, msg, nivel, ver=False)
            n += 1
        self.txt.config(state="disabled")
        self.txt.see("end")
        self._n_filtro.config(text=f"{n} de {len(self._lineas)}")

    def _insertar(self, hora, inst, nombre, msg, nivel, ver=True):
        """Escribe una linea en el cuadro con los colores de su tipo."""
        tags = ("error" if nivel == "error" else "aviso" if nivel == "aviso" else ())
        self.txt.insert("end", hora + "  ", ("hora", *tags))
        if inst:
            self.txt.insert("end", f"{nombre[:14]:<14} ", ("i" + inst, *tags) if inst in self.colores
                            else ("inst", *tags))
        self.txt.insert("end", msg + "\n", tags)
        if ver:
            self.txt.see("end")

    def _letra(self, paso):
        self.tam_letra = max(9, min(20, self.tam_letra + paso))
        self.txt.config(font=mono(self.tam_letra))
        d = leer_prefs()
        d["letra_registro"] = self.tam_letra
        guardar_prefs(d)

    def txt_tag(self, dev, color):
        self.txt.tag_config("i" + dev, foreground=color)

    def _limpiar(self):
        self._lineas.clear()
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.config(state="disabled")
        self._n_filtro.config(text="0 de 0")

    def _copiar(self):
        """Copia al portapapeles lo que se ve en el registro."""
        texto = self.txt.get("1.0", "end-1c")
        try:
            self.clipboard_clear()
            self.clipboard_append(texto)
        except tk.TclError:
            return
        self.escribir("", f"{len(texto.splitlines())} líneas copiadas al portapapeles.")

    def _abrir_capturas(self):
        """Abre la carpeta de capturas (las de «Captura» y las de cada cuenta)."""
        import os
        ruta = os.path.join(rutas.carpeta_datos(), "capturas")
        os.makedirs(ruta, exist_ok=True)
        try:
            os.startfile(ruta)                      # noqa: S606 (solo Windows)
        except Exception:                           # noqa: BLE001
            self.escribir("", f"Capturas en: {ruta}")

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
            self._log_panel = collections.deque(maxlen=200)
        if not hasattr(self, "_lineas"):            # si aun no hay pestana Registro
            self._lineas = collections.deque(maxlen=3000)
        hora = time.strftime("%H:%M:%S")
        nombre_i = next((f.nombre.split(" - ")[0] for f in getattr(self, "filas", [])
                         if f"127.0.0.1:{f.puerto}" == inst), inst) if inst else ""
        nombre = next((self._nombres().get(str(f.puerto), f.nombre.split(" - ")[0])
                       for f in getattr(self, "filas", [])
                       if f"127.0.0.1:{f.puerto}" == inst), inst)
        nivel = nivel_msg(msg)
        self._log_panel.append([hora, nombre_i, msg])         # para panel_estado.json
        self._lineas.append((hora, inst, nombre, msg, nivel))
        if not hasattr(self, "txt"):
            contar = getattr(self, "_contar_error", None)
            if contar is not None:
                contar(inst, msg)
            return
        if self._pasa(inst, nombre, msg, nivel):
            self.txt.config(state="normal")
            self._insertar(hora, inst, nombre, msg, nivel)
            # que no crezca sin fin (ni el cuadro ni la lista de arriba)
            if int(self.txt.index("end-1c").split(".")[0]) > 3000:
                self.txt.delete("1.0", "500.0")
            self.txt.config(state="disabled")
            self._n_filtro.config(text=f"{len(self._lineas)} de {len(self._lineas)}")
        contar = getattr(self, "_contar_error", None)
        if contar is not None:
            contar(inst, msg)

    def _ver_registro(self, f):
        import os
        nombre = f"127.0.0.1_{f.puerto}"
        panel.ventana_registro(self, self.tema, self._nombres().get(str(f.puerto), f.nombre),
                               os.path.join(rutas.carpeta_diag(), nombre, "registro.txt"))
