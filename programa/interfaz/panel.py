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
from interfaz.tema import TAM_M, TAM_S, TAM_XL, TAM_XS, TINTA, fuente, mono
from interfaz.widgets import registrar_rueda
from cerebro.textos_mision import pulir


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
                 font=fuente(TAM_M, True)).pack(anchor="w", pady=(0, 6))
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
            v = tk.Label(caja, text="–", bg=t["PANEL"], fg=col, font=fuente(TAM_XL, True),
                         anchor="w")
            v.pack(anchor="w")
            tk.Label(caja, text=titulo, bg=t["PANEL"], fg=t["SUAVE"], font=fuente(TAM_XS)).pack(anchor="w")
            s = tk.Label(caja, text="", bg=t["PANEL"], fg=t["SUAVE"], font=fuente(TAM_XS), anchor="w")
            s.pack(anchor="w")
            self.valor[clave], self.sub[clave] = v, s
        caja = tk.Frame(self, bg=t["PANEL"], padx=10, pady=8,
                        highlightthickness=1, highlightbackground=t["BORDE"])
        caja.pack(fill="x", pady=(6, 0))
        cab = tk.Frame(caja, bg=t["PANEL"])
        cab.pack(fill="x")
        tk.Label(cab, text="Últimos errores", bg=t["PANEL"], fg=t["TEXTO"],
                 font=fuente(TAM_S, True)).pack(side="left")
        b = tk.Button(cab, text="Abrir carpeta de errores", bd=0, relief="flat", cursor="hand2",
                      bg=t["PANEL"], fg=t["TEAL"], activebackground=t["PANEL"],
                      activeforeground=t["TEAL"], font=fuente(TAM_XS),
                      command=lambda: abrir_carpeta(diagnostico.carpeta()))
        b.pack(side="right")
        self.lbl_err = tk.Label(caja, text="Ningún error registrado.", bg=t["PANEL"], fg=t["SUAVE"],
                                font=mono(TAM_XS), anchor="w", justify="left", wraplength=640)
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
                           font=fuente(TAM_M, True), anchor="w", padx=0, pady=0,
                           command=self._plegar)
        self.b.pack(fill="x")
        self.cuerpo = tk.Frame(self, bg=t["PANEL"], padx=12, pady=10,
                               highlightthickness=1, highlightbackground=t["BORDE"])
        self.txt = tk.Text(self.cuerpo, height=8, bg=t["PANEL"], fg=t["TEXTO"], bd=0,
                           font=mono(TAM_S), wrap="none", highlightthickness=0)
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
                      fill=self.t["SUAVE"], font=fuente(TAM_XS))
        for i, (d, v) in enumerate(zip(dias, vals, strict=False)):
            x0 = 10 + i * ancho + 6
            alto = int((h - 38) * v / top)
            c.create_rectangle(x0, h - 16 - alto, x0 + ancho - 12, h - 16,
                               fill=self.t["AMBAR"] if i == 6 else self.t.get("VIOLETA", self.t["TEAL"]), width=0)
            c.create_text(x0 + (ancho - 12) / 2, h - 16 - alto - 7, text=str(int(v)),
                          fill=self.t["TEXTO"], font=fuente(TAM_XS))
            c.create_text(x0 + (ancho - 12) / 2, h - 6, text=d[5:], fill=self.t["SUAVE"],
                          font=fuente(TAM_XS))


def ventana_registro(master, t: dict, titulo: str, ruta_registro: str):
    """Ventana con el registro individual de una cuenta (ultimas lineas)."""
    w = tk.Toplevel(master)
    w.title(f"Registro · {titulo}")
    w.configure(bg=t["FONDO"])
    w.geometry("720x420")
    txt = tk.Text(w, bg=t["PANEL"], fg=t["TEXTO"], bd=0, font=mono(TAM_S), wrap="word")
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
# Ajustes de una cuenta (ventana «Ajustes» de su tarjeta)
# ---------------------------------------------------------------------------
OPCIONES_CUENTA = (("salto", "Usar salto de flota (material azul)"),
                   ("defensa", "Retirar flotas si entra un jugador"),
                   ("salto_normales", "Usar salto de flota (material azul)"),
                   ("mult", "Gastar remotos, imanes y x2"),
                   ("dados", "Gastar dados normales"),
                   ("ascender", "Subir de nivel (hasta el 6)"))
#  pasos de la Rutina que solo se encienden o apagan (sin mas ajustes)
#  pasos de la Rutina que solo se encienden o apagan (sin mas ajustes)
PASOS_DIARIOS = (("gratis", "Suministros gratis (cada 30 min)"),
                 ("eventos", "Recompensas de eventos"),
                 ("recompensas", "Recompensas diarias"))
#  los que se revisan por la mañana y por la tarde (cada uno con su casilla)
PASOS_TANDAS = (("simulacion", "Simulación",
                 "Simulación automática de batalla, solo si cuesta 0 GEC."),
                ("destacamento", "Destacamento de exploración", ""))
