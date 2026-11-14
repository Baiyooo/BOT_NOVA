"""Tarjeta de una instancia en la ventana (compacta: caben cuatro en 1080p)."""
from __future__ import annotations

import time
import tkinter as tk

from interfaz.catalogo import AYUDA_TAREA, NOMBRE_TAREA, SIN_LIMITE, TAREA_FILA, TAREA_GRUPOS, UNIDAD
from interfaz.preferencias import guardar_prefs, leer_prefs
from interfaz.tema import (AMBAR, BORDE, COLOR_ESTADO, ESP_L, ESP_M, ESP_S, ESP_XS, PANEL, PANEL2, SUAVE, TAM_M,
                           TAM_S, TAM_XS, TEAL, TEXTO, TINTA, fuente, icono_estado, mono, texto_estado, titular)
from interfaz.widgets import Ayuda, Barra, _plano

SENUELOS_DIA = 10          # señuelos que deja usar el juego al dia


def formato_marcha(seg: float) -> str:
    """Tiempo en marcha: '45 s', '12:05' (min:s) o '1:05:09' (h:min:s)."""
    s = max(0, int(seg))
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}" if m else f"{s} s"


class FilaInstancia(tk.Frame):
    """Tarjeta de una instancia: su tarea, su limite, lo que hace ahora y lo
    que hara despues, y sus botones de empezar / parar / ajustes."""

    def __init__(self, master, nombre: str, puerto: int, color: str):
        super().__init__(master, bg=PANEL, padx=ESP_L, pady=ESP_S + 2,
                         highlightthickness=1, highlightbackground=BORDE)
        self.puerto, self.nombre, self.color = puerto, nombre, color
        self.motor = None
        self.activa = tk.BooleanVar(value=True)
        self.parada = None                         # multiprocessing.Event al empezar
        self.hilo = None                           # el proceso de esta instancia
        self.estado: dict | None = None
        self.al_pulsar = None                      # lo pone la ventana
        self.al_renombrar = self.al_registro = self.al_captura = self.al_ajustes = None   # los pone la ventana
        self.al_parar = None
        #  acciones del menu «Más» (las pone la ventana)
        self.al_parar_acabar = self.al_pausar_min = self.al_gemas = self.al_releer = None
        self.al_probar = self.al_horario = self.al_exportar = self.al_importar = None
        self._senuelos = None                      # señuelos usados hoy (estadisticas)
        self._t0 = None                            # cuando empezo (epoch)
        self._detalle_abierto = False
        self.grid_columnconfigure(0, weight=1)

        # fila 0: casilla, color, nombre, estado, tiempo y botones
        cab = tk.Frame(self, bg=PANEL)
        cab.grid(row=0, column=0, sticky="ew")
        ck = tk.Checkbutton(cab, variable=self.activa, bg=PANEL, activebackground=PANEL,
                            fg=TEXTO, activeforeground=TEXTO, selectcolor=PANEL2, bd=0,
                            highlightthickness=0)
        ck.pack(side="left")
        Ayuda(ck, "Incluir en «Empezar todas», «Parar todas» y «Captura».")
        self.punto = tk.Label(cab, text="●", bg=PANEL, fg=color, font=fuente(TAM_M))   # color de la cuenta
        self.punto.pack(side="left")
        mostrado = leer_prefs().get("nombres", {}).get(str(puerto), nombre)
        self.lbl_nombre = tk.Label(cab, text=mostrado, bg=PANEL, fg=TEXTO, font=titular(TAM_M + 2))
        self.lbl_nombre.pack(side="left", padx=(ESP_S, 0))
        tk.Label(cab, text=f":{puerto}", bg=PANEL, fg=SUAVE, font=fuente(TAM_XS)).pack(side="left", padx=(ESP_S, ESP_L))
        self.lbl_estado = tk.Label(cab, text="○ En espera", bg=PANEL, fg=SUAVE, font=fuente(TAM_S, True))
        self.lbl_estado.pack(side="left")
        self.lbl_tiempo = tk.Label(cab, text="", bg=PANEL, fg=SUAVE, font=mono(TAM_S))
        self.lbl_tiempo.pack(side="left", padx=(ESP_L, 0))
        Ayuda(self.lbl_tiempo, "Tiempo que lleva en marcha esta cuenta.")

        self.b_mas = tk.Menubutton(cab, text="⋯ Más", bg=PANEL2, fg=TEXTO, activebackground=BORDE,
                                   activeforeground=TEXTO, bd=0, relief="flat", cursor="hand2",
                                   font=fuente(TAM_S), padx=ESP_M, pady=ESP_S)
        self.menu_mas = tk.Menu(self.b_mas, tearoff=0, bg=PANEL2, fg=TEXTO, activebackground=AMBAR,
                                activeforeground=TINTA, font=fuente(TAM_M), bd=0)
        self.b_mas["menu"] = self.menu_mas
        for entrada in (("⏹  Parar al acabar lo que hace", "al_parar_acabar"),
                        ("⏸  Pausar unos minutos", "al_pausar_min"),
                        None,
                        ("◈  Recoger gemas del sistema", "al_gemas"),
                        ("↻  Releer eventos ahora", "al_releer"),
                        ("◈  Probar 1 ballena (gasta 1 señuelo)", "al_probar"),
                        None,
                        ("🕑  Horario de esta cuenta", "al_horario"),
                        ("⇪  Exportar ajustes a un archivo", "al_exportar"),
                        ("⇩  Importar ajustes de un archivo", "al_importar"),
                        None,
                        ("✎  Cambiar nombre", "al_renombrar"),
                        ("☰  Registro de esta cuenta", "al_registro"),
                        ("▣  Captura de pantalla", "al_captura")):
            if entrada is None:
                self.menu_mas.add_separator()
                continue
            texto, attr = entrada
            self.menu_mas.add_command(label=texto,
                                      command=lambda a=attr: getattr(self, a) and getattr(self, a)(self))
        Ayuda(self.b_mas, "Más acciones de esta cuenta: nombre, registro, captura…")
        self.b_mas.pack(side="right", padx=(ESP_S, 0))
        self.b_ajustes = _plano(cab, "⚙ Ajustes", lambda: self.al_ajustes and self.al_ajustes(self),
                                padx=ESP_M, pady=ESP_S)
        self.b_ajustes.config(font=fuente(TAM_S))
        self.b_ajustes.pack(side="right", padx=(ESP_S, 0))
        Ayuda(self.b_ajustes, "Ajustes de esta cuenta: Rutina, Piratas, Ballenas, Cosmomante…")
        self.b_parar = _plano(cab, "■ Parar", lambda: self.al_parar and self.al_parar(self),
                              padx=ESP_M, pady=ESP_S)
        self.b_parar.config(font=fuente(TAM_S), state="disabled")
        self.b_parar.pack(side="right", padx=(ESP_S, 0))
        Ayuda(self.b_parar, "Para esta cuenta cuando termine lo que está haciendo.")
        self.b_fila = _plano(cab, "▶ Empezar", lambda: self.al_pulsar and self.al_pulsar(self),
                             bg=AMBAR, fg=TINTA, negrita=True, width=11, pady=ESP_S)
        self.b_fila.pack(side="right", padx=(ESP_S, 0))

        # fila 1: tarea, limite y barra de progreso
        ctl = tk.Frame(self, bg=PANEL)
        ctl.grid(row=1, column=0, sticky="ew", pady=(ESP_S, 0))
        prefs = leer_prefs()
        self.tarea_propia = tk.StringVar(
            value=NOMBRE_TAREA.get(prefs.get("tareas", {}).get(str(puerto)),
                                   "Rutina automática"))
        self.veces = tk.StringVar(value=str(prefs.get("veces", {}).get(str(puerto), 0)))
        self.tarea_propia.trace_add("write", lambda *a: self._cambio())
        self.veces.trace_add("write", lambda *a: self._guardar_tarea())
        self.om = tk.Menubutton(ctl, textvariable=self.tarea_propia, bg=PANEL2, fg=TEXTO,
                                activebackground=BORDE, activeforeground=TEXTO, bd=0,
                                highlightthickness=0, font=fuente(TAM_M), width=24,
                                anchor="w", padx=ESP_M, pady=ESP_S, indicatoron=True, relief="flat",
                                cursor="hand2")
        estilo = dict(bg=PANEL2, fg=TEXTO, activebackground=AMBAR,
                      activeforeground=TINTA, font=fuente(TAM_M), bd=0)
        menu = tk.Menu(self.om, tearoff=0, **estilo)
        for grupo, items in TAREA_GRUPOS:
            sub = tk.Menu(menu, tearoff=0, **estilo)
            for nombre in items:
                sub.add_command(label=nombre, command=lambda n=nombre: self.tarea_propia.set(n))
            menu.add_cascade(label=grupo, menu=sub)
        self.om["menu"] = menu
        self.om.pack(side="left")
        self.ayuda_tarea = Ayuda(self.om, "")
        self.lbl_lim = tk.Label(ctl, text="Límite", bg=PANEL, fg=SUAVE, font=fuente(TAM_S))
        self.lbl_lim.pack(side="left", padx=(ESP_L, ESP_M))
        self.spin = tk.Spinbox(ctl, from_=0, to=999, width=4, textvariable=self.veces,
                               bg=PANEL2, fg=TEXTO, buttonbackground=PANEL2, bd=0,
                               insertbackground=TEXTO, justify="center",
                               disabledbackground=PANEL, disabledforeground=BORDE,
                               font=mono(TAM_M))
        self.spin.pack(side="left", ipady=ESP_XS)
        self.lbl_unidad = tk.Label(ctl, text="", bg=PANEL, fg=SUAVE, font=fuente(TAM_S))
        self.lbl_unidad.pack(side="left", padx=(ESP_M, 0))
        Ayuda(self.spin, "Cuántas veces hacerlo. 0 = sin límite.")
        # «Solo ballenas»: pulsar su resumen abre Ajustes en la pestaña Ballenas
        self.lbl_unidad.bind("<Button-1>", lambda e: self.tarea() == "ballenas"
                             and self.al_ajustes and self.al_ajustes(self))
        self.lbl_det = tk.Label(ctl, text="", bg=PANEL, fg=SUAVE, font=fuente(TAM_S), anchor="e")
        self.lbl_det.pack(side="right")
        self.barra = Barra(ctl, ancho=140, alto=6)
        self.barra.pack(side="right", padx=(ESP_M, ESP_M))

        # filas 2 y 3: lo que hace ahora y lo que hara despues (y por que)
        self.lbl_ahora = tk.Label(self, text="", bg=PANEL, fg=TEXTO, font=fuente(TAM_S), anchor="w",
                                  justify="left")
        self.lbl_ahora.grid(row=2, column=0, sticky="ew", pady=(ESP_S, 0))
        self.lbl_sig = tk.Label(self, text="", bg=PANEL, fg=SUAVE, font=fuente(TAM_S), anchor="w",
                                justify="left")
        self.lbl_sig.grid(row=3, column=0, sticky="ew")
        self.bind("<Configure>", self._ajustar_texto)

        # fila 4: contadores del dia y boton «mas detalle»
        pie = tk.Frame(self, bg=PANEL)
        pie.grid(row=4, column=0, sticky="ew", pady=(ESP_XS, 0))
        self.lbl_hoy = tk.Label(pie, text="", bg=PANEL, fg=SUAVE, font=fuente(TAM_XS + 1), anchor="w")
        self.lbl_hoy.pack(side="left")
        self.b_detalle = tk.Button(pie, text="▸ Más detalle", bd=0, relief="flat", cursor="hand2", bg=PANEL,
                                   fg=TEAL, activebackground=PANEL, activeforeground=TEAL,
                                   font=fuente(TAM_XS), padx=0, pady=0, command=self.alternar_detalle)
        self.b_detalle.pack(side="right")
        Ayuda(self.b_detalle, "Enseña u oculta la cola de tareas y los datos de la tarea en curso.")

        # fila 5 (plegada): cola de tareas, detalle y sitio para botones extra
        self.detalle = tk.Frame(self, bg=PANEL)
        self.lbl_plan = tk.Label(self.detalle, text="", bg=PANEL, fg=SUAVE, font=fuente(TAM_S), anchor="w",
                                 justify="left", wraplength=560)
        self.lbl_plan.pack(fill="x")
        self.zona_extra = tk.Frame(self.detalle, bg=PANEL)       # botones y etiquetas de otros bloques
        self.zona_extra.pack(fill="x", pady=(ESP_S, 0))
        #  botones de las funciones de la cuenta (a mano, sin buscar el menu)
        for texto, attr in (("◈ Gemas del sistema", "al_gemas"), ("↻ Releer eventos", "al_releer"),
                            ("◈ Probar 1 ballena", "al_probar"), ("⏸ Pausar N min", "al_pausar_min"),
                            ("⏹ Parar al acabar", "al_parar_acabar"), ("🕑 Horario", "al_horario"),
                            ("⇪ Exportar", "al_exportar"), ("⇩ Importar", "al_importar")):
            b = _plano(self.zona_extra, texto,
                       lambda a=attr: getattr(self, a) and getattr(self, a)(self), pady=ESP_XS)
            b.config(font=fuente(TAM_S))
            b.pack(side="left", padx=(0, ESP_S))
        self.detalle.grid(row=5, column=0, sticky="ew", pady=(ESP_S, 0))
        self.detalle.grid_remove()
        self._cambio(guardar=False)

    # --- aspecto -----------------------------------------------------------
    def _ajustar_texto(self, e=None):
        """El texto de Ahora/Siguiente se parte en lineas segun el ancho."""
        try:
            ancho = max(200, self.winfo_width() - 2 * ESP_L - 4)
            self.lbl_ahora.config(wraplength=ancho)
            self.lbl_sig.config(wraplength=ancho)
            self.lbl_plan.config(wraplength=ancho)
        except tk.TclError:
            pass

    def alternar_detalle(self):
        self._detalle_abierto = not self._detalle_abierto
        if self._detalle_abierto:
            self.detalle.grid()
            self.b_detalle.config(text="▾ Menos detalle")
        else:
            self.detalle.grid_remove()
            self.b_detalle.config(text="▸ Más detalle")

    def anadir_accion(self, texto: str, comando):
        """Para otros bloques: una entrada mas en «⋯ Más» de la tarjeta.
        El comando recibe la tarjeta."""
        self.menu_mas.add_command(label=texto, command=lambda: comando(self))

    # --- tarea y limite -----------------------------------------------------
    def _ver_limite(self, si: bool):
        """El «Límite N» solo se ve en las tareas que tienen límite."""
        for w in (self.lbl_lim, self.spin, self.lbl_unidad):
            w.pack_forget()
        if si:
            self.lbl_lim.pack(side="left", padx=(ESP_L, ESP_M))
            self.spin.pack(side="left", ipady=ESP_XS)
        self.lbl_unidad.pack(side="left", padx=(ESP_M if si else ESP_L, 0))

    def pintar_ballenas(self):
        """«Solo ballenas»: en vez del límite, el ajuste de Ajustes > Ballenas
        en una linea («Sola · 2 al día (llevo 0) · 6 drones · gemas: sí»)."""
        if self.tarea() != "ballenas":
            return
        from cerebro import config_ballenas as cb
        prefs = leer_prefs()
        todas = prefs.get("ballenas")
        cfg = (todas if isinstance(todas, dict) else {}).get(str(self.puerto), {})
        if not isinstance(cfg, dict):
            cfg = {}
        nombres = dict(prefs.get("nombres") if isinstance(prefs.get("nombres"), dict) else {})
        extra = self.nombres_cuentas() if callable(getattr(self, "nombres_cuentas", None)) else None
        if isinstance(extra, dict):                # los nombres de todas las cuentas (lo pone la ventana)
            nombres.update(extra)
        try:
            hechas = cb.hechas_hoy(f"127.0.0.1:{self.puerto}")
        except Exception:                                     # noqa: BLE001
            hechas = None
        texto = cb.resumen(cfg, nombres, hechas)
        sin = cb.normalizar(cfg)["rol"] == "no"
        self.lbl_unidad.config(text=texto, fg=AMBAR if sin else TEXTO)
        self._b_t = time.time()

    def _cambio(self, guardar=True):
        clave = self.tarea()
        unidad = UNIDAD.get(clave)
        self._ver_limite(bool(unidad) and clave != "ballenas")   # sin limite: ni se ve
        if clave == "ballenas":                  # sin «Límite»: el resumen de su ajuste
            self.spin.config(state="disabled")
            self.pintar_ballenas()
        elif unidad:
            self.spin.config(state="normal")
            self.lbl_lim.config(fg=SUAVE)
            self.lbl_unidad.config(text=f"{unidad} · 0 = sin límite", fg=SUAVE)
        else:
            self.spin.config(state="disabled")
            self.lbl_lim.config(fg=BORDE)
            self.lbl_unidad.config(text=SIN_LIMITE.get(clave, ""), fg=SUAVE)
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
            self._t0 = self._t0 or time.time()
            self.b_fila.config(text="⏸ Pausar")
            self.b_fila.color(PANEL2, TEXTO)
            self.b_parar.config(state="normal")
            self.om.config(state="disabled")
            self.spin.config(state="disabled")
            self.config(highlightbackground=self.color)
        else:
            self._en_pausa = False
            self._t0 = None
            self.lbl_tiempo.config(text="")
            self.b_fila.config(text="▶ Empezar")
            self.b_fila.color(AMBAR, TINTA)
            self.b_parar.config(state="disabled")
            self.om.config(state="normal")
            self._cambio(guardar=False)
            self.config(highlightbackground=BORDE)

    def pausado(self, si: bool):
        """«Pausar» <-> «Reanudar» (la cuenta sigue en marcha, congelada)."""
        self._en_pausa = si
        if si:
            self.b_fila.config(text="▶ Reanudar")
            self.b_fila.color(AMBAR, TINTA)
            self.lbl_estado.config(text="⏸ En pausa", fg=AMBAR)
        else:
            self.b_fila.config(text="⏸ Pausar")
            self.b_fila.color(PANEL2, TEXTO)

    def poner_estado(self, estado: str, color=None, en_marcha: bool = True, texto: str | None = None):
        """Estado con icono y texto (nunca solo con color)."""
        color = color or COLOR_ESTADO.get(estado, TEAL if en_marcha else SUAVE)
        self.lbl_estado.config(text=f"{icono_estado(estado, en_marcha)} {texto or texto_estado(estado)}", fg=color)

    def refrescar_tiempo(self):
        if self._t0 and self.en_marcha():
            self.lbl_tiempo.config(text="⏱ " + formato_marcha(time.time() - self._t0))

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

    def ahora_siguiente(self, st: dict) -> tuple[str, str]:
        """(«Ahora», «Siguiente») sacados del plan que publica la Rutina:
        lo que hace ahora y la primera tarea de la cola, con su motivo."""
        plan = st.get("plan") or []
        ahora = [p for p in plan if p.get("e") == "ahora"]
        cola = [p for p in plan if p.get("e") == "pendiente"]
        if ahora:
            m = ahora[0].get("m", "")
            a = f"{ahora[0]['n']}" + (f" · {m}" if m else "")
        elif plan or st.get("rutina_texto"):
            a = "esperando" + (f" (siguiente {self._quedan(st['sig_c'])})" if st.get("sig_c") else "")
        else:
            a = ""
        if cola:
            m = cola[0].get("m", "")
            s = f"{cola[0]['n']}" + (f" · {m}" if m else "")
            if len(cola) > 1:
                s += f"  (y {len(cola) - 1} más)"
        elif st.get("sig_c"):
            s = f"revisar {self._quedan(st['sig_c'])}"
        else:
            s = ""
        return a, s

    def pintar_hoy(self, d: dict | None, extra: dict | None = None):
        """Contadores del dia: sigilo, normales, gemas, ballenas y señuelos (x/10)."""
        d, extra = d or {}, extra or {}
        if not d and not extra:
            self.lbl_hoy.config(text="")
            return
        sen = extra.get("senuelos", d.get("senuelos"))
        self._senuelos = None if sen is None else int(sen)
        nb = int(extra.get("ballenas", d.get("ballenas", 0)))
        txt = (f"Hoy: {int(d.get('sigilo', 0))} sigilo · {int(d.get('normales', 0))} normales · "
               f"{int(extra.get('gemas', d.get('gemas', 0)))} gemas · "
               f"{nb} {'ballena' if nb == 1 else 'ballenas'} · "
               f"señuelos {'—' if sen is None else int(sen)}/{SENUELOS_DIA}")
        if d.get("errores"):
            txt += f" · ✖ {int(d['errores'])} errores"
        self.lbl_hoy.config(text=txt)

    def pintar(self, st: dict):
        estado = st.get("estado", "en espera")
        marcha = self.en_marcha()
        color = COLOR_ESTADO.get(estado, TEAL if marcha else SUAVE)
        if getattr(self, "_en_pausa", False) and marcha:
            self.lbl_estado.config(text="⏸ En pausa", fg=AMBAR)
        else:
            self.poner_estado(estado, color, marcha)
        self.punto.config(fg=self.color)
        self.refrescar_tiempo()
        clave = self.tarea()
        if clave == "ballenas" and time.time() - getattr(self, "_b_t", 0) > 5:
            self.pintar_ballenas()              # «llevo N» al dia
        ahora, sig = self.ahora_siguiente(st)
        self.lbl_ahora.config(text=("▶ Ahora: " + ahora) if ahora else "")
        self.lbl_sig.config(text=("↳ Siguiente: " + sig) if sig else "")
        if st.get("plan"):                      # rutina: que hace y que tiene en cola
            total = st.get("rutina_total", 0)
            self.barra.set((st.get("rutina_hecho", 0) / total) if total else 0, color)
            if clave == "ballenas":
                nb = int(st.get("ballenas", 0) or 0)
                ng = int(st.get("gemas", 0) or 0)
                self.lbl_det.config(text=f"Tanda: {texto_estado(estado).lower()}  ·  "
                                         f"{nb} {'ballena muerta' if nb == 1 else 'ballenas muertas'}  ·  "
                                         f"{ng} {'gema' if ng == 1 else 'gemas'}")
            else:
                self.lbl_det.config(text=f"Lo diario: {st.get('rutina_hecho', 0)}/{total}")
            cola = [p for p in st["plan"] if p.get("e") == "pendiente"]
            self._plan("Cola: " + "  ·  ".join(p["n"] for p in cola[:6]) if cola else "")
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
        self.poner_estado("en espera", SUAVE, False)
        self.barra.set(0)
        self.lbl_det.config(text="")
        self.lbl_ahora.config(text="")
        self.lbl_sig.config(text="")
        self._plan("")

    def reset_plan(self):
        self._plan("")

    def _plan(self, texto: str):
        self.lbl_plan.config(text=texto)

    def nivel(self) -> str:
        """Nivel de la tarjeta para la cabecera: ok, aviso, error o inactivo."""
        from interfaz.tema import nivel_estado
        if not self.en_marcha():
            return "inactivo"
        estado = (self.estado or {}).get("estado", "en espera")
        if getattr(self, "sin_conexion", False):
            return "error"
        n = nivel_estado(estado, True)
        return n if n in ("aviso", "error") else "ok"
