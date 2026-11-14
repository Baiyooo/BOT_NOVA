"""Tarjeta de una instancia en la ventana."""
from __future__ import annotations

import time
import tkinter as tk

from interfaz.catalogo import AYUDA_TAREA, NOMBRE_TAREA, SIN_LIMITE, TAREA_FILA, TAREA_GRUPOS, UNIDAD
from interfaz.preferencias import guardar_prefs, leer_prefs
from interfaz.tema import (AMBAR, BLANCO, BORDE, COLOR_ESTADO, LETRA, PANEL, PANEL2, ROJO, SUAVE, TEAL, TEXTO, TINTA, texto_estado, titular)
from interfaz.widgets import Ayuda, Barra, _plano


class FilaInstancia(tk.Frame):
    """Tarjeta de una instancia: su tarea, su limite y su boton de empezar."""

    def __init__(self, master, nombre: str, puerto: int, color: str):
        super().__init__(master, bg=PANEL, padx=14, pady=12,
                         highlightthickness=1, highlightbackground=BORDE)
        self.puerto, self.nombre, self.color = puerto, nombre, color
        self.motor = None
        self.activa = tk.BooleanVar(value=True)
        self.parada = None                         # multiprocessing.Event al empezar
        self.hilo = None                           # el proceso de esta instancia
        self.estado: dict | None = None
        self.al_pulsar = None                      # lo pone la ventana
        self.grid_columnconfigure(1, weight=1)

        # columna 0: casilla "incluir" y punto de estado
        izq = tk.Frame(self, bg=PANEL)
        izq.grid(row=0, column=0, rowspan=4, sticky="n", padx=(0, 10))
        ck = tk.Checkbutton(izq, variable=self.activa, bg=PANEL, activebackground=PANEL,
                            fg=TEXTO, activeforeground=TEXTO,
                            selectcolor=PANEL2, bd=0, highlightthickness=0)
        ck.pack()
        Ayuda(ck, "Incluir en «Empezar todas», «Parar todas» y «Captura».")

        # fila 0: nombre, puerto y estado
        cab = tk.Frame(self, bg=PANEL)
        cab.grid(row=0, column=1, sticky="ew")
        self.punto = tk.Label(cab, text="●", bg=PANEL, fg=SUAVE, font=("Segoe UI", 10))
        self.punto.pack(side="left")
        mostrado = leer_prefs().get("nombres", {}).get(str(puerto), nombre)
        self.lbl_nombre = tk.Label(cab, text=mostrado, bg=PANEL, fg=TEXTO, font=titular(12))
        self.lbl_nombre.pack(side="left", padx=(4, 0))
        self.al_renombrar = self.al_registro = self.al_captura = self.al_ajustes = None   # los pone la ventana

        sub = tk.Frame(self, bg=PANEL)
        sub.grid(row=1, column=1, sticky="ew", pady=(1, 0))
        tk.Label(sub, text=f"Puerto {puerto}", bg=PANEL, fg=SUAVE,
                 font=(LETRA, 8)).pack(side="left", padx=(18, 4))
        for texto, attr, ayuda in (("✎ Nombre", "al_renombrar", "Cambia el nombre de esta cuenta."),
                                   ("Ajustes", "al_ajustes", "Ajustes propios de esta cuenta."),
                                   ("Registro", "al_registro", "Registro individual de esta cuenta."),
                                   ("Captura", "al_captura", "Captura de pantalla de esta cuenta.")):
            b = tk.Button(sub, text=texto, bd=0, relief="flat", cursor="hand2", bg=PANEL,
                          fg=TEAL, activebackground=PANEL, activeforeground=TEAL,
                          font=("Segoe UI", 8), padx=4, pady=0,
                          command=lambda a=attr: getattr(self, a) and getattr(self, a)(self))
            b.pack(side="left", padx=(4, 0))
            Ayuda(b, ayuda)
        self.lbl_estado = tk.Label(cab, text="En espera", bg=PANEL, fg=SUAVE,
                                   font=("Segoe UI", 9))
        self.lbl_estado.pack(side="right")

        # fila 1: tarea y limite
        ctl = tk.Frame(self, bg=PANEL)
        ctl.grid(row=2, column=1, sticky="ew", pady=(8, 0))
        prefs = leer_prefs()
        self.tarea_propia = tk.StringVar(
            value=NOMBRE_TAREA.get(prefs.get("tareas", {}).get(str(puerto)),
                                   "Rutina automática"))
        self.veces = tk.StringVar(value=str(prefs.get("veces", {}).get(str(puerto), 0)))
        self.tarea_propia.trace_add("write", lambda *a: self._cambio())
        self.veces.trace_add("write", lambda *a: self._guardar_tarea())
        self.om = tk.Menubutton(ctl, textvariable=self.tarea_propia, bg=PANEL2, fg=TEXTO,
                                activebackground=BORDE, activeforeground=TEXTO, bd=0,
                                highlightthickness=0, font=("Segoe UI", 10), width=26,
                                anchor="w", padx=10, pady=4, indicatoron=True, relief="flat",
                                cursor="hand2")
        estilo = dict(bg=PANEL2, fg=TEXTO, activebackground=AMBAR,
                      activeforeground=TINTA, font=(LETRA, 10), bd=0)
        menu = tk.Menu(self.om, tearoff=0, **estilo)
        for grupo, items in TAREA_GRUPOS:
            sub = tk.Menu(menu, tearoff=0, **estilo)
            for nombre in items:
                sub.add_command(label=nombre, command=lambda n=nombre: self.tarea_propia.set(n))
            menu.add_cascade(label=grupo, menu=sub)
        self.om["menu"] = menu
        self.om.pack(side="left")
        self.ayuda_tarea = Ayuda(self.om, "")
        self.lbl_lim = tk.Label(ctl, text="Límite", bg=PANEL, fg=SUAVE, font=("Segoe UI", 9))
        self.lbl_lim.pack(side="left", padx=(16, 6))
        self.spin = tk.Spinbox(ctl, from_=0, to=999, width=4, textvariable=self.veces,
                               bg=PANEL2, fg=TEXTO, buttonbackground=PANEL2, bd=0,
                               insertbackground=TEXTO, justify="center",
                               disabledbackground=PANEL, disabledforeground=BORDE,
                               font=("Consolas", 10))
        self.spin.pack(side="left", ipady=3)
        self.lbl_unidad = tk.Label(ctl, text="", bg=PANEL, fg=SUAVE, font=("Segoe UI", 9))
        self.lbl_unidad.pack(side="left", padx=(6, 0))
        Ayuda(self.spin, "Cuántas veces hacerlo. 0 = sin límite.")

        # columna 2: empezar / parar
        self.b_fila = _plano(self, "▶  Empezar", lambda: self.al_pulsar and self.al_pulsar(self),
                             bg=AMBAR, fg=TINTA, negrita=True, width=11, pady=8)
        self.b_fila.grid(row=0, column=2, rowspan=3, sticky="e", padx=(12, 0))

        # fila 2: progreso y resumen
        pie = tk.Frame(self, bg=PANEL)
        pie.grid(row=3, column=1, columnspan=2, sticky="ew", pady=(10, 0))
        self.barra = Barra(pie, ancho=220, alto=6)
        self.barra.pack(side="left")
        self.lbl_det = tk.Label(pie, text="", bg=PANEL, fg=SUAVE, font=("Segoe UI", 9))
        self.lbl_det.pack(side="left", padx=(12, 0))
        self.lbl_plan = tk.Label(self, text="", bg=PANEL, fg=SUAVE, font=("Segoe UI", 9),
                                 anchor="w", justify="left", wraplength=560)
        self.lbl_plan.grid(row=4, column=1, columnspan=2, sticky="ew", pady=(6, 0))
        self.lbl_plan.grid_remove()                # se ve solo cuando tiene texto
        self.lbl_hoy = tk.Label(self, text="", bg=PANEL, fg=SUAVE, font=("Segoe UI", 8),
                                anchor="w", justify="left")
        self.lbl_hoy.grid(row=5, column=1, columnspan=2, sticky="ew", pady=(4, 0))
        self._cambio(guardar=False)

    # --- tarea y limite -----------------------------------------------------
    def _cambio(self, guardar=True):
        clave = self.tarea()
        unidad = UNIDAD.get(clave)
        if unidad:
            self.spin.config(state="normal")
            self.lbl_lim.config(fg=SUAVE)
            self.lbl_unidad.config(text=f"{unidad} · 0 = sin límite")
        else:
            self.spin.config(state="disabled")
            self.lbl_lim.config(fg=BORDE)
            self.lbl_unidad.config(text=SIN_LIMITE.get(clave, ""))
        self.ayuda_tarea.texto = AYUDA_TAREA.get(clave, "")
        if guardar:
            self._guardar_tarea()

    def _guardar_tarea(self):
        d = leer_prefs()
        d.setdefault("tareas", {})[str(self.puerto)] = TAREA_FILA[self.tarea_propia.get()]
        try:
            d.setdefault("veces", {})[str(self.puerto)] = max(0, int(self.veces.get()))
        except ValueError:
            pass
        guardar_prefs(d)

    def n_veces(self) -> int:
        if not UNIDAD.get(self.tarea()):
            return 0
        try:
            return max(0, int(self.veces.get()))
        except ValueError:
            return 0

    def en_marcha(self) -> bool:
        return self.hilo is not None and self.hilo.is_alive()

    def tarea(self, general: str = "") -> str:
        return TAREA_FILA.get(self.tarea_propia.get()) or general

    def marcha(self, vivo: bool):
        """Aspecto de la tarjeta segun este en marcha o no."""
        if vivo:
            self.b_fila.config(text="■  Parar")
            self.b_fila.color(ROJO, BLANCO)
            self.om.config(state="disabled")
            self.spin.config(state="disabled")
            self.config(highlightbackground=self.color)
        else:
            self.b_fila.config(text="▶  Empezar")
            self.b_fila.color(AMBAR, TINTA)
            self.om.config(state="normal")
            self._cambio(guardar=False)
            self.config(highlightbackground=BORDE)

    # --- estado en vivo -----------------------------------------------------
    @staticmethod
    def _quedan(cuando: float) -> str:
        """Tiempo que falta hasta `cuando` (epoch): 'en 45 s', 'en 12 min', 'en 1 h 05'."""
        s = int(cuando - time.time())
        if s <= 0:
            return "ahora"
        if s < 90:
            return f"en {s} s"
        if s < 3600:
            return f"en {round(s / 60)} min"
        return f"en {s // 3600} h {s % 3600 // 60:02d}"

    def _rutina_txt(self, st: dict) -> str:
        """'Ahora: X  ·  Luego: Y en 12 min' con la cuenta atras al segundo."""
        if st.get("sig_c") and st.get("sig_n"):
            txt = st.get("rutina_texto", "").split("  ·  Luego")[0]
            return f"{txt}  ·  Luego: {st['sig_n']} {self._quedan(st['sig_c'])}"
        return st.get("rutina_texto", "")

    def pintar(self, st: dict):
        estado = st.get("estado", "en espera")
        color = COLOR_ESTADO.get(estado, TEAL if self.en_marcha() else SUAVE)
        self.lbl_estado.config(text=texto_estado(estado), fg=color)
        self.punto.config(fg=color if self.en_marcha() else SUAVE)
        clave = self.tarea()
        if st.get("plan"):                      # rutina: que hace y que tiene en cola
            total = st.get("rutina_total", 0)
            self.barra.set((st.get("rutina_hecho", 0) / total) if total else 0, color)
            self.lbl_det.config(text=f"Lo diario: {st.get('rutina_hecho', 0)}/{total}  ·  hoy "
                                     f"{st.get('normales', 0)} normales y "
                                     f"{st.get('sigilo', 0)} de sigilo")
            ahora = [p for p in st["plan"] if p.get("e") == "ahora"]
            cola = [p for p in st["plan"] if p.get("e") == "pendiente"]
            lineas = []
            if ahora:
                lineas.append(f"▶ {ahora[0]['n']}: {ahora[0].get('m', '')}")
            elif st.get("sig_c"):
                lineas.append(f"○ Esperando · siguiente {self._quedan(st['sig_c'])}")
            if cola:
                lineas.append("Luego: " + "  ·  ".join(p["n"] for p in cola[:5]))
            self._plan("\n".join(lineas))
            return
        self._plan("")
        if "jugadas" in st:                     # cosmomante
            fases = {"abriendo Cosmomante": 0.1, "leyendo el mapa": 0.25, "tiradas gratis": 0.7,
                     "dados normales": 0.85, "ascendiendo": 0.92,
                     "reclamando metas de dados": 0.96, "terminado": 1.0}
            frac = fases.get(estado, 0.4 if estado.startswith("jugada") else 0.05)
            self.barra.set(frac, color)
            nivel = st.get("nivel")
            nivel_txt = f"nivel {nivel}" if nivel else "nivel sin leer"
            j, a, r = st.get("jugadas", 0), st.get("ascensos", 0), st.get("recogidas", 0)
            self.lbl_det.config(text=f"{j} {'jugada' if j == 1 else 'jugadas'}  ·  {nivel_txt}  ·  "
                                     f"{a} {'ascenso' if a == 1 else 'ascensos'}  ·  "
                                     f"{r} {'meta recogida' if r == 1 else 'metas recogidas'}")
            return
        if "recogidas" in st:                   # recompensas
            paso, pasos = st.get("paso", 0), st.get("pasos", 3) or 3
            self.barra.set(paso / pasos, color)
            r = st.get("recogidas", 0)
            self.lbl_det.config(text=f"Paso {paso} de {pasos}  ·  {r} "
                                     f"{'recompensa recogida' if r == 1 else 'recompensas recogidas'}")
            return
        if "ciclo" in st:                       # piratas
            hecho, total = st.get("ciclo", 0), st.get("ciclos", 0)
            self.barra.set(hecho / (total or max(hecho, 1)) if total else (1 if hecho else 0), color)
            if clave == "mixto":
                txt = (f"{st.get('normales', hecho)} normales  ·  "
                       f"{st.get('sigilo', st.get('atacados', 0))} de sigilo")
            elif clave == "normales":
                txt = f"{hecho} ataque{'s' if hecho != 1 else ''}"
                if total:
                    txt += f" de {total}"
            else:
                txt = (f"Búsqueda {hecho}{f' de {total}' if total else ''}  ·  "
                       f"{st.get('encontrados', 0)} vistos  ·  {st.get('atacados', 0)} atacados")
            self.lbl_det.config(text=txt)
            return
        if "mov" in st or "partida" in st:      # roaming
            mov, movs = st.get("mov", 0), st.get("movs", 30) or 30
            self.barra.set(mov / movs, color)
            part, parts = st.get("partida", 0), st.get("partidas", 0)
            self.lbl_det.config(text=f"Partida {part}{f' de {parts}' if parts else ''}"
                                     f"  ·  movimiento {mov}/{movs}")
            return
        self.lbl_det.config(text="")

    def reset(self):
        self.motor = None
        self.lbl_estado.config(text="En espera", fg=SUAVE)
        self.punto.config(fg=SUAVE)
        self.barra.set(0)
        self.lbl_det.config(text="")
        self._plan("")

    def reset_plan(self):
        self._plan("")

    def _plan(self, texto: str):
        self.lbl_plan.config(text=texto)
        if texto:
            self.lbl_plan.grid()
        else:
            self.lbl_plan.grid_remove()