PASOS_RUTINA = PASOS_DIARIOS + tuple((k, t) for k, t, _ in PASOS_TANDAS)
PASOS_PIRATAS = (("sigilo", "Atacar piratas de sigilo"),
                 ("normales", "Piratas normales (solo si una misión lo pide)"),
                 ("llamar_flotas", "Llamar las flotas que se queden paradas fuera"))
#  pasos que se encienden en su propia pestaña
PASOS_OTROS = ("ballenas", "cosmomante", "roaming", "artefactos", "bingo", "escombros", "gemas")
PASOS_CUENTA = PASOS_RUTINA + PASOS_PIRATAS + tuple((k, k) for k in PASOS_OTROS)
_POR_DEFECTO = ("gratis", "eventos", "simulacion", "sigilo", "llamar_flotas", "destacamento",
                "escombros")
#  casillas de la tarea «Recolección»: solo gemas y escombros del sistema (lo demas es de la Rutina)
PASOS_RECOLECCION = (
    ("gemas", "Gemas del sistema",
     "Cada 5 min, si hay algún dron libre, recoge las gemas del mapa con la vista (2D o 3D) de la cuenta."),
    ("escombros", "Escombros del sistema",
     "Manda los drones libres a los escombros del sistema (mineral, aleación, cristal; nunca Núcleos)."))
RECOLECCION_DEFECTO = {"gemas": True, "escombros": True}
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
    m, s = divmod(s, 60)
    # como en el juego: «1 d 20:16:55» / «20:16:55»
    return f"{d} d {h:02d}:{m:02d}:{s:02d}" if d else f"{h:02d}:{m:02d}:{s:02d}"


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


def _pestana_eventos(padre, t: dict, eventos, obtener=None):
    """Eventos activos de ESTA cuenta con su progreso (zona con barra de
    desplazamiento). Esta viva mientras la ventana siga abierta: la cuenta
    atras baja cada segundo, un evento que llega a 0 desaparece y cada 30 s
    se vuelve a leer lo ultimo que ha visto el bot (obtener())."""
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
    # la rueda mueve esta lista solo con el raton encima (antes se quedaba
    # con la rueda de toda la aplicacion y la ventana principal no bajaba)
    lienzo.configure(yscrollincrement=22)
    registrar_rueda(lienzo, lambda golpes: lienzo.yview_scroll(
        (1 if golpes > 0 else -1) * max(1, round(abs(golpes) * 2)), "units"))

    relojes = []                              # (etiqueta, fin) que se refrescan cada segundo
    estado = {"firma": None, "leido": time.time()}

    def vivos(lista):
        ahora = time.time()
        return [e for e in (lista or []) if e.get("nombre") and not (e.get("fin") and e["fin"] <= ahora)]

    def pintar(lista):
        for w in dentro.winfo_children() or []:
            w.destroy()
        relojes.clear()
        _pintar_eventos_cuenta(dentro, t, lista, relojes)

    def tictac():
        try:
            if not dentro.winfo_exists():
                return
        except tk.TclError:
            return
        ahora = time.time()
        cerrado = any(fin and fin <= ahora for _l, fin in relojes)
        if obtener is not None and (cerrado or ahora - estado["leido"] >= 30):
            estado["leido"] = ahora
            try:
                nueva = vivos(obtener())
            except Exception:                                 # noqa: BLE001
                nueva = None
            if nueva is not None:
                import json as _json
                firma = _json.dumps(nueva, sort_keys=True, default=str)
                if firma != estado["firma"] or cerrado:
                    estado["firma"] = firma
                    pintar(nueva)
        for lbl, fin in list(relojes):
            try:
                resta = (fin - ahora) if fin else None
                lbl.config(text="⏱ " + _cuenta_atras(fin), fg=_color_resta(t, resta))
            except tk.TclError:
                pass
        dentro.after(1000, tictac)

    lista = vivos(eventos)
    import json as _json
    estado["firma"] = _json.dumps(lista, sort_keys=True, default=str)
    pintar(lista)
    dentro.after(1000, tictac)


def _color_resta(t, resta):
    return t["SUAVE"] if resta is None else (t["ROJO"] if resta < 86400 else
                                             (t["AMBAR"] if resta < 3 * 86400 else t["TEXTO"]))


