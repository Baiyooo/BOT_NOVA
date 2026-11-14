"""Centro de control de NovaBot: panel principal, errores recientes, estadisticas
historicas y registro individual por cuenta.

Todo el dibujo vive aqui para no engordar la ventana (interfaz/ventana.py). Los colores llegan en un
diccionario `t` (el tema de la ventana). Cada actualizacion esta protegida: un
fallo al pintar el panel nunca debe romper la ventana principal.
"""
from __future__ import annotations

import os
import sys
import time
import tkinter as tk

from nucleo import diagnostico
from nucleo import estadisticas


def abrir_carpeta(ruta: str):
    try:
        os.makedirs(ruta, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(ruta)                                   # noqa: S606
    except Exception:                                            # noqa: BLE001
        pass


def _nombre_corto(cuenta: str, nombres: dict) -> str:
    puerto = cuenta.rsplit(":", 1)[-1]
    return nombres.get(puerto) or nombres.get(cuenta) or f"Puerto {puerto}"


class PanelControl(tk.Frame):
    """Seis indicadores y la lista de los ultimos errores."""

    TILES = (("cuentas", "Cuentas", "teal"), ("activas", "Cuentas en marcha", "ambar"),
             ("ataques", "Ataques hoy", "violeta"), ("recompensas", "Recompensas hoy", "verde"),
             ("tiempo", "Tiempo en marcha hoy", "teal"), ("errores", "Errores hoy", "rojo"))

    def __init__(self, master, t: dict):
        super().__init__(master, bg=t["FONDO"], padx=20)
        self.t = t
        tk.Label(self, text="◆  PANEL DE MANDO", bg=t["FONDO"], fg=t["TEAL"],
                 font=("Bahnschrift", 10, "bold")).pack(anchor="w", pady=(0, 6))
        rejilla = tk.Frame(self, bg=t["FONDO"])
        rejilla.pack(fill="x")
        self.valor, self.sub = {}, {}
        for i, (clave, titulo, color) in enumerate(self.TILES):
            col = t[color.upper()] if color.upper() in t else t["TEAL"]
            caja = tk.Frame(rejilla, bg=t["PANEL"], padx=10, pady=8,
                            highlightthickness=1, highlightbackground=t["BORDE"])
            caja.grid(row=i // 3, column=i % 3, sticky="nsew", padx=3, pady=3)
            rejilla.grid_columnconfigure(i % 3, weight=1, uniform="tiles")
            tk.Frame(caja, bg=col, height=2).pack(fill="x", pady=(0, 4))
            v = tk.Label(caja, text="–", bg=t["PANEL"], fg=col, font=("Bahnschrift", 18, "bold"),
                         anchor="w")
            v.pack(anchor="w")
            tk.Label(caja, text=titulo, bg=t["PANEL"], fg=t["SUAVE"], font=("Segoe UI", 8)).pack(anchor="w")
            s = tk.Label(caja, text="", bg=t["PANEL"], fg=t["SUAVE"], font=("Segoe UI", 8), anchor="w")
            s.pack(anchor="w")
            self.valor[clave], self.sub[clave] = v, s
        caja = tk.Frame(self, bg=t["PANEL"], padx=10, pady=8,
                        highlightthickness=1, highlightbackground=t["BORDE"])
        caja.pack(fill="x", pady=(6, 0))
        cab = tk.Frame(caja, bg=t["PANEL"])
        cab.pack(fill="x")
        tk.Label(cab, text="Últimos errores", bg=t["PANEL"], fg=t["TEXTO"],
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        b = tk.Button(cab, text="Abrir carpeta de errores", bd=0, relief="flat", cursor="hand2",
                      bg=t["PANEL"], fg=t["TEAL"], activebackground=t["PANEL"],
                      activeforeground=t["TEAL"], font=("Segoe UI", 8),
                      command=lambda: abrir_carpeta(diagnostico.carpeta()))
        b.pack(side="right")
        self.lbl_err = tk.Label(caja, text="Ningún error registrado.", bg=t["PANEL"], fg=t["SUAVE"],
                                font=("Consolas", 8), anchor="w", justify="left", wraplength=640)
        self.lbl_err.pack(fill="x", pady=(4, 0))

    def actualizar(self, d: dict, nombres: dict):
        """d: detectadas, conectadas, activas, ataques, recompensas, segundos, errores."""
        try:
            self.valor["cuentas"].config(text=f"{d.get('detectadas', 0)}")
            self.sub["cuentas"].config(
                text=f"{d.get('conectadas', 0)} conectadas · "
                 f"{max(0, d.get('detectadas', 0) - d.get('conectadas', 0))} sin conectar")
            self.valor["activas"].config(text=f"{d.get('activas', 0)}")
            self.valor["ataques"].config(text=f"{d.get('ataques', 0)}")
            self.valor["recompensas"].config(text=f"{d.get('recompensas', 0)}")
            self.valor["tiempo"].config(text=estadisticas.formato_tiempo(d.get("segundos", 0)))
            self.valor["errores"].config(text=f"{d.get('errores', 0)}")
            ult = diagnostico.ultimos(4)
            if ult:
                self.lbl_err.config(fg=self.t["TEXTO"], text="\n".join(
                    f"{e.get('hora', '')[11:]}  {_nombre_corto(e.get('cuenta', ''), nombres)}  "
                    f"{e.get('tarea', '')}: {e.get('error', '')[:110]}" for e in reversed(ult)))
            else:
                self.lbl_err.config(fg=self.t["SUAVE"], text="Ningún error registrado.")
        except Exception:                                        # noqa: BLE001
            pass


class PanelEstadisticas(tk.Frame):
    """Estadisticas historicas por cuenta y grafica de ataques de los ultimos 7 dias."""

    COLS = (("sigilo", "Sigilo"), ("normales", "Normales"), ("encontrados", "Vistos"),
            ("recompensas", "Recompensas"), ("ok", "Pasos bien"), ("errores", "Errores"),
            ("segundos", "Tiempo"))

    def __init__(self, master, t: dict):
        super().__init__(master, bg=t["FONDO"], padx=20)
        self.t = t
        self.abierto = tk.BooleanVar(value=False)
        self.b = tk.Button(self, text="", bd=0, relief="flat", cursor="hand2", bg=t["FONDO"],
                           fg=t["TEAL"], activebackground=t["FONDO"], activeforeground=t["TEXTO"],
                           font=("Bahnschrift", 10, "bold"), anchor="w", padx=0, pady=0,
                           command=self._plegar)
        self.b.pack(fill="x")
        self.cuerpo = tk.Frame(self, bg=t["PANEL"], padx=12, pady=10,
                               highlightthickness=1, highlightbackground=t["BORDE"])
        self.txt = tk.Text(self.cuerpo, height=8, bg=t["PANEL"], fg=t["TEXTO"], bd=0,
                           font=("Consolas", 9), wrap="none", highlightthickness=0)
        self.txt.pack(fill="x")
        self.txt.config(state="disabled")
        self.grafica = tk.Canvas(self.cuerpo, height=90, bg=t["PANEL"], highlightthickness=0)
        self.grafica.pack(fill="x", pady=(8, 0))
        self._pintar_boton()

    def _plegar(self):
        self.abierto.set(not self.abierto.get())
        self._pintar_boton()
        if self.abierto.get():
            self.actualizar({})

    def _pintar_boton(self):
        if self.abierto.get():
            self.b.config(text="▾  ◆  ESTADÍSTICAS")
            self.cuerpo.pack(fill="x", pady=(6, 0))
        else:
            self.b.config(text="▸  ◆  ESTADÍSTICAS")
            self.cuerpo.pack_forget()

    def actualizar(self, nombres: dict):
        if not self.abierto.get():
            return
        try:
            hoy = estadisticas.resumen(1)
            sem = estadisticas.resumen(7)
            lineas = [f"{'Cuenta':<16}" + "".join(f"{c[1]:>13}" for c in self.COLS), ""]
            for titulo, datos in (("HOY", hoy), ("ÚLTIMOS 7 DÍAS", sem)):
                lineas.append(f"— {titulo} —")
                for cuenta, fila in sorted(datos["cuentas"].items()):
                    celdas = []
                    for k, _ in self.COLS:
                        v = fila.get(k, 0)
                        celdas.append(f"{estadisticas.formato_tiempo(v) if k == 'segundos' else int(v):>13}")
                    lineas.append(f"{_nombre_corto(cuenta, nombres)[:15]:<16}" + "".join(celdas))
                if not datos["cuentas"]:
                    lineas.append("(sin datos todavía)")
            self.txt.config(state="normal")
            self.txt.delete("1.0", "end")
            self.txt.insert("1.0", "\n".join(lineas))
            self.txt.config(state="disabled")
            self.txt.config(height=min(18, len(lineas) + 1))
            self._barras(sem["por_dia"])
        except Exception:                                        # noqa: BLE001
            pass

    def _barras(self, por_dia: dict):
        c = self.grafica
        c.delete("all")
        c.update_idletasks()
        w = max(c.winfo_width(), 300)
        h = 90
        dias = [time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 86400)) for i in range(6, -1, -1)]
        vals = [por_dia.get(d, {}).get("sigilo", 0) + por_dia.get(d, {}).get("normales", 0) for d in dias]
        top = max(vals + [1])
        ancho = (w - 20) / 7
        c.create_text(4, 6, text="Ataques por día (sigilo y normales)", anchor="w",
                      fill=self.t["SUAVE"], font=("Segoe UI", 8))
        for i, (d, v) in enumerate(zip(dias, vals)):
            x0 = 10 + i * ancho + 6
            alto = int((h - 38) * v / top)
            c.create_rectangle(x0, h - 16 - alto, x0 + ancho - 12, h - 16,
                               fill=self.t["AMBAR"] if i == 6 else self.t.get("VIOLETA", self.t["TEAL"]), width=0)
            c.create_text(x0 + (ancho - 12) / 2, h - 16 - alto - 7, text=str(int(v)),
                          fill=self.t["TEXTO"], font=("Segoe UI", 8))
            c.create_text(x0 + (ancho - 12) / 2, h - 6, text=d[5:], fill=self.t["SUAVE"],
                          font=("Segoe UI", 7))


def ventana_registro(master, t: dict, titulo: str, ruta_registro: str):
    """Ventana con el registro individual de una cuenta (ultimas lineas)."""
    w = tk.Toplevel(master)
    w.title(f"Registro · {titulo}")
    w.configure(bg=t["FONDO"])
    w.geometry("720x420")
    txt = tk.Text(w, bg=t["PANEL"], fg=t["TEXTO"], bd=0, font=("Consolas", 9), wrap="word")
    sb = tk.Scrollbar(w, command=txt.yview)
    txt.config(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    txt.pack(fill="both", expand=True)

    def cargar():
        try:
            with open(ruta_registro, encoding="utf-8", errors="replace") as fh:
                contenido = "".join(fh.readlines()[-400:])
        except OSError:
            contenido = "(todavía no hay registro de esta cuenta)"
        txt.config(state="normal")
        txt.delete("1.0", "end")
        txt.insert("1.0", contenido)
        txt.see("end")
        txt.config(state="disabled")
        try:
            if w.winfo_exists():
                w.after(2000, cargar)
        except tk.TclError:
            pass
    cargar()
    return w


# ---------------------------------------------------------------------------
# Ajustes propios de una cuenta (no tienen por que ser los generales)
# ---------------------------------------------------------------------------
OPCIONES_CUENTA = (("salto", "Usar salto de flota (material azul)"),
                   ("defensa", "Retirar flotas si entra un jugador"),
                   ("dados", "Cosmomante: dados normales (meta de 100)"),
                   ("mult", "Cosmomante: dados remotos, imanes y x2"),
                   ("ascender", "Cosmomante: ascender hasta nivel 6"))
PASOS_RUTINA = (("gratis", "Suministros gratis"), ("eventos", "Recompensas de eventos"),
                ("simulacion", "Simulación"), ("recompensas", "Recompensas diarias"),
                ("destacamento", "Destacamento"), ("cosmomante", "Cosmomante"))
PASOS_PIRATAS = (("sigilo", "Atacar piratas de sigilo"),
                 ("normales", "Piratas normales (solo si una misión lo pide)"),
                 ("llamar_flotas", "Llamar las flotas que se queden paradas fuera"))
PASOS_CUENTA = PASOS_RUTINA + PASOS_PIRATAS
_POR_DEFECTO = ("gratis", "eventos", "simulacion", "sigilo", "llamar_flotas", "destacamento")
MARCAS = {"bot": ("●", "TEAL", "la hace el bot"), "manual": ("✋", "SUAVE", "la haces tú"),
          "espera": ("…", "AMBAR", "pendiente")}


def _cuenta_atras(fin) -> str:
    if not fin:
        return "—"
    s = int(fin - time.time())
    if s <= 0:
        return "cerrado"
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, _ = divmod(s, 60)
    if d:
        return f"{d} d {h} h"
    return f"{h} h {m:02d} min" if h else f"{m} min"


def _hace(t) -> str:
    """«Progreso de esta cuenta: hace 12 min» (o que aun no se ha mirado)."""
    if not t:
        return "Progreso de esta cuenta: aún sin mirar (se mira al empezar la Rutina)."
    s = max(0, int(time.time() - t))
    if s < 90:
        cuando = "hace un momento"
    elif s < 3600:
        cuando = f"hace {s // 60} min"
    elif s < 86400:
        cuando = f"hace {s // 3600} h {s % 3600 // 60:02d} min"
    else:
        cuando = f"hace {s // 86400} d"
    return f"Progreso de esta cuenta: mirado {cuando}."


def _num(n) -> str:
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "?"


def _pestana_eventos(padre, t: dict, eventos):
    """Eventos activos de ESTA cuenta con su progreso (zona con barra de desplazamiento)."""
    caja = tk.Frame(padre, bg=t["PANEL"])
    caja.pack(fill="both", expand=True)
    lienzo = tk.Canvas(caja, bg=t["PANEL"], highlightthickness=0, width=470, height=380)
    barra = tk.Scrollbar(caja, orient="vertical", command=lienzo.yview)
    dentro = tk.Frame(lienzo, bg=t["PANEL"])
    dentro.bind("<Configure>", lambda e: lienzo.configure(scrollregion=lienzo.bbox("all")))
    lienzo.create_window((0, 0), window=dentro, anchor="nw", width=470)
    lienzo.configure(yscrollcommand=barra.set)
    lienzo.pack(side="left", fill="both", expand=True)
    barra.pack(side="right", fill="y")
    lienzo.bind_all("<MouseWheel>", lambda e: lienzo.yview_scroll(int(-e.delta / 120), "units")
                    if lienzo.winfo_exists() else None)

    eventos = [e for e in (eventos or []) if e.get("nombre")]
    if not eventos:
        tk.Label(dentro, text="Esta cuenta aún no ha leído los eventos del juego.\n"
                              "La Rutina los lee al empezar.", bg=t["PANEL"], fg=t["SUAVE"],
                 font=("Segoe UI", 9), justify="left").pack(anchor="w", padx=6, pady=10)
        return
    for e in eventos:
        mis = e.get("misiones") or []
        del_bot = [m for m in mis if m.get("accion") == "bot"]
        hechas = sum(1 for m in del_bot if m.get("completa"))
        tarjeta = tk.Frame(dentro, bg=t["PANEL2"], padx=10, pady=8,
                           highlightbackground=t["BORDE"], highlightthickness=1)
        tarjeta.pack(fill="x", padx=4, pady=4)
        cab = tk.Frame(tarjeta, bg=t["PANEL2"])
        cab.pack(fill="x")
        tk.Label(cab, text=e["nombre"], bg=t["PANEL2"], fg=t["TEXTO"],
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        fin = e.get("fin")
        resta = (fin - time.time()) if fin else None
        col = t["SUAVE"] if resta is None else (t["ROJO"] if resta < 86400 else
                                                 (t["AMBAR"] if resta < 3 * 86400 else t["TEXTO"]))
        tk.Label(cab, text="⏱ " + _cuenta_atras(fin), bg=t["PANEL2"], fg=col,
                 font=("Segoe UI", 9)).pack(side="right")
        if e.get("subtitulo"):
            tk.Label(tarjeta, text=e["subtitulo"], bg=t["PANEL2"], fg=t["SUAVE"],
                     font=("Segoe UI", 8)).pack(anchor="w")
        if del_bot:
            tk.Label(tarjeta, text=_hace(e.get("leido_t")), bg=t["PANEL2"], fg=t["SUAVE"],
                     font=("Segoe UI", 8, "italic")).pack(anchor="w")
        if not e.get("leidas", True) and not mis:
            tk.Label(tarjeta, text="Misiones sin leer todavía.", bg=t["PANEL2"], fg=t["SUAVE"],
                     font=("Segoe UI", 8, "italic")).pack(anchor="w", pady=(4, 0))
            continue
        if del_bot:
            # barra de progreso: misiones del bot hechas / total
            fila = tk.Frame(tarjeta, bg=t["PANEL2"])
            fila.pack(fill="x", pady=(6, 4))
            barra_p = tk.Canvas(fila, height=8, bg=t["PANEL"], highlightthickness=0, width=300)
            barra_p.pack(side="left", fill="x", expand=True)
            barra_p.update_idletasks()
            ancho = 300 * hechas / max(1, len(del_bot))
            barra_p.create_rectangle(0, 0, ancho, 8, fill=t["TEAL"], outline="")
            tk.Label(fila, text=f"{hechas}/{len(del_bot)} del bot", bg=t["PANEL2"], fg=t["TEAL"],
                     font=("Segoe UI", 8, "bold")).pack(side="right", padx=(8, 0))
        for m in mis:
            if m.get("completa"):
                marca, col = "✔", t["VERDE"]
            else:
                simb, ck, _ = MARCAS.get(m.get("accion"), ("·", "SUAVE", ""))
                marca, col = simb, t[ck]
            fila = tk.Frame(tarjeta, bg=t["PANEL2"])
            fila.pack(fill="x", pady=1)
            tk.Label(fila, text=marca, bg=t["PANEL2"], fg=col, width=2,
                     font=("Segoe UI", 9)).pack(side="left")
            tk.Label(fila, text=m.get("texto", ""), bg=t["PANEL2"],
                     fg=t["SUAVE"] if m.get("completa") else t["TEXTO"], anchor="w",
                     justify="left", wraplength=320, font=("Segoe UI", 8)).pack(side="left", fill="x",
                                                                               expand=True)
            if m.get("meta"):
                tk.Label(fila, text=f"{_num(m.get('actual') or 0)} / {_num(m['meta'])}", bg=t["PANEL2"],
                         fg=col, font=("Segoe UI", 8)).pack(side="right")
    ley = tk.Frame(dentro, bg=t["PANEL"])
    ley.pack(fill="x", padx=6, pady=(6, 2))
    for simb, ck, txt in (("●", "TEAL", "la hace el bot"), ("✋", "SUAVE", "la haces tú"),
                          ("…", "AMBAR", "pendiente"), ("✔", "VERDE", "hecha")):
        tk.Label(ley, text=f"{simb} {txt}", bg=t["PANEL"], fg=t[ck],
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 10))


def ventana_ajustes_cuenta(master, t: dict, titulo: str, actuales: dict, generales: dict, guardar):
    """Ventana con los ajustes de UNA cuenta, en pestañas: Eventos (progreso de
    esta cuenta), Rutina, Piratas y Opciones.
    actuales: {"propios": bool, "opciones": {...}, "rutina": {...}, "tickets": n,
               "eventos": [resumen de memoria_eventos de ESTA cuenta]}
    generales: los ajustes generales (para mostrar sus valores mientras no se usen los propios)
    guardar(dict) se llama al pulsar Guardar con el mismo formato que `actuales` (sin eventos)."""
    from tkinter import ttk
    w = tk.Toplevel(master)
    w.title(f"Ajustes · {titulo}")
    w.configure(bg=t["FONDO"])
    w.minsize(520, 520)
    try:
        w.iconbitmap(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "recursos", "NovaBot.ico"))
    except Exception:                                         # noqa: BLE001
        pass
    propios = tk.BooleanVar(value=bool(actuales.get("propios")))
    base_op = {**generales.get("opciones", {}), **(actuales.get("opciones", {}) if actuales.get("propios") else {})}
    base_ru = {**generales.get("rutina", {}), **(actuales.get("rutina", {}) if actuales.get("propios") else {})}
    ops = {k: tk.BooleanVar(value=bool(base_op.get(k, True))) for k, _ in OPCIONES_CUENTA}
    pas = {k: tk.BooleanVar(value=bool(base_ru.get(k, k in _POR_DEFECTO))) for k, _ in PASOS_CUENTA}
    tickets = tk.IntVar(value=int(actuales.get("tickets", generales.get("tickets", 0)) or 0))

    # cabecera
    cab = tk.Frame(w, bg=t["FONDO"], padx=14, pady=10)
    cab.pack(fill="x")
    tk.Label(cab, text=titulo, bg=t["FONDO"], fg=t["TEAL"], font=("Bahnschrift", 15, "bold")).pack(anchor="w")
    tk.Label(cab, text="Ajustes y progreso de esta cuenta", bg=t["FONDO"], fg=t["SUAVE"],
             font=("Segoe UI", 9)).pack(anchor="w")
    tk.Checkbutton(cab, text="Usar ajustes propios en esta cuenta (si no, usa los generales)",
                   variable=propios, bg=t["FONDO"], fg=t["TEXTO"], selectcolor=t["PANEL2"],
                   activebackground=t["FONDO"], activeforeground=t["TEXTO"], bd=0,
                   highlightthickness=0, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(8, 0))

    est = ttk.Style(w)
    try:
        est.theme_use("clam")
    except tk.TclError:
        pass
    est.configure("Nova.TNotebook", background=t["FONDO"], borderwidth=0, tabmargins=(10, 4, 10, 0))
    est.configure("Nova.TNotebook.Tab", background=t["PANEL2"], foreground=t["TEXTO"],
                  padding=(16, 6), borderwidth=0, font=("Segoe UI", 9, "bold"))
    est.map("Nova.TNotebook.Tab", background=[("selected", t["AMBAR"])],
            foreground=[("selected", t.get("TINTA", "#170e02"))])
    libro = ttk.Notebook(w, style="Nova.TNotebook")
    libro.pack(fill="both", expand=True, padx=10)

    def hoja(nombre):
        f = tk.Frame(libro, bg=t["PANEL"], padx=14, pady=12)
        libro.add(f, text=nombre)
        return f

    def casilla(padre, texto, var):
        tk.Checkbutton(padre, text=texto, variable=var, bg=t["PANEL"], fg=t["TEXTO"],
                       selectcolor=t["PANEL2"], activebackground=t["PANEL"], activeforeground=t["TEXTO"],
                       bd=0, highlightthickness=0, anchor="w", font=("Segoe UI", 9)).pack(fill="x", pady=2)

    def titulo_seccion(padre, texto, color, nota=""):
        tk.Label(padre, text=texto, bg=t["PANEL"], fg=t[color],
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 2))
        if nota:
            tk.Label(padre, text=nota, bg=t["PANEL"], fg=t["SUAVE"], font=("Segoe UI", 8),
                     wraplength=440, justify="left").pack(anchor="w", pady=(0, 6))

    h_ev = hoja("Eventos")
    _pestana_eventos(h_ev, t, actuales.get("eventos"))

    h_ru = hoja("Rutina")
    titulo_seccion(h_ru, "Rutina automática", "AMBAR", "Qué hace esta cuenta cuando está en Rutina.")
    for k, texto in PASOS_RUTINA:
        casilla(h_ru, texto, pas[k])

    h_pi = hoja("Piratas")
    titulo_seccion(h_pi, "Piratas y flotas", "TEAL",
                   "Al acabar una tanda de piratas, las flotas se llaman de vuelta enseguida.")
    for k, texto in PASOS_PIRATAS:
        casilla(h_pi, texto, pas[k])
    casilla(h_pi, OPCIONES_CUENTA[0][1], ops["salto"])
    casilla(h_pi, OPCIONES_CUENTA[1][1], ops["defensa"])

    h_op = hoja("Opciones")
    titulo_seccion(h_op, "Cosmomante", "AMBAR")
    for k, texto in OPCIONES_CUENTA[2:]:
        casilla(h_op, texto, ops[k])
    titulo_seccion(h_op, "Roaming Test", "TEAL")
    fila = tk.Frame(h_op, bg=t["PANEL"])
    fila.pack(fill="x", pady=(2, 0))
    tk.Label(fila, text="Tickets a usar (0 = todos los que haya)", bg=t["PANEL"], fg=t["TEXTO"],
             font=("Segoe UI", 9)).pack(side="left")
    tk.Spinbox(fila, from_=0, to=99, width=4, textvariable=tickets, bg=t["PANEL2"], fg=t["TEXTO"],
               bd=0, justify="center").pack(side="left", padx=(8, 0))

    def aceptar():
        try:
            n = max(0, int(tickets.get()))
        except (ValueError, tk.TclError):
            n = 0
        guardar({"propios": bool(propios.get()),
                 "opciones": {k: bool(v.get()) for k, v in ops.items()},
                 "rutina": {k: bool(v.get()) for k, v in pas.items()}, "tickets": n})
        w.destroy()

    pie = tk.Frame(w, bg=t["FONDO"], padx=14, pady=10)
    pie.pack(fill="x")
    tk.Label(pie, text="Se aplica la próxima vez que pulses Empezar en esta cuenta.", bg=t["FONDO"],
             fg=t["SUAVE"], font=("Segoe UI", 8)).pack(side="left")
    tk.Button(pie, text="Guardar", command=aceptar, bd=0, relief="flat", cursor="hand2",
              bg=t["AMBAR"], fg=t.get("TINTA", "#170e02"), font=("Bahnschrift", 10, "bold"), padx=14, pady=6).pack(side="right")
    tk.Button(pie, text="Cancelar", command=w.destroy, bd=0, relief="flat", cursor="hand2",
              bg=t["PANEL2"], fg=t["TEXTO"], font=("Segoe UI", 9), padx=12, pady=6).pack(side="right", padx=(0, 8))
    return w
