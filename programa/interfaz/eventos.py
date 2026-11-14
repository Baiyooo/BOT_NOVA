"""Panel de eventos del juego: cuentas atras, misiones y sus ajustes."""
from __future__ import annotations

import time
import tkinter as tk

from cerebro import memoria_eventos
from cerebro.textos_mision import pulir
from interfaz.preferencias import guardar_prefs, leer_prefs
from interfaz.tema import (AMBAR, BORDE, ESP_L, ESP_M, FONDO, PANEL, PANEL2, ROJO, SUAVE, TAM_M, TAM_S, TAM_XS, TEAL, TEXTO,
                           TEXTO_MISION, VERDE, fuente, mono, titular)
from interfaz.widgets import Ayuda


def _plano(t: str) -> str:
    return memoria_eventos._compacto(t)


class _PanelEventos:
    """Panel de eventos del juego: cuentas atras, misiones y sus ajustes."""

    def _eventos(self, pagina):
        """Pestana Eventos: lista de eventos del juego (se rehace sola)."""
        self.ev_abierto = leer_prefs().get("evento_abierto", "") or ""
        self.ev_firma = None
        self.ev_relojes = []
        cont = tk.Frame(pagina, bg=FONDO, padx=ESP_L, pady=ESP_M)
        cont.pack(fill="both", expand=True)
        tk.Label(cont, text="◆  EVENTOS DEL JUEGO", bg=FONDO, fg=TEAL,
                 font=titular(TAM_M)).pack(anchor="w", pady=(0, ESP_M))
        self.ev_lista = tk.Frame(cont, bg=PANEL, padx=ESP_M, pady=ESP_M,
                                 highlightthickness=1, highlightbackground=BORDE)
        self.ev_lista.pack(fill="x")

    def ev_casilla(self, master, texto, var, ayuda=""):
        """Casilla de un ajuste dentro de un evento."""
        c = tk.Checkbutton(master, text=texto, variable=var, bg=PANEL2, fg=TEXTO,
                           activebackground=PANEL2, activeforeground=TEXTO, selectcolor=PANEL,
                           bd=0, highlightthickness=0, font=fuente(TAM_S), anchor="w",
                           command=getattr(self, "_guardar_opciones", None))
        c.pack(anchor="w")
        if ayuda:
            Ayuda(c, ayuda)

    @staticmethod
    def _cuenta_atras(fin) -> str:
        if not fin:
            return "—"
        s = int(fin - time.time())
        if s <= 0:
            return "cerrado"
        d, s = divmod(s, 86400)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        if d:
            return f"{d} d {h} h"
        if h:
            return f"{h} h {m:02d} min"
        return f"{m} min {s:02d} s"

    @staticmethod
    def _color_fin(fin):
        if not fin:
            return SUAVE
        s = fin - time.time()
        return ROJO if s < 86400 else (AMBAR if s < 3 * 86400 else TEXTO)

    def _cuenta_eventos(self) -> str:
        """Cuenta cuyo progreso se ensena: la primera marcada en marcha, o la primera."""
        filas = [f for f in self.filas if f.activa.get()] or list(self.filas)
        vivas = [f for f in filas if f.en_marcha()]
        f = (vivas or filas or [None])[0]
        return f"127.0.0.1:{f.puerto}" if f is not None else "inst"

    def _datos_eventos(self):
        try:
            mem = memoria_eventos.Memoria(self._cuenta_eventos())
            lista = mem.resumen()
        except Exception:                                   # noqa: BLE001
            lista = []
        claves = {e["clave"] for e in lista}
        for k, n in self.EV_FIJOS:
            if k not in claves:
                lista.append({"clave": k, "nombre": n, "fin": None, "misiones": [],
                              "leidas": False, "fijo": True})
        return lista

    def _abrir_evento(self, k):
        self.ev_abierto = "" if self.ev_abierto == k else k
        d = leer_prefs()
        d["evento_abierto"] = self.ev_abierto
        guardar_prefs(d)
        self._pintar_eventos(forzar=True)

    def _ajustes_evento(self, master, k):
        """Ajustes propios de algunos eventos."""
        if k == "cosmomante":
            tk.Label(master, text="Siempre: tiradas gratis y metas de dados.\n"
                                  "Gasta dados solo si calcula que llega a nivel 6 "
                                  "(70 % o más); si no, los guarda.",
                     bg=PANEL2, fg=SUAVE, font=fuente(TAM_XS), wraplength=self.ANCHO_MISION + 18,
                     justify="left").pack(anchor="w", pady=(2, 4))
            self.ev_casilla(master, "Gastar remotos, imanes y x2", self.op_mult,
                            "Lleva la nave a las mejores casillas del tablero.")
            self.ev_casilla(master, "Gastar dados normales", self.op_dados,
                            "Tira hasta la meta más alta que alcance (30, 50 o 100).")
            self.ev_casilla(master, "Subir de nivel (hasta el 6)", self.op_ascender,
                            "Pulsa Ascender cada vez que se llena la barra.")
            tk.Label(master, text="Se juega con la tarea Cosmomante o si lo activas en la Rutina.",
                     bg=PANEL2, fg=SUAVE, font=fuente(TAM_XS), wraplength=self.ANCHO_MISION + 18,
                     justify="left").pack(anchor="w", pady=(4, 0))
        elif k == "neural_roaming":
            fila = tk.Frame(master, bg=PANEL2)
            fila.pack(fill="x", pady=2)
            tk.Label(fila, text="Roaming Test: tickets a usar", bg=PANEL2, fg=TEXTO,
                     font=fuente(TAM_S)).pack(side="left")
            tk.Spinbox(fila, from_=0, to=99, width=4, textvariable=self.op_tickets,
                       bg=PANEL, fg=TEXTO, bd=0, insertbackground=TEXTO,
                       buttonbackground=PANEL, font=fuente(TAM_S),
                       justify="center").pack(side="left", padx=(8, 0))
            tk.Label(master, text="0 = todos. Solo con la tarea Roaming Test.", bg=PANEL2,
                     fg=SUAVE, font=fuente(TAM_XS)).pack(anchor="w")

    ANCHO_MISION = 480                       # ancho del texto de cada mision (px)

    def _pintar_mision(self, master, m):
        """Una mision: marca de quien la hace, titulo, lo que pide y su
        progreso con una barrita."""
        marca, color, ayuda = self.MARCA_MISION.get(m["accion"], ("?", SUAVE, ""))
        hecha = m.get("completa")
        if hecha:
            marca, color, ayuda = "✔", VERDE, "Completada"
        fila = tk.Frame(master, bg=PANEL2)
        fila.pack(fill="x", pady=(0, 5))
        tk.Label(fila, text=marca, bg=PANEL2, fg=color, width=2,
                 font=fuente(TAM_S)).pack(side="left", anchor="n")
        cuerpo = tk.Frame(fila, bg=PANEL2)
        cuerpo.pack(side="left", fill="x", expand=True)
        del_bot = m["accion"] == "bot"
        titulo, texto = m.get("titulo") or "", m.get("texto") or ""
        if not titulo:
            titulo, texto = texto, ""
        widgets = [tk.Label(cuerpo, text=titulo, bg=PANEL2,
                            fg=SUAVE if hecha else (TEXTO if del_bot else SUAVE),
                            font=fuente(TAM_XS, True), wraplength=self.ANCHO_MISION,
                            justify="left", anchor="w")]
        if texto:
            widgets.append(tk.Label(cuerpo, text=texto, bg=PANEL2,
                                    fg=SUAVE if not del_bot or hecha else TEXTO_MISION,
                                    font=fuente(TAM_XS), wraplength=self.ANCHO_MISION,
                                    justify="left", anchor="w"))
        for w in widgets:
            w.pack(anchor="w", fill="x")
        meta, actual = m.get("meta"), m.get("actual")
        if meta and actual is not None:
            linea = tk.Frame(cuerpo, bg=PANEL2)
            linea.pack(anchor="w", fill="x", pady=(1, 0))
            barra = tk.Canvas(linea, width=90, height=5, bg=PANEL, highlightthickness=0, bd=0)
            barra.pack(side="left", pady=(2, 0))
            parte = max(0.0, min(1.0, actual / meta))
            if parte:
                barra.create_rectangle(0, 0, int(90 * parte), 5, width=0,
                                       fill=VERDE if hecha else (TEAL if del_bot else SUAVE))
            cifras = f"{actual:,} / {meta:,}".replace(",", ".")
            tk.Label(linea, text=cifras, bg=PANEL2, fg=SUAVE,
                     font=fuente(TAM_XS)).pack(side="left", padx=(6, 0))
            widgets.append(linea)
        consejo = f"{ayuda}. {m.get('motivo', '')}".strip(" .") if not hecha else ayuda
        for w in widgets:
            Ayuda(w, consejo)

    def _pintar_eventos(self, forzar=False):
        """Lista de eventos tipo acordeón. Las cuentas atrás se refrescan cada
        segundo; la lista solo se rehace si cambian los datos."""
        if not hasattr(self, "ev_lista"):
            return
        for lbl, fin in self.ev_relojes:
            try:
                lbl.config(text=self._cuenta_atras(fin), fg=self._color_fin(fin))
            except tk.TclError:
                pass
        datos = self._datos_eventos()
        import json as _json
        firma = _json.dumps([datos, self.ev_abierto], sort_keys=True, default=str)
        if firma == self.ev_firma and not forzar:
            return
        self.ev_firma = firma
        for w in self.ev_lista.winfo_children():
            w.destroy()
        self.ev_relojes = []
        if not any(not e.get("fijo") for e in datos):
            tk.Label(self.ev_lista, text="Aún no se han leído los eventos del juego: la Rutina "
                                         "los lee al empezar.", bg=PANEL, fg=SUAVE,
                     font=fuente(TAM_XS), wraplength=180, justify="left").pack(anchor="w",
                                                                                pady=(0, 6))
        for e in datos:
            k = e["clave"]
            abierto = (k == self.ev_abierto)
            cab = tk.Frame(self.ev_lista, bg=PANEL2 if abierto else PANEL, cursor="hand2")
            cab.pack(fill="x", pady=(0, 2))
            flecha = tk.Label(cab, text="▾" if abierto else "▸", bg=cab["bg"], fg=TEAL,
                              font=fuente(TAM_S))
            flecha.pack(side="left", padx=(4, 4))
            nombre = tk.Label(cab, text=pulir(e.get("nombre") or k), bg=cab["bg"],
                              fg=SUAVE if e.get("fijo") else TEXTO,
                              font=fuente(TAM_S, True), anchor="w")
            nombre.pack(side="left", fill="x", expand=True)
            reloj = tk.Label(cab, text=self._cuenta_atras(e.get("fin")), bg=cab["bg"],
                             fg=self._color_fin(e.get("fin")), font=mono(TAM_S))
            reloj.pack(side="right", padx=(4, 6))
            self.ev_relojes.append((reloj, e.get("fin")))
            bot = [m for m in e.get("misiones") or [] if m["accion"] == "bot"]
            if bot:
                hechas = sum(1 for m in bot if m.get("completa"))
                tk.Label(cab, text=f"{hechas}/{len(bot)}", bg=cab["bg"],
                         fg=VERDE if hechas == len(bot) else SUAVE,
                         font=fuente(TAM_XS)).pack(side="right")
            for w in (cab, flecha, nombre, reloj):
                w.bind("<Button-1>", lambda _e, k=k: self._abrir_evento(k))
            if not abierto:
                continue
            det = tk.Frame(self.ev_lista, bg=PANEL2, padx=10, pady=6)
            det.pack(fill="x", pady=(0, 4))
            sub = pulir(e.get("subtitulo") or "")
            if sub and _plano(sub) != _plano(e.get("nombre") or ""):
                tk.Label(det, text=sub, bg=PANEL2, fg=SUAVE,
                         font=fuente(TAM_XS, cursiva=True)).pack(anchor="w")
            if e.get("info"):
                tk.Label(det, text=e["info"], bg=PANEL2, fg=SUAVE, font=fuente(TAM_XS),
                         wraplength=self.ANCHO_MISION + 18, justify="left").pack(anchor="w",
                                                                              pady=(2, 2))
            self._ajustes_evento(det, k)
            if e.get("misiones"):
                tk.Label(det, text="Misiones", bg=PANEL2, fg=TEAL,
                         font=fuente(TAM_XS, True)).pack(anchor="w", pady=(4, 2))
                for m in e["misiones"]:
                    self._pintar_mision(det, m)
            elif not e.get("fijo"):
                tk.Label(det, text="Misiones aún sin leer." if not e.get("leidas")
                         else "Este evento no tiene misiones que lea el bot.",
                         bg=PANEL2, fg=SUAVE, font=fuente(TAM_XS)).pack(anchor="w")