def _pintar_eventos_cuenta(dentro, t, eventos, relojes):
    """Las tarjetas de los eventos (las rehace _pestana_eventos al cambiar)."""
    if not eventos:
        tk.Label(dentro, text="Esta cuenta aún no ha leído los eventos del juego.\n"
                              "La Rutina los lee al empezar.", bg=t["PANEL"], fg=t["SUAVE"],
                 font=fuente(TAM_S), justify="left").pack(anchor="w", padx=6, pady=10)
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
        tk.Label(cab, text=pulir(e["nombre"]), bg=t["PANEL2"], fg=t["TEXTO"],
                 font=fuente(TAM_M, True)).pack(side="left")
        fin = e.get("fin")
        reloj = tk.Label(cab, text="⏱ " + _cuenta_atras(fin), bg=t["PANEL2"],
                         fg=_color_resta(t, (fin - time.time()) if fin else None),
                         font=mono(TAM_S))
        reloj.pack(side="right")
        relojes.append((reloj, fin))
        sub = pulir(e.get("subtitulo") or "")
        if sub and sub.lower() != pulir(e["nombre"]).lower():
            tk.Label(tarjeta, text=sub, bg=t["PANEL2"], fg=t["SUAVE"],
                     font=fuente(TAM_XS, cursiva=True)).pack(anchor="w")
        if e.get("info"):
            tk.Label(tarjeta, text=e["info"], bg=t["PANEL2"], fg=t["SUAVE"], wraplength=420,
                     justify="left", font=fuente(TAM_XS)).pack(anchor="w", pady=(2, 0))
        if del_bot:
            tk.Label(tarjeta, text=_hace(e.get("leido_t")), bg=t["PANEL2"], fg=t["SUAVE"],
                     font=fuente(TAM_XS, cursiva=True)).pack(anchor="w")
        if not e.get("leidas", True) and not mis:
            tk.Label(tarjeta, text="Misiones sin leer todavía.", bg=t["PANEL2"], fg=t["SUAVE"],
                     font=fuente(TAM_XS, cursiva=True)).pack(anchor="w", pady=(4, 0))
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
                     font=fuente(TAM_XS, True)).pack(side="right", padx=(8, 0))
        for m in mis:
            if m.get("completa"):
                marca, col = "✔", t["VERDE"]
            else:
                simb, ck, _ = MARCAS.get(m.get("accion"), ("·", "SUAVE", ""))
                marca, col = simb, t[ck]
            fila = tk.Frame(tarjeta, bg=t["PANEL2"])
            fila.pack(fill="x", pady=1)
            tk.Label(fila, text=marca, bg=t["PANEL2"], fg=col, width=2,
                     font=fuente(TAM_S)).pack(side="left", anchor="n")
            if m.get("meta"):
                tk.Label(fila, text=f"{_num(m.get('actual') or 0)} / {_num(m['meta'])}", bg=t["PANEL2"],
                         fg=col, font=fuente(TAM_XS)).pack(side="right", anchor="n")
            cuerpo = tk.Frame(fila, bg=t["PANEL2"])
            cuerpo.pack(side="left", fill="x", expand=True)
            titulo_m, texto_m = m.get("titulo") or "", m.get("texto") or ""
            if not titulo_m:
                titulo_m, texto_m = texto_m, ""
            tenue = m.get("completa") or m.get("accion") != "bot"
            tk.Label(cuerpo, text=titulo_m, bg=t["PANEL2"], fg=t["SUAVE"] if tenue else t["TEXTO"],
                     anchor="w", justify="left", wraplength=300,
                     font=fuente(TAM_XS, True)).pack(anchor="w")
            if texto_m:
                tk.Label(cuerpo, text=texto_m, bg=t["PANEL2"], fg=t["SUAVE"], anchor="w",
                         justify="left", wraplength=300, font=fuente(TAM_XS)).pack(anchor="w")
    ley = tk.Frame(dentro, bg=t["PANEL"])
    ley.pack(fill="x", padx=6, pady=(6, 2))
    for simb, ck, txt in (("●", "TEAL", "la hace el bot"), ("✋", "SUAVE", "la haces tú"),
                          ("…", "AMBAR", "pendiente"), ("✔", "VERDE", "hecha")):
        tk.Label(ley, text=f"{simb} {txt}", bg=t["PANEL"], fg=t[ck],
                 font=fuente(TAM_XS)).pack(side="left", padx=(0, 10))


