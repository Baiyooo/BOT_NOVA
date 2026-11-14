"""Panel de eventos del juego: cuentas atras, misiones y sus ajustes."""
from __future__ import annotations

import time
import tkinter as tk

from cerebro import memoria_eventos
from interfaz.preferencias import guardar_prefs, leer_prefs
from interfaz.tema import AMBAR, PANEL, PANEL2, ROJO, SUAVE, TEAL, TEXTO, VERDE
from interfaz.widgets import Ayuda


class _PanelEventos:
    """Panel de eventos del juego: cuentas atras, misiones y sus ajustes."""

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
            self.ev_casilla(master, "Dados normales hasta 100", self.op_dados)
            self.ev_casilla(master, "Dados remotos, imanes y x2", self.op_mult)
            self.ev_casilla(master, "Ascender hasta nivel 6", self.op_ascender)
        elif k == "neural_roaming":
            fila = tk.Frame(master, bg=PANEL2)
            fila.pack(fill="x", pady=2)
            tk.Label(fila, text="Roaming Test: tickets a usar", bg=PANEL2, fg=TEXTO,
                     font=("Segoe UI", 9)).pack(side="left")
            tk.Spinbox(fila, from_=0, to=99, width=4, textvariable=self.op_tickets,
                       bg=PANEL, fg=TEXTO, bd=0, insertbackground=TEXTO,
                       buttonbackground=PANEL, font=("Segoe UI", 9),
                       justify="center").pack(side="left", padx=(8, 0))
            tk.Label(master, text="0 = todos. Solo con la tarea Roaming Test.", bg=PANEL2,
                     fg=SUAVE, font=("Segoe UI", 8)).pack(anchor="w")

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
                     font=("Segoe UI", 8), wraplength=180, justify="left").pack(anchor="w",
                                                                                pady=(0, 6))
        for e in datos:
            k = e["clave"]
            abierto = (k == self.ev_abierto)
            cab = tk.Frame(self.ev_lista, bg=PANEL2 if abierto else PANEL, cursor="hand2")
            cab.pack(fill="x", pady=(0, 2))
            flecha = tk.Label(cab, text="▾" if abierto else "▸", bg=cab["bg"], fg=TEAL,
                              font=("Segoe UI", 9))
            flecha.pack(side="left", padx=(4, 4))
            nombre = tk.Label(cab, text=e.get("nombre") or k, bg=cab["bg"],
                              fg=SUAVE if e.get("fijo") else TEXTO,
                              font=("Segoe UI", 9, "bold"), anchor="w")
            nombre.pack(side="left", fill="x", expand=True)
            reloj = tk.Label(cab, text=self._cuenta_atras(e.get("fin")), bg=cab["bg"],
                             fg=self._color_fin(e.get("fin")), font=("Consolas", 9))
            reloj.pack(side="right", padx=(4, 6))
            self.ev_relojes.append((reloj, e.get("fin")))
            bot = [m for m in e.get("misiones") or [] if m["accion"] == "bot"]
            if bot:
                hechas = sum(1 for m in bot if m.get("completa"))
                tk.Label(cab, text=f"{hechas}/{len(bot)}", bg=cab["bg"],
                         fg=VERDE if hechas == len(bot) else SUAVE,
                         font=("Segoe UI", 8)).pack(side="right")
            for w in (cab, flecha, nombre, reloj):
                w.bind("<Button-1>", lambda _e, k=k: self._abrir_evento(k))
            if not abierto:
                continue
            det = tk.Frame(self.ev_lista, bg=PANEL2, padx=10, pady=6)
            det.pack(fill="x", pady=(0, 4))
            if e.get("subtitulo"):
                tk.Label(det, text=e["subtitulo"], bg=PANEL2, fg=SUAVE,
                         font=("Segoe UI", 8, "italic")).pack(anchor="w")
            self._ajustes_evento(det, k)
            if e.get("misiones"):
                tk.Label(det, text="Misiones", bg=PANEL2, fg=TEAL,
                         font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(4, 0))
                for m in e["misiones"]:
                    marca, color, ayuda = self.MARCA_MISION.get(m["accion"], ("?", SUAVE, ""))
                    if m.get("completa"):
                        marca, color, ayuda = "✔", VERDE, "completada"
                    prog = ""
                    if m.get("meta") and m.get("actual") is not None:
                        prog = f"  {m['actual']:,}/{m['meta']:,}".replace(",", ".")
                    fila = tk.Frame(det, bg=PANEL2)
                    fila.pack(fill="x")
                    tk.Label(fila, text=marca, bg=PANEL2, fg=color, width=2,
                             font=("Segoe UI", 9)).pack(side="left", anchor="n")
                    lb = tk.Label(fila, text=m["texto"] + prog, bg=PANEL2,
                                  fg=TEXTO if m["accion"] == "bot" else SUAVE,
                                  font=("Segoe UI", 8), wraplength=170, justify="left",
                                  anchor="w")
                    lb.pack(side="left", fill="x")
                    Ayuda(lb, f"{ayuda}. {m.get('motivo', '')}".strip())
            elif not e.get("fijo"):
                tk.Label(det, text="Misiones aún sin leer." if not e.get("leidas")
                         else "Este evento no tiene misiones que lea el bot.",
                         bg=PANEL2, fg=SUAVE, font=("Segoe UI", 8)).pack(anchor="w")
