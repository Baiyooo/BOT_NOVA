"""Caja de AJUSTES: opciones generales, por cuenta, rutina y ballenas."""
from __future__ import annotations

import tkinter as tk

from cerebro import memoria_eventos
from interfaz import panel
from interfaz.preferencias import guardar_prefs, leer_prefs
from interfaz.tema import (AMBAR, BORDE, FONDO, PANEL, PANEL2, ROJO, SUAVE, TEAL, TEXTO, TINTA, titular)
from interfaz.widgets import Ayuda, _plano


class _Ajustes:
    """Caja de AJUSTES: opciones generales, por cuenta, rutina y ballenas."""

    def _ajustes(self):
        """Opciones que no son de una instancia concreta, plegables."""
        c = tk.Frame(self.zona, bg=FONDO, padx=20)
        c.pack(fill="x", pady=(10, 0))
        self.ajustes_abiertos = tk.BooleanVar(value=bool(leer_prefs().get("ajustes_abiertos", False)))
        self.b_ajustes = tk.Button(c, text="", command=self._plegar, bg=FONDO, fg=TEAL,
                                   activebackground=FONDO, activeforeground=TEXTO, bd=0,
                                   relief="flat", font=titular(10),
                                   cursor="hand2", padx=0, pady=0, anchor="w")
        self.b_ajustes.pack(fill="x")
        self.fr_ajustes = tk.Frame(c, bg=FONDO)
        self.fr_ajustes.grid_columnconfigure(0, weight=1, uniform="a")
        self.fr_ajustes.grid_columnconfigure(1, weight=1, uniform="a")
        self.fr_ajustes.grid_columnconfigure(2, weight=1, uniform="a")

        def caja(col, titulo, color):
            k = tk.Frame(self.fr_ajustes, bg=PANEL, padx=12, pady=10,
                         highlightthickness=1, highlightbackground=BORDE)
            k.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 4, 0 if col == 2 else 4))
            tk.Frame(k, bg=color, height=2).pack(fill="x", pady=(0, 8))
            tk.Label(k, text=titulo, bg=PANEL, fg=color,
                     font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
            return k

        def casilla(master, texto, var, ayuda=""):
            ck = tk.Checkbutton(master, text=texto, variable=var, bg=PANEL, fg=TEXTO,
                                selectcolor=PANEL2, activebackground=PANEL,
                                activeforeground=TEXTO, bd=0, highlightthickness=0,
                                font=("Segoe UI", 9), anchor="w")
            ck.pack(fill="x", pady=1)
            if ayuda:
                Ayuda(ck, ayuda)

        prefs = leer_prefs()
        op = prefs.get("opciones", {})
        self.op_atacar = tk.BooleanVar(value=op.get("atacar", True))
        self.op_salto = tk.BooleanVar(value=op.get("salto", True))
        self.op_dados = tk.BooleanVar(value=op.get("dados", True))
        self.op_defensa = tk.BooleanVar(value=op.get("defensa", True))
        self.op_mision = tk.BooleanVar(value=op.get("parar_mision", True))
        self.op_mult = tk.BooleanVar(value=op.get("mult", True))
        self.op_ascender = tk.BooleanVar(value=op.get("ascender", True))
        for v in (self.op_atacar, self.op_salto, self.op_dados, self.op_defensa, self.op_mision,
                  self.op_mult, self.op_ascender):
            v.trace_add("write", lambda *a: self._guardar_opciones())
        guardadas = prefs.get("rutina", {})
        self.op_rutina = {}

        def casilla_rutina(box, k, texto, defecto):
            v = tk.BooleanVar(value=bool(guardadas.get(k, defecto)))
            v.trace_add("write", lambda *a: self._guardar_rutina())
            self.op_rutina[k] = v
            casilla(box, texto, v)

        k1 = caja(0, "Piratas", ROJO)
        casilla(k1, "Usar salto de flota (material azul)", self.op_salto)
        casilla(k1, "Retirar flotas", self.op_defensa,
                "Si entra un jugador en la batalla, retira cada flota con su Llamar.")

        k2 = caja(1, "Rutina", AMBAR)
        # desplegable: que piratas ataca la rutina (rellena los huecos entre tareas)
        for k, d in (("normales", False), ("sigilo", True)):
            v = tk.BooleanVar(value=bool(guardadas.get(k, d)))
            v.trace_add("write", lambda *a: self._guardar_rutina())
            self.op_rutina[k] = v
        opciones_pir = {"No atacar piratas": (False, False), "Solo piratas normales": (True, False),
                        "Solo piratas de sigilo": (False, True),
                        "Normales y de sigilo": (True, True)}
        inv = {v: k for k, v in opciones_pir.items()}
        self.var_piratas = tk.StringVar(value=inv[(self.op_rutina["normales"].get(),
                                                   self.op_rutina["sigilo"].get())])

        def elegir_piratas(*a):
            n, s = opciones_pir[self.var_piratas.get()]
            self.op_rutina["normales"].set(n)
            self.op_rutina["sigilo"].set(s)
        self.var_piratas.trace_add("write", elegir_piratas)
        tk.Label(k2, text="Atacar piratas", bg=PANEL, fg=SUAVE,
                 font=("Segoe UI", 8)).pack(anchor="w")
        mb = tk.Menubutton(k2, textvariable=self.var_piratas, bg=PANEL2, fg=TEXTO,
                           activebackground=BORDE, activeforeground=TEXTO, bd=0,
                           highlightthickness=0, font=("Segoe UI", 9), anchor="w",
                           padx=8, pady=3, indicatoron=True, relief="flat", cursor="hand2")
        mm = tk.Menu(mb, tearoff=0, bg=PANEL2, fg=TEXTO, activebackground=AMBAR,
                     activeforeground=TINTA, font=("Segoe UI", 9), bd=0)
        for t in opciones_pir:
            mm.add_radiobutton(label=t, variable=self.var_piratas, value=t)
        mb.config(menu=mm)
        mb.pack(fill="x", pady=(0, 6))
        Ayuda(mb, "Qué piratas ataca la Rutina entre tareas.")
        casilla_rutina(k2, "gratis", "Suministros gratis (cada 30 min)", True)
        casilla_rutina(k2, "eventos", "Recompensas de eventos", True)
        casilla_rutina(k2, "simulacion", "Simulación", True)
        casilla_rutina(k2, "recompensas", "Recompensas diarias", False)

        casilla_rutina(k2, "cosmomante", "Cosmomante (tiradas gratis y metas)", False)
        casilla_rutina(k2, "llamar_flotas", "Llamar a las flotas paradas fuera", True)
        casilla_rutina(k2, "destacamento", "Destacamento de exploración (en pruebas, sin GEC)", False)
        casilla_rutina(k2, "ballenas", "Ballenas de éter", False)
        self.op_ballenas = tk.IntVar(value=int(op.get("ballenas_dia", 2) or 0))
        self.op_ballenas.trace_add("write", lambda *a: self._guardar_opciones())
        fb = tk.Frame(k2, bg=PANEL)
        fb.pack(fill="x", pady=(0, 2))
        self.lbl_ballenas = tk.Label(fb, text="", bg=PANEL, fg=SUAVE, font=("Segoe UI", 8),
                                     anchor="w", justify="left", wraplength=150)
        self.lbl_ballenas.pack(side="left", padx=(18, 0))
        bb = tk.Button(fb, text="Ballenas…", command=self._dialogo_ballenas, bd=0, relief="flat",
                       cursor="hand2", bg=PANEL2, fg=TEAL, activebackground=BORDE,
                       activeforeground=TEAL, font=("Segoe UI", 8), padx=6)
        bb.pack(side="right")
        Ayuda(bb, "Qué cuenta invoca, cuál apoya, robots y ballenas al día de cada una.")
        self._pintar_ballenas()
        tk.Label(k2, text="Los piratas normales solo se atacan mientras un evento activo "
                          "pida fuerza pirata y esta cuenta no la haya completado.",
                 bg=PANEL, fg=SUAVE, font=("Segoe UI", 8), wraplength=180,
                 justify="left").pack(anchor="w", pady=(6, 0))

        # ---- Eventos: lista con su cuenta atras; al pulsar uno, sus ajustes y misiones
        k3 = caja(2, "Eventos", TEAL)
        self.op_tickets = tk.IntVar(value=int(op.get("roaming_tickets", 0) or 0))
        self.op_tickets.trace_add("write", lambda *a: self._guardar_opciones())
        self.ev_caja = k3
        self.ev_lista = tk.Frame(k3, bg=PANEL)
        self.ev_lista.pack(fill="x")
        self.ev_abierto = leer_prefs().get("evento_abierto", "")
        self.ev_firma = None
        self.ev_relojes = []                  # (etiqueta, fin) para la cuenta atras
        self.ev_casilla = casilla
        self._pintar_eventos(forzar=True)
        self._pintar_ajustes()

    def _generales(self) -> dict:
        """Los ajustes de la caja AJUSTES, en el mismo formato que los de cada cuenta."""
        return {"opciones": {"salto": self.op_salto.get(), "defensa": self.op_defensa.get(),
                             "dados": self.op_dados.get(), "mult": self.op_mult.get(),
                             "ascender": self.op_ascender.get()},
                "rutina": {k: v.get() for k, v in self.op_rutina.items()},
                "tickets": self._tickets()}

    def _ajustes_cuenta(self, f):
        propios = leer_prefs().get("cuentas", {}).get(str(f.puerto), {})

        def guardar(d):
            p = leer_prefs()
            p.setdefault("cuentas", {})[str(f.puerto)] = d
            guardar_prefs(p)
            self.escribir(f"127.0.0.1:{f.puerto}",
                          "Ajustes propios " + ("activados." if d["propios"] else "guardados (usa los generales)."))
        try:                                   # progreso de eventos de ESTA cuenta
            eventos = memoria_eventos.Memoria(f"127.0.0.1:{f.puerto}").resumen()
        except Exception:                                   # noqa: BLE001
            eventos = []
        panel.ventana_ajustes_cuenta(self, self.tema, self._nombres().get(str(f.puerto), f.nombre),
                                     {**propios, "eventos": eventos}, self._generales(), guardar)

    def _plegar(self):
        self.ajustes_abiertos.set(not self.ajustes_abiertos.get())
        d = leer_prefs()
        d["ajustes_abiertos"] = self.ajustes_abiertos.get()
        guardar_prefs(d)
        self._pintar_ajustes()

    def _pintar_ajustes(self):
        if self.ajustes_abiertos.get():
            self.b_ajustes.config(text="▾  ◆  AJUSTES")
            self.fr_ajustes.pack(fill="x", pady=(6, 0))
        else:
            self.b_ajustes.config(text="▸  ◆  AJUSTES")
            self.fr_ajustes.pack_forget()

    def _guardar_opciones(self):
        d = leer_prefs()
        d["opciones"] = {"atacar": self.op_atacar.get(), "salto": self.op_salto.get(),
                         "dados": self.op_dados.get(), "defensa": self.op_defensa.get(),
                         "parar_mision": self.op_mision.get(),
                         "mult": self.op_mult.get(), "ascender": self.op_ascender.get(),
                         "roaming_tickets": self._tickets(),
                         "ballenas_dia": self._ballenas_dia()}
        guardar_prefs(d)

    # ------------------------------------------------------ ballenas --
    def _cfg_ballenas(self) -> dict:
        """{puerto: {"rol": invoca/apoya/no, "con": puerto, "robots": n, "dia": n}}"""
        cfg = leer_prefs().get("ballenas")
        return cfg if isinstance(cfg, dict) else {}

    def _guardar_cfg_ballenas(self, cfg):
        d = leer_prefs()
        d["ballenas"] = cfg
        guardar_prefs(d)
        self._pintar_ballenas()

    def _pintar_ballenas(self):
        if not hasattr(self, "lbl_ballenas"):
            return
        nombres = {str(f.puerto): f.nombre.split(" - ")[-1] for f in getattr(self, "filas", [])}
        partes = [f"{nombres.get(p, p)} invoca con {nombres.get(c.get('con'), c.get('con'))} "
                  f"({c.get('dia', 0)}/día)" for p, c in self._cfg_ballenas().items()
                  if c.get("rol") == "invoca"]
        self.lbl_ballenas.config(text="; ".join(partes) or "ninguna pareja")

    def _dialogo_ballenas(self):
        cfg = {p: dict(c) for p, c in self._cfg_ballenas().items()}
        w = tk.Toplevel(self)
        w.title("Ballenas de éter")
        w.configure(bg=FONDO)
        caja = tk.Frame(w, bg=PANEL, padx=14, pady=12)
        caja.pack(fill="both", expand=True, padx=10, pady=10)
        filas = list(self.filas)
        nombres = {str(f.puerto): self._nombres().get(str(f.puerto), f.nombre) for f in filas}
        for col, t in enumerate(("Cuenta", "Papel", "Con quién", "Robots", "Al día")):
            tk.Label(caja, text=t, bg=PANEL, fg=TEAL, font=("Segoe UI", 9, "bold")).grid(
                row=0, column=col, sticky="w", padx=6, pady=(0, 6))
        roles = {"No": "no", "Invoca": "invoca", "Apoya": "apoya"}
        inv = {v: k for k, v in roles.items()}
        vars_ = {}
        for i, f in enumerate(filas, start=1):
            p = str(f.puerto)
            c = cfg.get(p, {})
            v_rol = tk.StringVar(value=inv.get(c.get("rol", "no"), "No"))
            v_con = tk.StringVar(value=nombres.get(str(c.get("con", "")), "—"))
            v_rob = tk.IntVar(value=int(c.get("robots") or 6))
            v_dia = tk.IntVar(value=int(c.get("dia") or 0))
            vars_[p] = (v_rol, v_con, v_rob, v_dia)
            tk.Label(caja, text=nombres[p], bg=PANEL, fg=TEXTO, font=("Segoe UI", 9)).grid(
                row=i, column=0, sticky="w", padx=6, pady=2)
            tk.OptionMenu(caja, v_rol, *roles).grid(row=i, column=1, sticky="ew", padx=6)
            otros = ["—"] + [nombres[str(g.puerto)] for g in filas if g is not f]
            tk.OptionMenu(caja, v_con, *otros).grid(row=i, column=2, sticky="ew", padx=6)
            tk.Spinbox(caja, from_=1, to=10, width=4, textvariable=v_rob).grid(row=i, column=3, padx=6)
            tk.Spinbox(caja, from_=0, to=40, increment=2, width=4, textvariable=v_dia).grid(
                row=i, column=4, padx=6)
        tk.Label(caja, text="Invoca = gasta sus Señuelos de éter y lleva el ciclo (hasta «Al día»).\n"
                            "Apoya = ataca a la vez y recoge la mitad de las gemas.",
                 bg=PANEL, fg=SUAVE, font=("Segoe UI", 8), justify="left").grid(
            row=len(filas) + 1, column=0, columnspan=5, sticky="w", padx=6, pady=(8, 4))
        por_nombre = {v: k for k, v in nombres.items()}

        def guardar():
            nuevo = {}
            for p, (v_rol, v_con, v_rob, v_dia) in vars_.items():
                try:
                    rob, dia = int(v_rob.get()), int(v_dia.get())
                except (ValueError, tk.TclError):
                    rob, dia = 6, 0
                nuevo[p] = {"rol": roles[v_rol.get()], "con": por_nombre.get(v_con.get(), ""),
                            "robots": max(1, min(10, rob)), "dia": max(0, min(40, dia))}
            # parejas coherentes: si A invoca con B, B apoya con A (y al reves)
            for p, c in list(nuevo.items()):
                if c["rol"] == "no" or not c["con"]:
                    c["rol"] = "no" if not c["con"] else c["rol"]
                    continue
                otro = nuevo.setdefault(c["con"], {"robots": 6, "dia": 0})
                if c["rol"] == "invoca":
                    otro.update(rol="apoya", con=p)
                elif c["rol"] == "apoya" and otro.get("rol") != "invoca":
                    otro.update(rol="invoca", con=p)
            self._guardar_cfg_ballenas(nuevo)
            self.escribir("", "Ballenas: " + (self.lbl_ballenas.cget("text") or "sin parejas") +
                          ". Se aplica al empezar cada cuenta.")
            w.destroy()
        pie = tk.Frame(caja, bg=PANEL)
        pie.grid(row=len(filas) + 2, column=0, columnspan=5, sticky="e", pady=(6, 0))
        _plano(pie, "Cancelar", w.destroy).pack(side="right", padx=(6, 0))
        _plano(pie, "Guardar", guardar, bg=AMBAR, fg=TINTA, negrita=True).pack(side="right")

    def _ballenas_dia(self) -> int:
        try:
            return max(0, int(self.op_ballenas.get()))
        except (ValueError, tk.TclError, AttributeError):
            return 0

    def _tickets(self) -> int:
        try:
            return max(0, int(self.op_tickets.get()))
        except (ValueError, tk.TclError):
            return 0

    def _guardar_rutina(self):
        d = leer_prefs()
        d["rutina"] = {k: v.get() for k, v in self.op_rutina.items()}
        guardar_prefs(d)