def ventana_ajustes_cuenta(master, t: dict, titulo: str, actuales: dict, guardar,
                           cuentas=(), ballenas=None):
    """Ventana con los ajustes de UNA cuenta, en pestañas: Eventos (progreso de
    esta cuenta), Rutina (que hace y resumen de las demas), Piratas, Ballenas
    y Opciones (Cosmomante y Roaming Test).
    actuales: {"opciones": {...}, "rutina": {...}, "tickets": n,
               "eventos": [resumen de memoria_eventos de ESTA cuenta]}
    cuentas: [(puerto, nombre)] de las OTRAS cuentas (para la pareja de ballenas)
    ballenas: la configuracion de cerebro/config_ballenas.py (rol sola/invoca/apoya/no,
              con, robots, dia, grupo, reparar, gemas)
    guardar(dict) se llama al pulsar Guardar con opciones, rutina, tickets y ballenas."""
    from tkinter import ttk
    w = tk.Toplevel(master)
    w.title(f"Ajustes · {titulo}")
    w.configure(bg=t["FONDO"])
    w.minsize(540, 560)
    try:
        w.iconbitmap(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                  "recursos", "NovaBot.ico"))
    except Exception:                                         # noqa: BLE001
        pass
    base_op = actuales.get("opciones", {})
    base_ru = actuales.get("rutina", {})
    ops = {k: tk.BooleanVar(value=bool(base_op.get(k, k != "salto_normales")))
           for k, _ in OPCIONES_CUENTA}
    pas = {k: tk.BooleanVar(value=bool(base_ru.get(k, k in _POR_DEFECTO))) for k, _ in PASOS_CUENTA}
    tickets = tk.IntVar(value=int(actuales.get("tickets", 0) or 0))
    from cerebro import config_ballenas as cb
    ball = cb.normalizar(ballenas)          # los ajustes de siempre + los nuevos por defecto
    nombres = {str(p): n for p, n in cuentas}
    roles = {txt: clave for clave, txt in cb.MODOS}
    v_rol = tk.StringVar(value=cb.NOMBRE_MODO[ball["rol"]])
    v_con = tk.StringVar(value=nombres.get(str(ball.get("con", "")), "—"))
    v_grupo = tk.BooleanVar(value=ball["grupo"])
    v_reparar = tk.BooleanVar(value=ball["reparar"])
    v_gemas = tk.BooleanVar(value=ball["gemas"])
    v_escombros = tk.BooleanVar(value=ball["escombros"])
    # vista del sistema en la que esta cuenta busca ballenas y gemas (2D por defecto)
    vistas = {"2D (recomendada)": "2d", "3D": "3d"}
    v_vista = tk.StringVar(value="3D" if ball.get("vista") == "3d" else "2D (recomendada)")
    # minimo (millones) de cada escombro de ballena: se guardan como texto y se leen con seguridad
    v_min = {k: tk.StringVar(value=f"{ball[f'min_{k}']:g}") for k in ("mineral", "cristal", "aleacion")}
    # robots de las ballenas: de 0 a 7 (cada cuenta tiene los suyos; por defecto 6)
    max_robots = 7
    r0 = ball.get("robots")
    v_rob = tk.IntVar(value=min(max_robots, int(6 if r0 is None else r0)))
    v_dia = tk.IntVar(value=int(ball.get("dia") or 0))

    # cabecera
    cab = tk.Frame(w, bg=t["FONDO"], padx=14, pady=10)
    cab.pack(fill="x")
    tk.Label(cab, text=titulo, bg=t["FONDO"], fg=t["TEAL"],
             font=fuente(15, True)).pack(anchor="w")
    tk.Label(cab, text="Ajustes y progreso de esta cuenta", bg=t["FONDO"], fg=t["SUAVE"],
             font=fuente(TAM_S)).pack(anchor="w")

    est = ttk.Style(w)
    try:
        est.theme_use("clam")
    except tk.TclError:
        pass
    est.configure("Nova.TNotebook", background=t["FONDO"], borderwidth=0, tabmargins=(10, 4, 10, 0))
    est.configure("Nova.TNotebook.Tab", background=t["PANEL2"], foreground=t["TEXTO"],
                  padding=(14, 6), borderwidth=0, font=fuente(TAM_S, True))
    est.map("Nova.TNotebook.Tab", background=[("selected", t["AMBAR"])],
            foreground=[("selected", t.get("TINTA", TINTA))])
    libro = ttk.Notebook(w, style="Nova.TNotebook")
    libro.pack(fill="both", expand=True, padx=10)

    def hoja(nombre):
        f = tk.Frame(libro, bg=t["PANEL"], padx=14, pady=12)
        libro.add(f, text=nombre)
        return f

    def casilla(padre, texto, var, ayuda="", sangria=0):
        ck = tk.Checkbutton(padre, text=texto, variable=var, bg=t["PANEL"], fg=t["TEXTO"],
                            selectcolor=t["PANEL2"], activebackground=t["PANEL"],
                            activeforeground=t["TEXTO"], bd=0, highlightthickness=0, anchor="w",
                            font=fuente(TAM_S))
        ck.pack(fill="x", pady=2, padx=(sangria, 0))
        if ayuda:
            tk.Label(padre, text=ayuda, bg=t["PANEL"], fg=t["SUAVE"], font=fuente(TAM_XS),
                     wraplength=440 - sangria, justify="left").pack(anchor="w", padx=(24 + sangria, 0),
                                                                    pady=(0, 3))
        return ck

    def titulo_seccion(padre, texto, color, nota="", arriba=0):
        tk.Label(padre, text=texto, bg=t["PANEL"], fg=t.get(color, t["TEAL"]),
                 font=fuente(TAM_M, True)).pack(anchor="w", pady=(arriba, 2))
        if nota:
            tk.Label(padre, text=nota, bg=t["PANEL"], fg=t["SUAVE"], font=fuente(TAM_XS),
                     wraplength=460, justify="left").pack(anchor="w", pady=(0, 6))

    def campo(padre, texto, widget_fn):
        fila = tk.Frame(padre, bg=t["PANEL"])
        fila.pack(fill="x", pady=3)
        tk.Label(fila, text=texto, bg=t["PANEL"], fg=t["TEXTO"], width=16, anchor="w",
                 font=fuente(TAM_S)).pack(side="left")
        widget_fn(fila).pack(side="left")

    def desplegable(padre, var, valores):
        mb = tk.Menubutton(padre, textvariable=var, bg=t["PANEL2"], fg=t["TEXTO"],
                           activebackground=t["BORDE"], activeforeground=t["TEXTO"], bd=0,
                           highlightthickness=0, font=fuente(TAM_S), anchor="w", width=22,
                           padx=8, pady=3, indicatoron=True, relief="flat", cursor="hand2")
        mm = tk.Menu(mb, tearoff=0, bg=t["PANEL2"], fg=t["TEXTO"], activebackground=t["AMBAR"],
                     activeforeground=t.get("TINTA", TINTA), font=fuente(TAM_S), bd=0)
        for v in valores:
            mm.add_radiobutton(label=v, variable=var, value=v)
        mb.config(menu=mm)
        return mb

    def numero(padre, var, desde, hasta, paso=1):
        return tk.Spinbox(padre, from_=desde, to=hasta, increment=paso, width=4, textvariable=var,
                          bg=t["PANEL2"], fg=t["TEXTO"], bd=0, buttonbackground=t["PANEL2"],
                          insertbackground=t["TEXTO"], justify="center")

    # ---- Eventos (progreso de esta cuenta)
    h_ev = hoja("Eventos")
    _pestana_eventos(h_ev, t, actuales.get("eventos"), actuales.get("obtener_eventos"))

    # ---- Rutina: lo que solo se enciende aqui + resumen de las otras pestañas
    h_ru = hoja("Rutina")
    titulo_seccion(h_ru, "Rutina automática", "AMBAR",
                   "Qué hace esta cuenta cuando está en Rutina. Piratas, Ballenas y los "
                   "eventos con juego propio (pestaña Opciones) se ajustan en su pestaña; "
                   "aquí ves cómo están.")
    for k, texto in PASOS_DIARIOS:
        casilla(h_ru, texto, pas[k])
    titulo_seccion(h_ru, "Mañana y tarde", "VERDE",
                   "Cada una se revisa como mucho 2 veces por la mañana y 2 por la tarde "
                   "(la tarde empieza a las 17:00 en invierno y a las 18:00 en verano).",
                   arriba=10)
    for k, texto, ayuda in PASOS_TANDAS:
        casilla(h_ru, texto, pas[k], ayuda)
    titulo_seccion(h_ru, "De las otras pestañas", "TEAL", arriba=10)
    resumen = {}
    for clave_r in ("Piratas", "Ballenas", "Cosmomante", "Roaming Test", "Artefactos",
                    "Bingo Estelar"):
        fila = tk.Frame(h_ru, bg=t["PANEL"])
        fila.pack(fill="x", pady=1)
        tk.Label(fila, text=clave_r, bg=t["PANEL"], fg=t["SUAVE"], width=12, anchor="w",
                 font=fuente(TAM_S)).pack(side="left")
        resumen[clave_r] = tk.Label(fila, text="", bg=t["PANEL"], fg=t["TEXTO"], anchor="w",
                                    font=fuente(TAM_S))
        resumen[clave_r].pack(side="left")

    def pintar_resumen(*_a):
        try:
            s, n = pas["sigilo"].get(), pas["normales"].get()
            resumen["Piratas"].config(
                text={(True, True): "sigilo y normales (si una misión lo pide)",
                      (True, False): "solo sigilo",
                      (False, True): "solo normales (si una misión lo pide)",
                      (False, False): "no ataca"}[(s, n)],
                fg=t["TEXTO"] if (s or n) else t["SUAVE"])
            rol = roles.get(v_rol.get(), "no")
            con = v_con.get()
            m_con.config(state="normal" if rol in cb.CON_PAREJA else "disabled")  # la pareja, solo si hace falta
            ajuste = {"rol": rol, "con": "x" if con != "—" else "", "robots": v_rob.get(),
                      "dia": v_dia.get(), "gemas": v_gemas.get(), "escombros": v_escombros.get(),
                      **{f"min_{k}": v.get() for k, v in v_min.items()}}
            texto_aj = cb.resumen(ajuste, {"x": con})
            lbl_resumen_b.config(text=texto_aj, fg=t["TEXTO"] if rol != "no" else t["SUAVE"])
            if rol == "no":
                resumen["Ballenas"].config(text="no hace", fg=t["SUAVE"])
            elif not pas["ballenas"].get():
                resumen["Ballenas"].config(text=texto_aj + " (solo con «Solo ballenas»)", fg=t["SUAVE"])
            else:
                resumen["Ballenas"].config(text=texto_aj, fg=t["TEXTO"])
            if rol in cb.CON_PAREJA and con == "—":
                resumen["Ballenas"].config(text="falta elegir la cuenta pareja",
                                           fg=t.get("AMBAR", t["TEXTO"]))
            if pas["cosmomante"].get():
                gasta = [x for x, k in (("remotos", "mult"), ("normales", "dados")) if ops[k].get()]
                txt = "juega: gratis y metas" + (", gasta " + " y ".join(gasta) if gasta else "")
                resumen["Cosmomante"].config(text=txt, fg=t["TEXTO"])
            else:
                resumen["Cosmomante"].config(text="no juega", fg=t["SUAVE"])
            if pas["roaming"].get():
                n = tickets.get()
                resumen["Roaming Test"].config(
                    text="juega " + ("todos los tickets" if not n else f"{n} ticket(s)") + " cada 6 h",
                    fg=t["TEXTO"])
            else:
                resumen["Roaming Test"].config(text="no juega", fg=t["SUAVE"])
            for k_ev, n_ev, txt_ev in (("artefactos", "Artefactos", "Buscar, cada 6 h"),
                                       ("bingo", "Bingo Estelar", "misiones, cada 6 h")):
                if pas[k_ev].get():
                    resumen[n_ev].config(text="juega: " + txt_ev, fg=t["TEXTO"])
                else:
                    resumen[n_ev].config(text="no juega", fg=t["SUAVE"])
        except (tk.TclError, ValueError):
            pass

    # ---- Piratas
    h_pi = hoja("Piratas")
    titulo_seccion(h_pi, "Piratas y flotas", "ROJO",
                   "Los piratas normales solo se atacan mientras un evento activo pida "
                   "fuerza pirata y esta cuenta no la haya completado.")
    def subopcion(padre_var, texto, var):
        """Casilla metida debajo de otra; en gris si la de arriba esta quitada."""
        sub = casilla(h_pi, texto, var, sangria=24)

        def activar(*_a, sub=sub):
            try:
                sub.config(state="normal" if padre_var.get() else "disabled")
            except tk.TclError:
                pass
        padre_var.trace_add("write", activar)
        activar()

    for k, texto in PASOS_PIRATAS:
        casilla(h_pi, texto, pas[k])
        if k == "sigilo":
            subopcion(pas["sigilo"], "Usar salto de flota (material azul)", ops["salto"])
        elif k == "normales":
            subopcion(pas["normales"], "Usar salto de flota (material azul)", ops["salto_normales"])
    casilla(h_pi, dict(OPCIONES_CUENTA)["defensa"], ops["defensa"])
    # recoger con los drones: aparte de matar (se puede recoger sin atacar)
    titulo_seccion(h_pi, "Recoger con drones", "VIOLETA",
                   "Busca por todo el sistema y manda un dron a cada montón libre. Cada dron "
                   "lleva su contador (ida, unos 5 min recogiendo y vuelta).", arriba=10)
    casilla(h_pi, "Escombros (mineral, aleación, cristal)", pas["escombros"])
    casilla(h_pi, "Gemas", pas["gemas"])
    campo(h_pi, "Robots", lambda p: numero(p, v_rob, 0, max_robots))
    tk.Label(h_pi, text=f"Los mismos para las gemas de las ballenas y los escombros (0 a {max_robots}).",
             bg=t["PANEL"], fg=t["SUAVE"], font=fuente(TAM_XS)).pack(anchor="w")

    # ---- Ballenas
    h_ba = hoja("Ballenas")
    titulo_seccion(h_ba, "Ballenas de éter", "VIOLETA",
                   "Usa los Señuelos de éter que ya tengas (nunca compra ni gasta GEC). Es el "
                   "único sitio donde se ajustan: lo usan la Rutina y la tarea «Solo ballenas».")
    lbl_resumen_b = tk.Label(h_ba, text="", bg=t["PANEL"], fg=t["TEXTO"], anchor="w",
                             font=fuente(TAM_S, True))
    lbl_resumen_b.pack(anchor="w", pady=(0, 6))
    fila_modo = tk.Frame(h_ba, bg=t["PANEL"])
    fila_modo.pack(fill="x", pady=3)
    tk.Label(fila_modo, text="Modo", bg=t["PANEL"], fg=t["TEXTO"], width=16, anchor="w",
             font=fuente(TAM_S)).pack(side="left")
    desplegable(fila_modo, v_rol, list(roles)).pack(side="left")
    tk.Label(h_ba, text="Sola: la cuenta invoca, ataca con su flota, espera la muerte y recoge todas "
                        "las gemas con todos sus drones, sin ayuda de nadie. Con otra cuenta: una "
                        "invoca y la otra ataca a la vez y recoge la mitad de las gemas.",
             bg=t["PANEL"], fg=t["SUAVE"], font=fuente(TAM_XS), wraplength=460,
             justify="left").pack(anchor="w", pady=(0, 4))
    fila_con = tk.Frame(h_ba, bg=t["PANEL"])
    fila_con.pack(fill="x", pady=3)
    tk.Label(fila_con, text="Cuenta pareja", bg=t["PANEL"], fg=t["TEXTO"], width=16, anchor="w",
             font=fuente(TAM_S)).pack(side="left")
    m_con = desplegable(fila_con, v_con, ["—"] + [n for _, n in cuentas])
    m_con.pack(side="left")
    tk.Label(h_ba, text="Solo con «Invoca con ayuda» o «Ayuda a otra cuenta». Al guardar, la otra "
                        "cuenta queda emparejada con esta (y con las ballenas activadas).",
             bg=t["PANEL"], fg=t["SUAVE"], font=fuente(TAM_XS), wraplength=460,
             justify="left").pack(anchor="w", pady=(0, 4))
    fila_vista = tk.Frame(h_ba, bg=t["PANEL"])
    fila_vista.pack(fill="x", pady=3)
    tk.Label(fila_vista, text="Vista", bg=t["PANEL"], fg=t["TEXTO"], width=16, anchor="w",
             font=fuente(TAM_S)).pack(side="left")
    desplegable(fila_vista, v_vista, list(vistas)).pack(side="left")
    tk.Label(h_ba, text="Vista del sistema en la que esta cuenta busca ballenas y gemas. En 2D (radar) va por "
                        "iconos con el sol de referencia; en 3D, por la forma de la ballena y las etiquetas de "
                        "las gemas.", bg=t["PANEL"], fg=t["SUAVE"], font=fuente(TAM_XS), wraplength=460,
             justify="left").pack(anchor="w", pady=(0, 4))
    campo(h_ba, "Ballenas al día", lambda p: numero(p, v_dia, 0, 40, 2))
    campo(h_ba, "Drones (robots)", lambda p: numero(p, v_rob, 0, max_robots))
    tk.Label(h_ba, text="El tope de ballenas al día no cuenta en «Ayuda a otra cuenta». Los drones "
                        "son los mismos de la pestaña Piratas (gemas y escombros).",
             bg=t["PANEL"], fg=t["SUAVE"], font=fuente(TAM_XS), wraplength=460,
             justify="left").pack(anchor="w", pady=(0, 6))
    casilla(h_ba, "Preparar el grupo de batalla 2 antes de empezar", v_grupo)
    casilla(h_ba, "Reparar las naves al acabar la tanda", v_reparar)
    casilla(h_ba, "Recoger las gemas de las ballenas", v_gemas)
    casilla(h_ba, "Recoger escombros (mineral, aleación, cristal)", v_escombros,
            "Las ballenas también sueltan escombros: se recogen después de las gemas, con los "
            "drones que queden libres (nunca Núcleos). Solo los que están junto a donde murió la "
            "ballena y superan el mínimo de abajo.", sangria=0)
    for clave_m, texto_m in (("mineral", "Mínimo mineral (millones)"),
                             ("cristal", "Mínimo cristal (millones)"),
                             ("aleacion", "Mínimo aleación (millones)")):
        campo(h_ba, texto_m, lambda p, k=clave_m: numero(p, v_min[k], 0, 999))
    titulo_seccion(h_ba, "En la Rutina", "AMBAR", arriba=8)
    casilla(h_ba, "Hacer ballenas en la Rutina", pas["ballenas"],
            "La tarea «Solo ballenas» (en el desplegable de la cuenta) no necesita esta "
            "casilla: usa este mismo modo.")

    # ---- Recolección: qué recoge la tarea «Recolección» (como en la Rutina, a elegir)
    rec = {k: tk.BooleanVar(value=bool((actuales.get("recoleccion") or {}).get(k, RECOLECCION_DEFECTO[k])))
           for k, _t, _a in PASOS_RECOLECCION}
    h_re = hoja("Recolección")
    titulo_seccion(h_re, "Recolección", "AMBAR",
                   "Qué recoge esta cuenta cuando eliges la tarea «Recolección (a elegir)»: solo lo que "
                   "marques aquí. Los suministros y las recompensas no van aquí (son de la Rutina). Los "
                   "drones y la vista (2D o 3D) son los de la pestaña Ballenas.")
    for k, texto_r, ayuda_r in PASOS_RECOLECCION:
        casilla(h_re, texto_r, rec[k], ayuda_r)
    fila_vista_r = tk.Frame(h_re, bg=t["PANEL"])
    fila_vista_r.pack(fill="x", pady=(8, 3))
    tk.Label(fila_vista_r, text="Vista", bg=t["PANEL"], fg=t["TEXTO"], width=16, anchor="w",
             font=fuente(TAM_S)).pack(side="left")
    desplegable(fila_vista_r, v_vista, list(vistas)).pack(side="left")      # la misma de la pestaña Ballenas
    tk.Label(h_re, text="2D (radar): va por iconos con el sol de referencia. 3D: lee las etiquetas de las gemas "
                        "junto a donde murió la última ballena; sin ballena reciente usa el 2D. Es el mismo "
                        "ajuste que en la pestaña Ballenas.", bg=t["PANEL"], fg=t["SUAVE"],
             font=fuente(TAM_XS), wraplength=460, justify="left").pack(anchor="w", pady=(0, 4))

    # ---- Opciones: Cosmomante y Roaming Test
    # (larga: con barra y rueda para bajar)
    from interfaz.widgets import Desplazable
    zona_op = Desplazable(hoja("Opciones"), t["PANEL"])
    zona_op.pack(fill="both", expand=True)
    h_op = zona_op.dentro
    titulo_seccion(h_op, "Cosmomante", "AMBAR",
                   "Mientras dure el evento, cada 6 h. Siempre: tiradas gratis y metas de dados. Gasta dados solo si calcula que "
                   "llega a nivel 6 (70 % o más); si no, los guarda.")
    casilla(h_op, "Jugar Cosmomante en la Rutina", pas["cosmomante"])
    casilla(h_op, dict(OPCIONES_CUENTA)["mult"], ops["mult"], "Lleva la nave a las mejores casillas.")
    casilla(h_op, dict(OPCIONES_CUENTA)["dados"], ops["dados"],
            "Tira hasta la meta más alta que alcance (30, 50 o 100).")
    casilla(h_op, dict(OPCIONES_CUENTA)["ascender"], ops["ascender"], "Pulsa Ascender al llenarse la barra.")
    titulo_seccion(h_op, "Roaming Test", "TEAL",
                   "Evento Neural Roaming. Abre el minijuego desde la lista de eventos, juega "
                   "los tickets y vuelve a la base. Mientras dure el evento, cada 6 h.", arriba=10)
    casilla(h_op, "Jugar Roaming Test en la Rutina", pas["roaming"])
    fila = tk.Frame(h_op, bg=t["PANEL"])
    fila.pack(fill="x", pady=(2, 0))
    tk.Label(fila, text="Tickets a usar (0 = todos los que haya)", bg=t["PANEL"], fg=t["TEXTO"],
             font=fuente(TAM_S)).pack(side="left")
    numero(fila, tickets, 0, 99).pack(side="left", padx=(8, 0))
    titulo_seccion(h_op, "Artefactos", "VIOLETA",
                   "Mientras dure el evento, cada 6 h: pulsa «Buscar» con todo el encendido "
                   "(una recompensa cada vez). Sus misiones (en «Añadir potencia») las lee "
                   "una sola vez: siempre son las mismas.",
                   arriba=10)
    casilla(h_op, "Jugar Artefactos en la Rutina", pas["artefactos"])
    titulo_seccion(h_op, "Bingo Estelar", "VERDE",
                   "Mientras dure el evento, cada 6 h: lee sus misiones y recoge las cumplidas. "
                   "Aún no gasta fichas en el tablero.", arriba=10)
    casilla(h_op, "Jugar Bingo Estelar en la Rutina", pas["bingo"])

    for v in list(pas.values()) + list(ops.values()) + [v_rol, v_con, v_dia, v_rob, v_gemas, v_escombros, tickets, *v_min.values()]:
        v.trace_add("write", pintar_resumen)
    pintar_resumen()
    libro.select({"Ballenas": 3, "Recolección": 4}.get(actuales.get("pestana"), 1))   # Rutina, o la de la tarea

    def entero(var, defecto, lo, hi):
        try:
            return max(lo, min(hi, int(var.get())))
        except (ValueError, tk.TclError):
            return defecto

    def aceptar():
        por_nombre = {n: p for p, n in nombres.items()}
        guardar({"opciones": {k: bool(v.get()) for k, v in ops.items()},
                 "rutina": {k: bool(v.get()) for k, v in pas.items()},
                 "tickets": entero(tickets, 0, 0, 99),
                 "recoleccion": {k: bool(v.get()) for k, v in rec.items()},
                 "ballenas": {"rol": roles.get(v_rol.get(), "no"),
                              "con": por_nombre.get(v_con.get(), ""),
                              "vista": vistas.get(v_vista.get(), "2d"),
                              "robots": entero(v_rob, 6, 0, max_robots),
                              "dia": entero(v_dia, 0, 0, 40),
                              "grupo": bool(v_grupo.get()), "reparar": bool(v_reparar.get()),
                              "gemas": bool(v_gemas.get()),
                              "escombros": bool(v_escombros.get()),
                              **{f"min_{k}": v.get() for k, v in v_min.items()}}})
        w.destroy()

    pie = tk.Frame(w, bg=t["FONDO"], padx=14, pady=10)
    pie.pack(fill="x")
    tk.Label(pie, text="Se aplica al pulsar Empezar, o al Reanudar si la cuenta está en pausa.", bg=t["FONDO"],
             fg=t["SUAVE"], font=fuente(TAM_XS)).pack(side="left")
    tk.Button(pie, text="Guardar", command=aceptar, bd=0, relief="flat", cursor="hand2",
              bg=t["AMBAR"], fg=t.get("TINTA", TINTA), font=fuente(TAM_M, True),
              padx=14, pady=6).pack(side="right")
    tk.Button(pie, text="Cancelar", command=w.destroy, bd=0, relief="flat", cursor="hand2",
              bg=t["PANEL2"], fg=t["TEXTO"], font=fuente(TAM_S), padx=12,
              pady=6).pack(side="right", padx=(0, 8))
    return w
